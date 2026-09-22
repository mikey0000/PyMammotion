"""Base classes, exceptions, enums, and EventBus for the transport layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
import collections
import contextlib
from enum import Enum
import json
import logging
import socket
import time
from typing import TYPE_CHECKING, Generic, Self, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_logger = logging.getLogger(__name__)
T = TypeVar("T")


class TransportError(Exception):
    """Base exception for all transport failures."""


class TransportRateLimitedError(TransportError):
    """Send blocked because this transport is currently rate-limited by the cloud."""


class AuthError(TransportError):
    """Authentication refused by the remote endpoint (e.g. MQTT rc=4/5)."""


class CommandTimeoutError(TransportError):
    """No response received within timeout after all retry attempts."""

    def __init__(self, expected_field: str, attempts: int) -> None:
        """Store the field name and attempt count, then format the message."""
        self.expected_field = expected_field
        self.attempts = attempts
        super().__init__(f"No response for '{expected_field}' after {attempts} attempt(s)")


class NoTransportAvailableError(TransportError):
    """No connected transport available to send the command."""


class ConcurrentRequestError(TransportError):
    """A concurrent request for the same response field is already pending."""


class ReLoginRequiredError(AuthError):
    """Token refresh failed; a full re-login with stored credentials will be attempted."""

    def __init__(self, account_id: str, reason: str) -> None:
        """Store account ID and reason, then format the message."""
        self.account_id = account_id
        self.reason = reason
        super().__init__(f"Re-login required for account '{account_id}': {reason}")


class AccountInUseError(ReLoginRequiredError):
    """The Aliyun account is already active in another session (distributed lock held).

    Code 2152 / "distributed lock failed" from the broker means another app or
    device has an exclusive session lock on this account.  Re-login will not help
    until the other session releases the lock or times out.  HA-Luba should catch
    this separately and surface a user-visible message rather than silently retrying.
    """


class LoginFailedError(AuthError):
    """Full re-login with stored credentials failed; user must reconfigure."""

    def __init__(self, account_id: str, reason: str) -> None:
        """Store account ID and reason, then format the message."""
        self.account_id = account_id
        self.reason = reason
        super().__init__(f"Login failed for account '{account_id}': {reason}")


#: aiohttp exception classes (or bases) that indicate the request never got a
#: coherent answer — none of them is an auth verdict.
_TRANSIENT_AIOHTTP_ERRORS = frozenset(
    {
        "ClientConnectionError",
        "ClientConnectorError",
        "ClientConnectorDNSError",
        "ClientConnectorCertificateError",
        "ClientOSError",
        "ClientPayloadError",
        "ServerDisconnectedError",
        "ServerTimeoutError",
    }
)


def is_transient_network_error(exc: BaseException) -> bool:
    """Return True if *exc* is a transient connectivity failure rather than an auth one.

    Covers DNS resolution failures, connection refused/timeout, and any OSError
    socket-class error indicating the network is down.  These must NOT be
    wrapped as ``ReLoginRequiredError`` — doing so triggers a destructive full
    re-login in the MQTT transport fatal-auth handler, which itself fails the
    same way and leaves the integration looping.  Let them propagate as their
    original type so the connection loop's existing exponential-backoff catch
    handles them.

    Recognises:
      * ``socket.gaierror``                  — DNS resolution failure
      * ``ConnectionError`` / ``TimeoutError`` — generic connection failures
      * ``OSError``                          — broader socket-level errors
      * ``json.JSONDecodeError``           — truncated / half-written body
      * aiohttp connection, disconnect and payload errors, matched by class name
        anywhere in the MRO (so we don't introduce a hard runtime dep on aiohttp
        from this module)
      * The ``__cause__`` chain for any of the above (aiohttp wraps OSError)
    """
    if isinstance(exc, (socket.gaierror, ConnectionError, TimeoutError, OSError, json.JSONDecodeError)):
        return True
    if any(cls.__name__ in _TRANSIENT_AIOHTTP_ERRORS for cls in type(exc).__mro__):
        return True
    cause = exc.__cause__
    return cause is not None and isinstance(cause, (socket.gaierror, OSError, ConnectionError, TimeoutError))


class NoBLEAddressKnownError(TransportError):
    """No MAC address or external BLE device registered for this device_id."""


class BLEUnavailableError(TransportError):
    """BLE connection failed: direct connect and scan both failed."""


class SagaInterruptedError(TransportError):
    """A saga step timed out after all retries; the saga executor will restart."""


class SagaFailedError(TransportError):
    """A saga exhausted all restart attempts."""

    def __init__(self, name: str, attempts: int) -> None:
        """Store saga name and attempt count, then format the message."""
        self.name = name
        self.attempts = attempts
        super().__init__(f"Saga '{name}' failed after {attempts} attempt(s)")


class TransportType(Enum):
    """The underlying connection mechanism."""

    CLOUD_ALIYUN = "cloud_aliyun"
    CLOUD_MAMMOTION = "cloud_mammotion"
    BLE = "ble"


class SessionExpiredError(AuthError):
    """Session token expired; a targeted credential refresh should fix it.

    Carries the transport_type so the caller knows which credentials to refresh.
    """

    def __init__(self, transport_type: TransportType, message: str = "") -> None:
        """Store the transport type whose session expired."""
        self.transport_type = transport_type
        super().__init__(message or f"Session expired on {transport_type.value}")


class TransportAvailability(Enum):
    """Connection state of one transport channel."""

    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


class Subscription:
    """RAII handle for an EventBus subscription.

    Call cancel() or use as a context manager to unsubscribe.
    """

    def __init__(self, sub_id: int, unsubscribe: Callable[[], None]) -> None:
        """Store the subscription ID and unsubscribe callable."""
        self._sub_id = sub_id
        self._unsubscribe = unsubscribe
        self._cancelled = False

    def cancel(self) -> None:
        """Remove this handler from the event bus."""
        if not self._cancelled:
            self._unsubscribe()
            self._cancelled = True

    def __enter__(self) -> Self:
        """Return self for use as a context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Cancel the subscription on context exit."""
        self.cancel()


class EventBus(Generic[T]):
    """Type-safe event bus with RAII subscriptions.

    Handlers are called concurrently on emit(). An exception in one handler
    is logged but does not prevent other handlers from being called.
    """

    def __init__(self) -> None:
        """Initialise an empty event bus."""
        self._handlers: dict[int, Callable[[T], Awaitable[None]]] = {}
        self._next_id: int = 0

    def subscribe(self, handler: Callable[[T], Awaitable[None]]) -> Subscription:
        """Register a handler and return a Subscription for later cancellation."""
        sub_id = self._next_id
        self._next_id += 1
        self._handlers[sub_id] = handler

        def _remove() -> None:
            self._handlers.pop(sub_id, None)

        return Subscription(sub_id, _remove)

    async def emit(self, event: T) -> None:
        """Call all registered handlers with event.

        Copies the handler dict before iteration so unsubscribing during emit is safe.
        """
        for handler in list(self._handlers.values()):
            try:
                await handler(event)
            except Exception:
                _logger.exception("EventBus handler raised an unhandled exception")

    def __len__(self) -> int:
        """Return the number of active subscribers."""
        return len(self._handlers)


class Transport(ABC):
    """Abstract base class for all transport implementations (MQTT, BLE).

    Holds only what a link of *any* kind has: a message callback, inbound/outbound
    activity timestamps, an error window, and availability listeners.  Send quota,
    broker credentials and the ``thing/*`` message callbacks belong to
    :class:`~pymammotion.transport.cloud.CloudTransport` — BLE has none of them.

    Concrete implementations: AliyunMQTTTransport, MQTTTransport (both via
    CloudTransport), and BLETransport.
    """

    # Maximum window kept in memory (1 hour); older entries are pruned on record_error().
    _ERROR_RETENTION_SECONDS: float = 3600.0

    def __init__(self) -> None:
        """Initialise the availability listener list and error window."""
        self._availability_listeners: list[Callable[[TransportAvailability], Awaitable[None]]] = []
        self._error_timestamps: collections.deque[float] = collections.deque()
        self._last_received_monotonic: float = 0.0
        self._on_message: Callable[[bytes], Awaitable[None]] | None = None
        #: Monotonic timestamp of the most recent outbound send (0.0 = never sent).
        self._last_send_monotonic: float = 0.0

    @property
    def on_message(self) -> Callable[[bytes], Awaitable[None]] | None:
        """Callback invoked with raw bytes when the transport receives a message."""
        return self._on_message

    @on_message.setter
    def on_message(self, fn: Callable[[bytes], Awaitable[None]] | None) -> None:
        if fn is None:
            self._on_message = None
            return

        async def _wrapped(data: bytes) -> None:
            self._last_received_monotonic = time.monotonic()
            await fn(data)

        self._on_message = _wrapped

    @property
    def last_received_monotonic(self) -> float:
        """Monotonic timestamp of the last inbound message (0.0 if none yet)."""
        return self._last_received_monotonic

    def _mark_received(self) -> None:
        """Stamp inbound activity for receive paths that bypass the on_message wrapper.

        The MQTT transports deliver most traffic via on_device_message / the topic
        dispatchers, which never pass through the on_message property setter's
        timestamping wrapper — they must call this per inbound message so
        last_received_monotonic (used for poll-staleness cadence) stays honest.
        """
        self._last_received_monotonic = time.monotonic()

    @property
    def last_send_monotonic(self) -> float:
        """Monotonic timestamp of the last outbound send (0.0 if never sent)."""
        return self._last_send_monotonic

    def record_error(self) -> None:
        """Record an error occurrence at the current time.

        Prunes entries older than _ERROR_RETENTION_SECONDS to bound memory use.
        """
        now = time.monotonic()
        self._error_timestamps.append(now)
        cutoff = now - self._ERROR_RETENTION_SECONDS
        while self._error_timestamps and self._error_timestamps[0] < cutoff:
            self._error_timestamps.popleft()

    def errors_in_window(self, window_seconds: float = 1200.0) -> int:
        """Return the number of errors recorded in the last *window_seconds* seconds."""
        cutoff = time.monotonic() - window_seconds
        # deque is sorted ascending; bisect from the left
        count = 0
        for ts in reversed(self._error_timestamps):
            if ts >= cutoff:
                count += 1
            else:
                break
        return count

    def add_availability_listener(
        self,
        listener: Callable[[TransportAvailability], Awaitable[None]],
    ) -> None:
        """Register a listener for transport availability changes.

        Multiple listeners are supported — all are called on each state change.
        """
        if listener not in self._availability_listeners:
            self._availability_listeners.append(listener)

    def remove_availability_listener(
        self,
        listener: Callable[[TransportAvailability], Awaitable[None]],
    ) -> None:
        """Remove a previously registered availability listener."""
        with contextlib.suppress(ValueError):
            self._availability_listeners.remove(listener)

    async def _fire_availability_listeners(self, state: TransportAvailability) -> None:
        """Notify all registered availability listeners of a state change."""
        for listener in list(self._availability_listeners):
            try:
                await listener(state)
            except Exception:
                _logger.exception("availability listener raised an unhandled exception")

    @property
    def is_usable(self) -> bool:
        """True when this transport is in a state where ``send()`` could plausibly succeed.

        The default is unconditionally True: a link with no extra preconditions is
        usable whenever it is registered.  Both subclasses narrow it, for unrelated
        reasons — :class:`~pymammotion.transport.cloud.CloudTransport` on terminal
        auth failure, ``BLETransport`` on BLEDevice presence, signal strength and
        connect cooldown.

        ``DeviceHandle.active_transport()`` reads this polymorphically, which is why
        it stays on the base rather than moving down with the auth flags.
        """
        return True

    @abstractmethod
    async def connect(self) -> None:
        """Establish the connection. Raises TransportError or AuthError on failure."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close the connection."""

    @abstractmethod
    async def send(self, payload: bytes, iot_id: str = "", firmware_version: str = "1.0.0.0") -> None:
        """Send a raw payload. Raises TransportError if not connected."""

    async def send_heartbeat(self, payload: bytes, iot_id: str = "") -> None:
        """Send a keepalive heartbeat payload without counting it against the send quota.

        The default delegates to ``send()``.  MQTT transports override this to
        skip ``record_send()`` so periodic ble_sync pings don't burn the 300-sends/24 h
        budget.
        """
        await self.send(payload, iot_id=iot_id)

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if the transport currently has an active connection."""

    @property
    @abstractmethod
    def availability(self) -> TransportAvailability:
        """Current availability state of this transport."""

    @property
    @abstractmethod
    def transport_type(self) -> TransportType:
        """The type of this transport (CLOUD_ALIYUN, CLOUD_MAMMOTION, or BLE)."""
