"""CloudTransport — the Transport surface that only the two MQTT transports have.

Sits between :class:`~pymammotion.transport.base.Transport` and
``AliyunMQTTTransport`` / ``MQTTTransport``.  Everything here is meaningless for
BLE: a Bluetooth link has no cloud send quota, no broker credentials to be
rejected, and no ``thing/*`` message kinds.  These members used to live on the
shared base, where ``BLETransport`` inherited ~15 of them and used none — the
leak was visible in ``BLETransport.send``, which still carries ``iot_id`` and
``firmware_version`` parameters it ignores, and in ``Transport.is_usable``,
which BLE *had* to override because the default was computed from cloud auth
flags.

Deliberately not solved by giving BLE no-op stubs: that reproduces the same
coupling with an extra layer of indirection.  See ``docs/decisions.md`` D2 for
the earlier version of that mistake.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import collections
import logging
import time
from typing import TYPE_CHECKING

from packaging.version import InvalidVersion, Version

from pymammotion.transport.base import Transport, TransportRateLimitedError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.data.mqtt.event import ThingEventMessage
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage, ThingPropertiesMessage
    from pymammotion.data.mqtt.status import ThingStatusMessage

_logger = logging.getLogger(__name__)

#: Firmware version at which devices migrated to the Mammotion MQTT broker.
#: Devices on this version or newer are not subject to the cloud send quota
#: (see ``CloudTransport.is_send_blocked``).
RATE_LIMIT_REMOVED_VERSION = Version("1.30.25.1")

#: Starting delay for an MQTT reconnect, doubling on each consecutive failure.
#: Shared by both cloud transports.
MQTT_RECONNECT_MIN_SEC = 1

#: Ceiling for that backoff.  The two transports deliberately differ, so the
#: values live here together rather than drifting apart in separate modules:
#:
#: * Aliyun (60 s) — the broker enforces a single session per identity, so a
#:   longer gap means a longer window in which the phone app can hold the slot.
#: * Mammotion direct (120 s) — no such contention, so back off harder and keep
#:   reconnect traffic down.
#:
#: This asymmetry was previously two unrelated ``_MQTT_RECONNECT_MAX_SEC``
#: definitions and read as an accident; if it turns out to be one, changing it is
#: now a one-line edit in one place.
MQTT_RECONNECT_MAX_SEC_ALIYUN = 60
MQTT_RECONNECT_MAX_SEC_MAMMOTION = 120


class CloudTransport(Transport, ABC):
    """A Transport that talks to a broker: send quota, broker credentials, ``thing/*`` messages.

    Concrete implementations: ``AliyunMQTTTransport``, ``MQTTTransport``.
    """

    #: Called on auth failure; returns True if credentials were refreshed (retry).
    on_auth_failure: Callable[[], Awaitable[bool]] | None = None

    #: Called when credential recovery is exhausted and this transport is giving up.
    #: One declaration for both transports: the two used to declare it separately with
    #: divergent parameter types (``Exception`` vs ``ReLoginRequiredError``), and a
    #: handler that accepts only the narrow type cannot safely serve a caller that may
    #: pass any exception.
    on_fatal_auth_error: Callable[[Exception], Awaitable[None]] | None = None

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
        """Initialise the send-quota window and the terminal auth flags."""
        super().__init__()
        #: Monotonic timestamp after which a *cloud-imposed* (429) rate-limit ban expires
        #: (0 = not banned).  The self-imposed quota is NOT tracked here — it is derived
        #: live from the rolling window so it self-clears the instant the count drops back
        #: under _SEND_LIMIT.
        self._rate_limited_until: float = 0.0
        #: Rolling log of outbound send timestamps for the _SEND_WINDOW send budget.
        self._send_timestamps: collections.deque[float] = collections.deque()
        #: Edge-trigger flag so the quota-exhaustion warning logs once per entry, not per send.
        self._quota_warned: bool = False
        #: Set by mark_auth_failed() when a send fails with ReLoginRequiredError.
        #: Terminal for this object — recovery is a rebuild from a fresh login.
        self._auth_failed: bool = False
        #: Set by mark_unrecoverable_auth_failure() when the re-login circuit
        #: breaker trips.  Unlike _auth_failed, this is a permanent state — the
        #: transport's connect() must refuse to start a new receive loop, and
        #: is_usable stays False until something explicitly clears it.  The
        #: integration host (HA) is expected to initiate a reauth flow.
        self._unrecoverable_auth_failure: bool = False

    @abstractmethod
    async def _invoke(self, payload: bytes, iot_id: str) -> None:
        """Hand *payload* to the broker, with no quota accounting of any kind.

        The unmetered primitive that ``send``, ``send_heartbeat`` and
        :meth:`send_user` are each a different metering policy over.
        """

    async def send_user(self, payload: bytes, iot_id: str = "", firmware_version: str = "1.0.0.0") -> None:
        """Send a human-initiated payload, exempt from the self-imposed quota.

        Still counted by :meth:`record_send` — the budget has to reflect real traffic,
        or the next poll-cadence decision is made on a lie — and still refused while
        :attr:`is_cloud_banned`.

        BLE has no quota, so ``DeviceHandle._send_marked`` routes only cloud transports
        here and leaves BLE on the plain ``send()``.
        """
        self.raise_if_send_blocked(firmware_version, user_initiated=True)
        await self._invoke(payload, iot_id)
        self.record_send()

    def raise_if_send_blocked(self, firmware_version: str, *, user_initiated: bool = False) -> None:
        """Refuse a send that must not go out.

        The single place that turns :meth:`is_send_blocked` into an exception.  Both
        send verbs and ``DeviceHandle._send_marked``'s pre-flight call it, so they
        cannot drift apart on the predicate, on the firmware exemption, or on the
        message — which they had, three different ways.

        Always ``TransportRateLimitedError``: this is *us* declining to transmit, which
        is a different event from the cloud answering 429 mid-flight
        (``TooManyRequestsException``, raised by the send path itself).  Keeping them
        distinct is what lets ``DeviceHandle.send_raw`` arm the ban on exactly the
        latter and not re-arm it on every subsequent refusal.
        """
        if not self.is_send_blocked(firmware_version, user_initiated=user_initiated):
            return
        remaining = self.seconds_until_send_available()
        blocked_by = "the cloud" if self.is_cloud_banned else "its own send quota"
        msg = f"{type(self).__name__} rate-limited by {blocked_by} for {remaining:.0f}s more"
        raise TransportRateLimitedError(msg)

    @property
    def is_cloud_banned(self) -> bool:
        """True while a ban the *cloud* imposed is still running.

        Set by :meth:`set_rate_limited` when the broker answered 429, for a fixed
        ``_RATE_LIMIT_DURATION``.  Kept separate from the self-imposed quota because
        the two mean different things: this one is the server telling us to stop, so
        nothing — not even a user-initiated command — may push through it.
        """
        return time.monotonic() < self._rate_limited_until

    @property
    def is_quota_exhausted(self) -> bool:
        """True while the rolling window holds ``>= _SEND_LIMIT`` sends.

        Self-imposed: our own budget for staying clear of the cloud's 429 in the first
        place.  Computed live, so it releases the moment enough of the oldest sends age
        out of the window — no fixed wait once back under the limit.
        """
        return self.sends_in_window() >= self._SEND_LIMIT

    @property
    def is_rate_limited(self) -> bool:
        """Report whether a send is currently blocked, by either source.

        Callers gating an actual send should use :meth:`is_send_blocked` instead, which
        also applies the firmware exemption — devices on
        ``RATE_LIMIT_REMOVED_VERSION``+ firmware have migrated to the Mammotion MQTT
        broker and have no cloud send quota.
        """
        return self.is_cloud_banned or self.is_quota_exhausted

    @staticmethod
    def version_is_rate_limited(firmware_version: str) -> bool:
        """Report whether *firmware_version* predates the migration to the Mammotion MQTT broker.

        An unknown/unparseable version (e.g. "" before the first update-check frame)
        is treated as pre-migration so the rate-limit gate stays engaged rather than
        letting Version("") raise InvalidVersion out of the send path.
        """
        try:
            return Version(firmware_version) < RATE_LIMIT_REMOVED_VERSION
        except InvalidVersion:
            return True

    def is_send_blocked(self, firmware_version: str, *, user_initiated: bool = False) -> bool:
        """Return True when an outbound send must be refused for a device on *firmware_version*.

        The single source of truth for the rate-limit gate: combines the two block
        sources with the firmware exemption (``RATE_LIMIT_REMOVED_VERSION``).  Every
        send path — ``send()`` itself and any caller that pre-checks before touching
        the network — must use this predicate rather than reading the flags directly,
        so the gates can never disagree about whether a send is allowed.

        *user_initiated* marks a command a person is waiting on.  It spends past our
        own budget — the quota exists to pace *polling*, and a button press should not
        be starved by it — but never past a ban the server itself imposed.
        """
        if not self.version_is_rate_limited(firmware_version):
            return False
        return self.is_cloud_banned if user_initiated else self.is_rate_limited

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
        """False once an auth failure has been recorded on this transport.

        Recorded by :meth:`mark_auth_failed` or :meth:`mark_unrecoverable_auth_failure`.
        ``BLETransport`` has its own, unrelated notion of usable (BLEDevice presence,
        signal strength, connect cooldown) — which is why the base declares neither.
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

        Terminal for this object: recovery is a rebuild — a fresh caller-initiated
        login constructs new transports.
        """
        self._auth_failed = True

    def mark_unrecoverable_auth_failure(self) -> None:
        """Mark this transport as permanently failed — the re-login circuit breaker tripped.

        Concrete transports must check this in ``connect()`` and refuse to spawn
        a new receive loop while set; otherwise stale ``call_soon(connect())``
        callbacks (scheduled by an earlier ``_on_fatal_auth`` cycle) will keep
        restarting the loop after the breaker has decided to give up.
        """
        self._unrecoverable_auth_failure = True
