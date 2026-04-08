"""Per-device request/response broker, event bus, and supporting types."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.transport.base import CommandTimeoutError, ConcurrentRequestError, EventBus, Subscription

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_logger = logging.getLogger(__name__)

# Maps a LubaSubMsg field name to its sub-message oneof group name.
# Used by on_message() to extract the leaf field name for correlation.
_LUBA_SUB_GROUP: dict[str, str] = {
    "net": "NetSubType",
    "nav": "SubNavMsg",
    "sys": "SubSysMsg",
    "driver": "SubDrvMsg",
    "ota": "SubOtaMsg",
    "mul": "SubMul",
    "pept": "SubPeptMsg",
    "base": "BaseStationSubType",
}


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
        self._event_bus: EventBus[Any] = EventBus()
        self._lock = asyncio.Lock()

    async def send_and_wait(
        self,
        send_fn: Callable[[], Awaitable[None]],
        expected_field: str,
        send_timeout: float = 1.0,
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
                        _logger.debug(
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
                    except Exception:  # noqa: BLE001, S110
                        pass
                if field_name is None:
                    field_name = sub_name  # fallback: top-level sub-msg name (e.g. "net", "mul")
        except Exception:  # noqa: BLE001, S110
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

    def subscribe_unsolicited(self, handler: Callable[[Any], Awaitable[None]]) -> Subscription:
        """Subscribe to unsolicited (device-initiated) messages. Returns a Subscription RAII handle."""
        return self._event_bus.subscribe(handler)

    async def close(self) -> None:
        """Cancel all pending futures and clear state. Call on device shutdown."""
        async with self._lock:
            for pending in self._pending.values():
                if not pending.future.done():
                    pending.future.cancel()
            self._pending.clear()
