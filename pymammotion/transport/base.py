"""Base classes, exceptions, enums, and EventBus for the transport layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
import collections
import contextlib
from enum import Enum
import logging
import socket
import time
from typing import TYPE_CHECKING, Generic, Self, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.data.mqtt.event import ThingEventMessage
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage, ThingPropertiesMessage
    from pymammotion.data.mqtt.status import ThingStatusMessage

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
      * ``aiohttp.ClientConnectorError`` and subclasses, by class name (so we
        don't introduce a hard runtime dep on aiohttp from this module)
      * The ``__cause__`` chain for any of the above (aiohttp wraps OSError)
    """
    if isinstance(exc, (socket.gaierror, ConnectionError, TimeoutError, OSError)):
        return True
    name = type(exc).__name__
    if name in {"ClientConnectorError", "ClientConnectorDNSError", "ClientConnectorCertificateError"}:
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

    def _unsubscribe(self, sub_id: int) -> None:
        """Remove a handler by subscription ID."""
        self._handlers.pop(sub_id, None)

    def __len__(self) -> int:
        """Return the number of active subscribers."""
        return len(self._handlers)


class Transport(ABC):
    """Abstract base class for all transport implementations (MQTT, BLE).

    Concrete implementations: MQTTTransport, BLETransport.
    """

    # Maximum window kept in memory (1 hour); older entries are pruned on record_error().
    _ERROR_RETENTION_SECONDS: float = 3600.0

    #: Called on auth failure; returns True if credentials were refreshed (retry).
    on_auth_failure: Callable[[], Awaitable[bool]] | None = None

    #: Called when a per-device thing/status message arrives.
    on_device_status: Callable[[str, ThingStatusMessage], Awaitable[None]] | None = None

    #: Called when a non-protobuf thing.events message arrives (iot_id, event).
    on_device_event: Callable[[str, ThingEventMessage], Awaitable[None]] | None = None

    #: Called when a thing.properties message arrives (iot_id, properties).
    on_device_properties: Callable[[str, ThingPropertiesMessage], Awaitable[None]] | None = None

    #: Called when a Mammotion MQTT flat property/post message arrives (iot_id, properties).
    on_device_mammotion_properties: Callable[[str, MammotionPropertiesMessage], Awaitable[None]] | None = None

    #: Duration of the rate-limit ban in seconds (12 hours).
    _RATE_LIMIT_DURATION: float = 43200.0
    #: Rolling window for the outbound send counter (12 hours).
    _SEND_WINDOW: float = 43200.0
    #: Maximum sends allowed within _SEND_WINDOW before self-imposing rate limiting.
    _SEND_LIMIT: int = 600

    def __init__(self) -> None:
        """Initialise the availability listener list and error window."""
        self._availability_listeners: list[Callable[[TransportAvailability], Awaitable[None]]] = []
        self._error_timestamps: collections.deque[float] = collections.deque()
        self._last_received_monotonic: float = 0.0
        self._on_message: Callable[[bytes], Awaitable[None]] | None = None
        #: Monotonic timestamp after which a *cloud-imposed* (429) rate-limit ban expires
        #: (0 = not banned).  The self-imposed quota is NOT tracked here — it is derived
        #: live from the rolling window so it self-clears the instant the count drops back
        #: under _SEND_LIMIT.
        self._rate_limited_until: float = 0.0
        #: Rolling log of outbound send timestamps for the _SEND_WINDOW send budget.
        self._send_timestamps: collections.deque[float] = collections.deque()
        #: Edge-trigger flag so the quota-exhaustion warning logs once per entry, not per send.
        self._quota_warned: bool = False
        #: Monotonic timestamp of the most recent outbound send (0.0 = never sent).
        self._last_send_monotonic: float = 0.0
        #: Set by mark_auth_failed() when a send fails with ReLoginRequiredError.
        #: Cleared by clear_auth_failed() after successful credential recovery.
        self._auth_failed: bool = False
        #: Set by mark_unrecoverable_auth_failure() when the re-login circuit
        #: breaker trips.  Unlike _auth_failed, this is a permanent state — the
        #: transport's connect() must refuse to start a new receive loop, and
        #: is_usable stays False until something explicitly clears it.  The
        #: integration host (HA) is expected to initiate a reauth flow.
        self._unrecoverable_auth_failure: bool = False

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
    def is_rate_limited(self) -> bool:
        """True when a send is currently blocked, from either of two independent sources:

        * **Cloud-imposed ban** — the cloud returned 429; ``set_rate_limited()`` set a fixed
          ``_RATE_LIMIT_DURATION`` timer that has not yet expired.
        * **Self-imposed quota** — the rolling send window currently holds ``>= _SEND_LIMIT``
          sends.  This is computed live, so it releases the moment enough of the oldest sends
          age out of the window — no fixed wait once back under the limit.
        """
        if time.monotonic() < self._rate_limited_until:
            return True
        return self.sends_in_window() >= self._SEND_LIMIT

    def seconds_until_send_available(self) -> float:
        """Seconds until a send would be allowed again (``0.0`` if allowed right now).

        Returns the larger of the cloud-ban remaining time and the self-imposed quota
        release time.  The quota release is the moment just enough of the oldest in-window
        sends age out that the count drops back under ``_SEND_LIMIT`` — so callers that back
        off by this value (e.g. the poll loop) resume the instant the window slides under,
        instead of waiting a flat ``_RATE_LIMIT_DURATION``.
        """
        now = time.monotonic()
        cloud_remaining = max(0.0, self._rate_limited_until - now)

        cutoff = now - self._SEND_WINDOW
        in_window = [ts for ts in self._send_timestamps if ts >= cutoff]  # ascending (append order)
        quota_remaining = 0.0
        if len(in_window) >= self._SEND_LIMIT:
            # Age out (count - _SEND_LIMIT + 1) of the oldest so the count becomes
            # _SEND_LIMIT - 1.  That happens once in_window[idx] leaves the window.
            idx = len(in_window) - self._SEND_LIMIT
            quota_remaining = max(0.0, in_window[idx] + self._SEND_WINDOW - now)

        return max(cloud_remaining, quota_remaining)

    @property
    def is_usable(self) -> bool:
        """True when this transport is in a state where ``send()`` could plausibly succeed.

        Returns False when an auth failure has been recorded via
        :meth:`mark_auth_failed` or :meth:`mark_unrecoverable_auth_failure`.
        :class:`~pymammotion.transport.ble.BLETransport` overrides this to add
        BLEDevice-presence and cooldown gating.
        """
        return not self._auth_failed and not self._unrecoverable_auth_failure

    @property
    def is_unrecoverable_auth_failure(self) -> bool:
        """True after the re-login circuit breaker has tripped on this transport."""
        return self._unrecoverable_auth_failure

    def set_rate_limited(self) -> None:
        """Record a rate-limit event; blocks sends on this transport for _RATE_LIMIT_DURATION seconds."""
        self._rate_limited_until = time.monotonic() + self._RATE_LIMIT_DURATION

    def record_send(self) -> None:
        """Record one outbound send against the rolling send-window quota.

        Call this from MQTT transport send() implementations only — BLE has no cloud quota.
        No fixed-duration ban is imposed here: ``is_rate_limited`` derives the self-imposed
        quota block live from the rolling window, so sends resume automatically as soon as
        enough of the oldest entries age out and the count drops back under ``_SEND_LIMIT``.
        """
        now = time.monotonic()
        self._last_send_monotonic = now
        self._send_timestamps.append(now)
        cutoff = now - self._SEND_WINDOW
        while self._send_timestamps and self._send_timestamps[0] < cutoff:
            self._send_timestamps.popleft()
        if len(self._send_timestamps) >= self._SEND_LIMIT:
            if not self._quota_warned:
                self._quota_warned = True
                _logger.warning(
                    "%s: %d sends in %.0f h — throttling until the rolling window drops back under %d",
                    type(self).__name__,
                    len(self._send_timestamps),
                    self._SEND_WINDOW / 3600,
                    self._SEND_LIMIT,
                )
        else:
            self._quota_warned = False

    def sends_in_window(self) -> int:
        """Return the number of sends recorded in the current 24-hour rolling window."""
        cutoff = time.monotonic() - self._SEND_WINDOW
        count = 0
        for ts in reversed(self._send_timestamps):
            if ts >= cutoff:
                count += 1
            else:
                break
        return count

    def mark_auth_failed(self) -> None:
        """Mark this transport as unusable due to an authentication failure.

        ``is_usable`` returns False until ``clear_auth_failed()`` is called.
        """
        self._auth_failed = True

    def clear_auth_failed(self) -> None:
        """Clear the auth-failed flag after successful credential recovery."""
        self._auth_failed = False

    def mark_unrecoverable_auth_failure(self) -> None:
        """Mark this transport as permanently failed — the re-login circuit breaker tripped.

        Concrete transports must check this in ``connect()`` and refuse to spawn
        a new receive loop while set; otherwise stale ``call_soon(connect())``
        callbacks (scheduled by an earlier ``_on_fatal_auth`` cycle) will keep
        restarting the loop after the breaker has decided to give up.
        """
        self._unrecoverable_auth_failure = True

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
