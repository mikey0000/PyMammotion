"""Per-device request/response broker, event bus, and supporting types."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING, Any, Generic, TypeVar

import betterproto2

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_logger = logging.getLogger(__name__)

# Maps a LubaSubMsg field name to its sub-message oneof group name.
# Used by on_message() to extract the leaf field name for correlation.
_LUBA_SUB_GROUP: dict[str, str] = {
    "nav": "SubNavMsg",
    "sys": "SubSysMsg",
    "driver": "SubDrvMsg",
    "ota": "SubOtaMsg",
    "pept": "SubPeptMsg",
}
T = TypeVar("T")


class ConcurrentRequestError(Exception):
    """A concurrent request for the same response field is already pending."""


class CommandTimeoutError(Exception):
    """No response received after all retry attempts."""

    def __init__(self, expected_field: str, attempts: int) -> None:
        """Initialise with the field name and number of attempts made."""
        self.expected_field = expected_field
        self.attempts = attempts
        super().__init__(f"No response for '{expected_field}' after {attempts} attempt(s)")


class _EventBus(Generic[T]):
    """Simple event bus for unsolicited device messages."""

    def __init__(self) -> None:
        """Initialise with an empty handler registry."""
        self._handlers: dict[int, Callable[[T], Awaitable[None]]] = {}
        self._next_id: int = 0

    def subscribe(self, handler: Callable[[T], Awaitable[None]]) -> int:
        """Register handler and return subscription ID."""
        sub_id = self._next_id
        self._next_id += 1
        self._handlers[sub_id] = handler
        return sub_id

    def unsubscribe(self, sub_id: int) -> None:
        """Remove handler by subscription ID."""
        self._handlers.pop(sub_id, None)

    async def emit(self, event: T) -> None:
        """Emit event to all handlers; exceptions are logged, not raised."""
        for handler in list(self._handlers.values()):
            try:
                await handler(event)
            except Exception:
                _logger.exception("EventBus handler raised an unhandled exception")


@dataclass
class PendingRequest:
    """A command awaiting a specific protobuf response field."""

    expected_field: str
    future: asyncio.Future[Any]
    sent_at: float
    resend: Callable[[], Awaitable[None]]


class DeviceMessageBroker:
    """Per-device request/response broker over MQTT or BLE.

    Classifies incoming LubaMsg messages as:
    - Solicited: matches a pending send_and_wait → resolves the future
    - Unsolicited: device-initiated event → emitted to the event bus

    Correlation key is the protobuf oneof field name (e.g. 'toapp_gethash_ack'),
    since Mammotion protocol has no request ID field. At most one pending
    request per field name is allowed (ConcurrentRequestError otherwise).

    One broker instance per device, shared across MQTT and BLE transports.
    """

    def __init__(self) -> None:
        """Initialise broker with empty pending-request table and event bus."""
        self._pending: dict[str, PendingRequest] = {}
        self._event_bus: _EventBus[Any] = _EventBus()
        self._lock = asyncio.Lock()

    async def send_and_wait(
        self,
        send_fn: Callable[[], Awaitable[None]],
        expected_field: str,
        send_timeout: float = 10.0,
        retries: int = 3,
    ) -> Any:
        """Send a command and wait for the matching protobuf response.

        Args:
            send_fn: Async callable that sends the command over transport.
            expected_field: Protobuf oneof field name expected in response.
            send_timeout: Seconds to wait per attempt before retrying.
            retries: Total send attempts before raising CommandTimeoutError.

        Returns:
            The LubaMsg response with the matching field set.

        Raises:
            ConcurrentRequestError: Already waiting for same expected_field.
            CommandTimeoutError: No response after all retry attempts.

        """
        async with self._lock:
            if expected_field in self._pending:
                msg = f"Already waiting for '{expected_field}'"
                raise ConcurrentRequestError(msg)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        pending = PendingRequest(
            expected_field=expected_field,
            future=future,
            sent_at=time.monotonic(),
            resend=send_fn,
        )

        async with self._lock:
            self._pending[expected_field] = pending

        try:
            for attempt in range(1, retries + 1):
                await send_fn()
                try:
                    # shield prevents the future being cancelled on timeout;
                    # a late response can still resolve it on retry
                    return await asyncio.wait_for(asyncio.shield(future), timeout=send_timeout)
                except TimeoutError:
                    if attempt < retries:
                        _logger.warning(
                            "No response for '%s' (attempt %d/%d), retrying",
                            expected_field,
                            attempt,
                            retries,
                        )
                    else:
                        raise CommandTimeoutError(expected_field, retries) from None
        finally:
            async with self._lock:
                self._pending.pop(expected_field, None)
            if not future.done():
                future.cancel()

    async def on_message(self, message: Any) -> None:
        """Route an incoming message to a pending future or the event bus.

        Called by the transport layer for every incoming message.
        Supports LubaMsg hierarchy (LubaSubMsg → SubNavMsg / SubSysMsg / …) as
        well as a generic ``"payload"`` oneof group for test doubles.
        """
        field_name: str | None = None

        # Try LubaMsg hierarchy first: LubaSubMsg → sub-group → leaf field
        try:
            sub_name, sub_val = betterproto2.which_one_of(message, "LubaSubMsg")
            if sub_name and sub_val is not None:
                sub_group = _LUBA_SUB_GROUP.get(sub_name)
                if sub_group:
                    try:
                        leaf_name, _ = betterproto2.which_one_of(sub_val, sub_group)
                        if leaf_name:
                            field_name = leaf_name
                    except Exception:  # noqa: BLE001
                        pass
                if field_name is None:
                    field_name = sub_name  # fallback: top-level sub-msg name (e.g. "net", "mul")
        except Exception:  # noqa: BLE001
            pass

        # Fallback: generic "payload" oneof (used by test doubles and future protocols)
        if field_name is None:
            try:
                field_name, _ = betterproto2.which_one_of(message, "payload")
            except Exception:  # noqa: BLE001
                _logger.debug("on_message: could not extract field name, treating as unsolicited")

        if field_name:
            async with self._lock:
                pending = self._pending.get(field_name)

            if pending is not None and not pending.future.done():
                pending.future.set_result(message)
                return  # solicited — do NOT emit to event bus

        await self._event_bus.emit(message)

    def subscribe_unsolicited(self, handler: Callable[[Any], Awaitable[None]]) -> int:
        """Subscribe to unsolicited (device-initiated) messages. Returns sub ID."""
        return self._event_bus.subscribe(handler)

    def unsubscribe_unsolicited(self, sub_id: int) -> None:
        """Unsubscribe from unsolicited messages."""
        self._event_bus.unsubscribe(sub_id)

    async def close(self) -> None:
        """Cancel all pending futures and clear state. Call on device shutdown."""
        async with self._lock:
            for pending in self._pending.values():
                if not pending.future.done():
                    pending.future.cancel()
            self._pending.clear()
