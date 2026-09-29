"""Cloud remote drive ("FPV control"): token-authorised joystick frames sent over IoT only.

A port of the app's ``RemoteDriveControllerImpl`` (APK 2.3.20.30).  ``docs/remote_drive.md``
describes the protocol, the phases and the fault mapping.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum, auto
import logging
import time
from typing import TYPE_CHECKING, Protocol

from pymammotion.aliyun.exceptions import GatewayTimeoutException
from pymammotion.http.model.fpv_control import FpvControl, FpvControlOutcome, fpv_control_outcome
from pymammotion.proto import LubaMsg
from pymammotion.transport.base import EventBus, NoTransportAvailableError, Subscription

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.device.handle import DeviceHandle
    from pymammotion.http.http import MammotionHTTP
    from pymammotion.http.model.http import Response
    from pymammotion.proto import DrvSessionCtrlAck

_logger = logging.getLogger(__name__)

KEEP_ALIVE_INTERVAL_S = 3.0
SAFETY_NOTICE_TIMEOUT_S = 180.0
MIN_FRAME_INTERVAL_MS = 150
SEQ_RESET_GAP_MS = 1000
INVOKE_TIMEOUT_S = 1.0
INVOKE_TIMEOUTS_TO_FAULT = 3
DEFAULT_IDLE_TIMEOUT_S = 10
TOKEN_REFRESH_LEAD_S = 60
LATENCY_WARN_OFFSET_MS = 500
APPROACH_FENCE_DISTANCE_M = 5.0


class RemoteDrivePhase(StrEnum):
    """Where a session is; ``EXITING`` covers the forced stop and token release."""

    IDLE = auto()
    REQUESTING_TOKEN = auto()
    SAFETY_NOTICE = auto()
    ACTIVE = auto()
    EXITING = auto()


class RemoteDriveEventKind(StrEnum):
    """What a session reports to its subscribers (the app's ``FaultType`` plus its exit toasts).

    ``APPROACH_FENCE`` and ``LATENCY_HIGH`` leave the session running; every other kind
    means it has ended and released its token.
    """

    TOKEN_UNAVAILABLE = auto()
    OCCUPIED_BY_OTHER = auto()
    NETWORK_POOR = auto()
    TOKEN_EXPIRED = auto()
    OUT_OF_FENCE = auto()
    BLE_PREEMPT = auto()
    NO_LOC_MILEAGE_EXHAUSTED = auto()
    ENV_NOT_READY = auto()
    SEND_FAILED = auto()
    APPROACH_FENCE = auto()
    LATENCY_HIGH = auto()
    IDLE_TIMEOUT = auto()
    SAFETY_NOTICE_TIMEOUT = auto()
    VIDEO_UNAVAILABLE = auto()


@dataclass(frozen=True)
class RemoteDriveEvent:
    """One session event; *detail* is the server/device code or account the app would show."""

    kind: RemoteDriveEventKind
    detail: str | None = None
    error: Exception | None = None


class RemoteDriveError(RuntimeError):
    """A session call made in a state that cannot accept it."""


class DriveTimer(Protocol):
    """A scheduled callback that can be cancelled before it fires."""

    def cancel(self) -> None:
        """Stop the callback from running."""


class DriveClock(Protocol):
    """Time source and scheduler, injected so tests move time by hand."""

    def now_ms(self) -> int:
        """Epoch milliseconds that never step backwards (the app's ``MonotonicClock.now``)."""

    def call_later(self, delay: float, callback: Callable[[], Awaitable[None]]) -> DriveTimer:
        """Run *callback* after *delay* seconds."""


class DriveSend(Protocol):
    """The cloud send a session is given."""

    async def __call__(self, payload: bytes, *, timeout: float) -> None:
        """Send *payload*, bounding each network attempt by *timeout* (``TimeoutError``).

        A credential refresh between attempts is not bounded: cancelling one mid-flight can
        strand a refresh token the server has already rotated.
        """


class FpvTokenSource(Protocol):
    """Where a session gets its control token."""

    async def request(self) -> Response[FpvControl]:
        """Ask for a new control token."""

    async def refresh(self, token: str) -> Response[FpvControl]:
        """Renew *token*."""


class LoopDriveClock:
    """The production :class:`DriveClock`: the event loop's timers and an epoch-anchored monotonic clock."""

    def __init__(self) -> None:
        """Anchor the monotonic clock to the epoch once, as ``MonotonicClock`` does."""
        self._epoch_offset_ms = time.time() * 1000 - time.monotonic() * 1000
        self._tasks: set[asyncio.Task[None]] = set()

    def now_ms(self) -> int:
        """Epoch milliseconds from the monotonic clock."""
        return int(time.monotonic() * 1000 + self._epoch_offset_ms)

    def call_later(self, delay: float, callback: Callable[[], Awaitable[None]]) -> DriveTimer:
        """Schedule *callback* as a task after *delay* seconds."""
        return asyncio.get_running_loop().call_later(delay, self._spawn, callback)

    def _spawn(self, callback: Callable[[], Awaitable[None]]) -> None:
        task: asyncio.Task[None] = asyncio.ensure_future(callback())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


class HttpTokenSource:
    """An :class:`FpvTokenSource` over an account's HTTP login, looked up per call so a re-login is picked up."""

    def __init__(self, http: Callable[[], MammotionHTTP | None], iot_id: str) -> None:
        """Bind the login lookup and the device's iot id."""
        self._http = http
        self._iot_id = iot_id

    async def request(self) -> Response[FpvControl]:
        """Ask for a new control token."""
        return await self._login().request_fpv_control_token(self._iot_id)

    async def refresh(self, token: str) -> Response[FpvControl]:
        """Renew *token*."""
        return await self._login().refresh_fpv_control_token(self._iot_id, token)

    def _login(self) -> MammotionHTTP:
        if (http := self._http()) is None:
            msg = "remote drive needs a cloud login"
            raise NoTransportAvailableError(msg)
        return http


def mask_account(account: str | None) -> str | None:
    """Mask a numeric account id the way the app does before showing it (``maskNumericAccountId``)."""
    if not (value := (account or "").strip()):
        return None
    if not value.isdigit() or len(value) < 5:
        return value
    return value[:2] + "*" * (len(value) - 5) + value[-3:]


_ACK_OK = frozenset({0, 3, 5})
_ACK_FAULTS: dict[int, RemoteDriveEventKind] = {
    4: RemoteDriveEventKind.NETWORK_POOR,
    6: RemoteDriveEventKind.TOKEN_EXPIRED,
    7: RemoteDriveEventKind.TOKEN_EXPIRED,
    8: RemoteDriveEventKind.OUT_OF_FENCE,
    9: RemoteDriveEventKind.BLE_PREEMPT,
    10: RemoteDriveEventKind.NO_LOC_MILEAGE_EXHAUSTED,
    11: RemoteDriveEventKind.NETWORK_POOR,
}


def _unavailable_detail(response: Response[FpvControl]) -> str | None:
    if response.code != 0:
        return str(response.code)
    if response.data is None or response.data.device_result is None:
        return None
    return str(response.data.device_result)


@dataclass(frozen=True)
class _Frame:
    linear: int
    angular: int
    await_ack: bool
    fixed_seq: int | None


_NO_FRAME = _Frame(0, 0, await_ack=False, fixed_seq=None)


class RemoteDriveSession:
    """One device's cloud remote-drive session.

    ``start()`` gets a control token and enters the safety notice, sending a zero-speed
    keep-alive every 3 s; ``confirm()`` (the user accepted the notice) makes it ACTIVE;
    ``drive(linear, angular)`` feeds joystick input in the device's wire units;
    ``stop()`` halts the mower and releases the token.  Faults and exits arrive on
    :meth:`subscribe`.  Every frame goes over the cloud on the caller-supplied *send*.

    The app refuses to start (and ends a running session) while its video has no frame;
    with ``require_video`` the same gate applies to :meth:`set_video_ready`.
    """

    def __init__(
        self,
        handle: DeviceHandle,
        *,
        tokens: FpvTokenSource,
        send: DriveSend,
        clock: DriveClock | None = None,
        require_video: bool = False,
        invoke_timeout: float = INVOKE_TIMEOUT_S,
    ) -> None:
        """Bind the session to *handle*; nothing is sent until :meth:`start`."""
        self._handle = handle
        self._commands = handle.commands
        self._tokens = tokens
        self._send = send
        self._clock: DriveClock = clock if clock is not None else LoopDriveClock()
        self.require_video = require_video
        self._invoke_timeout = invoke_timeout
        self._events: EventBus[RemoteDriveEvent] = EventBus()
        self._phase = RemoteDrivePhase.IDLE
        self._video_ready = False
        self._grant: FpvControl | None = None
        self._start_attempt = 0
        self._subscription: Subscription | None = None
        self._keep_alive_timer: DriveTimer | None = None
        self._safety_timer: DriveTimer | None = None
        self._refresh_timer: DriveTimer | None = None
        self._flush_timer: DriveTimer | None = None
        self._idle_timer: DriveTimer | None = None
        self._oneshots: set[DriveTimer] = set()
        self._refreshing = False
        self._idle_active = False
        self._idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S
        self._latency_warn_ms: int | None = None
        self._latency_warned = False
        self._fence_latched = False
        self._fence_paused = False
        self._next_seq = 0
        self._vehicle_ts = 0
        self._last_send_at = 0
        self._awaiting = False
        self._in_flight = -1
        self._pending: tuple[int, int] | None = None
        self._last_sent = _NO_FRAME
        self._timeouts = 0

    @property
    def phase(self) -> RemoteDrivePhase:
        """The session's current phase."""
        return self._phase

    @property
    def grant(self) -> FpvControl | None:
        """The live token grant (``fps_4g`` is the app's 4G video rate for the session), or ``None``."""
        return self._grant

    @property
    def video_ready(self) -> bool:
        """What the host last reported through :meth:`set_video_ready`."""
        return self._video_ready

    @property
    def fence_paused(self) -> bool:
        """True while input is dropped after an approach-fence stop, until :meth:`acknowledge_fence_warning`."""
        return self._fence_paused

    def subscribe(self, handler: Callable[[RemoteDriveEvent], Awaitable[None]]) -> Subscription:
        """Receive every :class:`RemoteDriveEvent` the session emits."""
        return self._events.subscribe(handler)

    async def start(self) -> bool:
        """Request a control token and enter the safety notice.

        Returns False when the server refused the token (a ``TOKEN_UNAVAILABLE`` or
        ``OCCUPIED_BY_OTHER`` event says why).

        Raises:
            RemoteDriveError: the session is already running, or video is required and not ready.
            NoTransportAvailableError: the device has no usable cloud transport.  Over BLE the
                app drives with the legacy ``DrvMotionCtrl`` instead.
            UnauthorizedExceptionError: the login was rejected by the token endpoint.

        """
        if self._phase is not RemoteDrivePhase.IDLE:
            msg = f"remote drive for '{self._handle.device_name}' is already {self._phase.value}"
            raise RemoteDriveError(msg)
        if self.require_video and not self._video_ready:
            msg = f"remote drive for '{self._handle.device_name}' needs a video frame first"
            raise RemoteDriveError(msg)
        self._handle.usable_cloud_transport(user_initiated=True)
        self._commands = self._handle.commands
        self._phase = RemoteDrivePhase.REQUESTING_TOKEN
        # A stop() and a new start() may overlap this request; only the latest attempt may act on its answer.
        self._start_attempt += 1
        attempt = self._start_attempt
        try:
            response = await self._tokens.request()
        except BaseException:
            if self._phase is RemoteDrivePhase.REQUESTING_TOKEN and attempt == self._start_attempt:
                self._phase = RemoteDrivePhase.IDLE
            raise
        if self._phase is not RemoteDrivePhase.REQUESTING_TOKEN or attempt != self._start_attempt:
            if fpv_control_outcome(response) is FpvControlOutcome.GRANTED and response.data is not None:
                await self._notify_exit(response.data.token)
            return False
        match fpv_control_outcome(response):
            case FpvControlOutcome.GRANTED if response.data is not None:
                self._apply_grant(response.data)
                self._reset_ctrl()
                self._phase = RemoteDrivePhase.SAFETY_NOTICE
                self._subscription = self._handle.broker.subscribe_unsolicited(self._on_message)
                self._safety_timer = self._clock.call_later(SAFETY_NOTICE_TIMEOUT_S, self._on_safety_timeout)
                self._schedule_refresh()
                await self._keep_alive()
                return True
            case FpvControlOutcome.OCCUPIED:
                self._phase = RemoteDrivePhase.IDLE
                holder = response.data.preempt_user if response.data is not None else None
                await self._emit(RemoteDriveEventKind.OCCUPIED_BY_OTHER, holder)
                return False
            case _:
                self._phase = RemoteDrivePhase.IDLE
                await self._emit(RemoteDriveEventKind.TOKEN_UNAVAILABLE, _unavailable_detail(response))
                return False

    async def confirm(self) -> None:
        """Leave the safety notice and accept input (the user confirmed the notice).

        Raises:
            RemoteDriveError: the session is not showing the safety notice, or video is required and not ready.

        """
        if self._phase is not RemoteDrivePhase.SAFETY_NOTICE:
            msg = f"remote drive for '{self._handle.device_name}' is {self._phase.value}, not awaiting confirmation"
            raise RemoteDriveError(msg)
        if self.require_video and not self._video_ready:
            msg = f"remote drive for '{self._handle.device_name}' needs a video frame first"
            raise RemoteDriveError(msg)
        self._cancel(self._keep_alive_timer, self._safety_timer)
        self._keep_alive_timer = self._safety_timer = None
        self._phase = RemoteDrivePhase.ACTIVE
        self._start_idle()

    async def drive(self, linear: int, angular: int) -> None:
        """Feed joystick input in wire units; (0, 0) means hands off and starts the idle countdown.

        Ignored outside ACTIVE and while :attr:`fence_paused`.  A negative *linear* is sent as 0:
        the app does not reverse over the cloud.
        """
        if self._phase is not RemoteDrivePhase.ACTIVE or self._fence_paused:
            _logger.debug("remote drive '%s': input ignored in %s", self._handle.device_name, self._phase.value)
            return
        linear = max(linear, 0)
        if linear or angular:
            self._clear_idle()
            await self._enqueue(linear, angular)
            return
        await self._enqueue(0, 0)
        self._start_idle()

    def acknowledge_fence_warning(self) -> None:
        """Resume input after an ``APPROACH_FENCE`` stop."""
        if self._fence_paused:
            self._fence_paused = False
            self._pending = None

    async def set_video_ready(self, *, ready: bool) -> None:
        """Report whether the host's video has a frame; losing it ends a session that requires it."""
        self._video_ready = ready
        if not ready and self.require_video and self._phase in _LIVE:
            await self._end(RemoteDriveEventKind.VIDEO_UNAVAILABLE)

    async def stop(self) -> None:
        """Halt the mower (when ACTIVE) and release the token.  Never raises; idempotent."""
        if self._phase in (RemoteDrivePhase.IDLE, RemoteDrivePhase.EXITING):
            return
        await self._end(None)

    async def _end(
        self, kind: RemoteDriveEventKind | None, detail: str | None = None, error: Exception | None = None
    ) -> None:
        force_stop = self._phase is RemoteDrivePhase.ACTIVE
        self._phase = RemoteDrivePhase.EXITING
        self._cancel_idle()
        await self._finish(kind, detail, error, force_stop=force_stop)

    def _fail(self, kind: RemoteDriveEventKind, detail: str | None = None, error: Exception | None = None) -> None:
        """End the session from a context that must not send inline (an ack handler, a send's own error)."""
        if self._phase not in _LIVE:
            return
        force_stop = self._phase is RemoteDrivePhase.ACTIVE
        self._phase = RemoteDrivePhase.EXITING
        self._cancel_idle()
        self._oneshot(lambda: self._finish(kind, detail, error, force_stop=force_stop))

    async def _finish(
        self, kind: RemoteDriveEventKind | None, detail: str | None, error: Exception | None, *, force_stop: bool
    ) -> None:
        if force_stop:
            await self._force_stop()
        await self._release()
        if kind is not None:
            await self._emit(kind, detail, error)

    async def _release(self) -> None:
        self._cancel(
            self._keep_alive_timer, self._safety_timer, self._refresh_timer, self._flush_timer, self._idle_timer
        )
        self._cancel(*self._oneshots)
        self._oneshots.clear()
        self._keep_alive_timer = self._safety_timer = self._refresh_timer = self._flush_timer = None
        self._idle_timer = None
        if self._subscription is not None:
            self._subscription.cancel()
            self._subscription = None
        if self._grant is not None:
            await self._notify_exit(self._grant.token)
        self._grant = None
        self._latency_warn_ms = None
        self._latency_warned = False
        self._refreshing = False
        self._idle_active = False
        self._idle_timeout_s = DEFAULT_IDLE_TIMEOUT_S
        self._fence_latched = self._fence_paused = False
        self._reset_ctrl()
        self._phase = RemoteDrivePhase.IDLE

    async def _notify_exit(self, token: str | None) -> None:
        if not token:
            return
        try:
            await self._send(self._commands.session_exit_notify(token), timeout=self._invoke_timeout)
        except Exception:  # the server expires the token anyway
            _logger.debug("remote drive '%s': exit notify failed", self._handle.device_name, exc_info=True)

    async def _emit(
        self, kind: RemoteDriveEventKind, detail: str | None = None, error: Exception | None = None
    ) -> None:
        _logger.debug("remote drive '%s': %s %s", self._handle.device_name, kind.value, detail or "")
        await self._events.emit(RemoteDriveEvent(kind, detail, error))

    def _apply_grant(self, control: FpvControl) -> None:
        self._grant = control
        self._idle_timeout_s = (
            control.timeout_exit if control.timeout_exit and control.timeout_exit > 0 else DEFAULT_IDLE_TIMEOUT_S
        )
        threshold = control.latency_threshold
        self._latency_warn_ms = max(threshold - LATENCY_WARN_OFFSET_MS, 0) if threshold and threshold > 0 else None

    def _schedule_refresh(self) -> None:
        self._cancel(self._refresh_timer)
        self._refresh_timer = None
        if self._grant is not None and (expire_in := self._grant.expire_in) and expire_in > 0:
            delay = max(expire_in - TOKEN_REFRESH_LEAD_S, 0)
            self._refresh_timer = self._clock.call_later(delay, self._refresh)

    async def _refresh(self) -> None:
        self._refresh_timer = None
        if self._phase not in _DRIVING or self._grant is None or not (token := self._grant.token) or self._refreshing:
            return
        self._refreshing = True
        try:
            response = await self._tokens.refresh(token)
        except Exception as exc:  # noqa: BLE001 — the app ends the session on any renewal failure
            self._refreshing = False
            self._fail(RemoteDriveEventKind.TOKEN_EXPIRED, error=exc)
            return
        self._refreshing = False
        if self._phase not in _DRIVING:
            return
        match fpv_control_outcome(response):
            case FpvControlOutcome.GRANTED if response.data is not None:
                self._apply_grant(response.data)
                self._schedule_refresh()
            case FpvControlOutcome.OCCUPIED:
                holder = response.data.preempt_user if response.data is not None else None
                self._fail(RemoteDriveEventKind.BLE_PREEMPT, mask_account(holder))
            case _:
                self._fail(RemoteDriveEventKind.TOKEN_EXPIRED, _unavailable_detail(response))

    async def _on_safety_timeout(self) -> None:
        self._safety_timer = None
        if self._phase is RemoteDrivePhase.SAFETY_NOTICE:
            await self._end(RemoteDriveEventKind.SAFETY_NOTICE_TIMEOUT)

    async def _keep_alive(self) -> None:
        self._keep_alive_timer = None
        if self._phase is not RemoteDrivePhase.SAFETY_NOTICE:
            return
        await self._send_frame(0, 0, await_ack=False, fixed_seq=0)
        if self._phase is RemoteDrivePhase.SAFETY_NOTICE:
            self._keep_alive_timer = self._clock.call_later(KEEP_ALIVE_INTERVAL_S, self._keep_alive)

    def _start_idle(self) -> None:
        if self._phase is RemoteDrivePhase.ACTIVE and not self._idle_active:
            self._idle_active = True
            self._idle_timer = self._clock.call_later(self._idle_timeout_s, self._on_idle_timeout)

    def _clear_idle(self) -> None:
        was_counting = self._idle_active
        self._cancel_idle()
        if was_counting:
            self._reset_ctrl()

    def _cancel_idle(self) -> None:
        self._cancel(self._idle_timer)
        self._idle_timer = None
        self._idle_active = False

    async def _on_idle_timeout(self) -> None:
        self._idle_timer = None
        if self._phase is RemoteDrivePhase.ACTIVE and self._idle_active:
            await self._end(RemoteDriveEventKind.IDLE_TIMEOUT)

    def _reset_ctrl(self) -> None:
        self._cancel(self._flush_timer)
        self._flush_timer = None
        self._reset_seq()
        self._awaiting = False
        self._in_flight = -1
        self._pending = None
        self._last_sent = _NO_FRAME
        self._timeouts = 0

    def _reset_seq(self) -> None:
        self._next_seq = 0
        self._vehicle_ts = 0
        self._last_send_at = 0

    def _halt_pending(self) -> None:
        self._pending = None
        self._awaiting = False
        self._in_flight = -1
        self._cancel(self._flush_timer)
        self._flush_timer = None

    async def _enqueue(self, linear: int, angular: int) -> None:
        if self._awaiting:
            self._pending = (linear, angular)
            return
        if (remaining := self._remaining_interval_ms()) <= 0:
            # Supersedes a hold-repeat the last ack queued but whose flush has not run yet.
            self._pending = None
            self._cancel(self._flush_timer)
            self._flush_timer = None
            self._reset_seq_after_gap()
            await self._send_frame(linear, angular, await_ack=True)
            return
        self._pending = (linear, angular)
        self._schedule_flush(remaining / 1000)

    def _remaining_interval_ms(self) -> int:
        if self._last_send_at <= 0:
            return 0
        return max(self._last_send_at + MIN_FRAME_INTERVAL_MS - self._clock.now_ms(), 0)

    def _reset_seq_after_gap(self) -> None:
        if self._last_send_at > 0 and self._clock.now_ms() - self._last_send_at >= SEQ_RESET_GAP_MS:
            self._reset_seq()

    def _schedule_flush(self, delay: float) -> None:
        self._cancel(self._flush_timer)
        self._flush_timer = self._clock.call_later(delay, self._flush)

    async def _flush(self) -> None:
        self._flush_timer = None
        if self._phase is not RemoteDrivePhase.ACTIVE or self._fence_paused:
            self._pending = None
            return
        if (pending := self._pending) is not None and not self._awaiting:
            self._pending = None
            self._reset_seq_after_gap()
            await self._send_frame(*pending, await_ack=True)

    async def _force_stop(self) -> None:
        self._halt_pending()
        await self._send_frame(0, 0, await_ack=False)

    async def _send_frame(self, linear: int, angular: int, *, await_ack: bool, fixed_seq: int | None = None) -> None:
        if self._grant is None or not (token := self._grant.token):
            return
        if fixed_seq is None:
            seq = self._next_seq
            self._next_seq = (seq + 1) & 0xFFFFFFFF
        else:
            seq = fixed_seq
        now = self._clock.now_ms()
        if fixed_seq is None:
            self._last_send_at = now
        self._last_sent = _Frame(linear, angular, await_ack=await_ack, fixed_seq=fixed_seq)
        if await_ack:
            self._awaiting = True
            self._in_flight = seq
        payload = self._commands.session_ctrl(
            ctrl_seq=seq,
            linear_speed=linear,
            angular_speed=angular,
            app_send_ts_ms=now,
            vehicle_send_ts_ms=self._vehicle_ts,
            token=token,
        )
        await self._invoke(payload)

    async def _invoke(self, payload: bytes) -> None:
        try:
            await self._send(payload, timeout=self._invoke_timeout)
        except (TimeoutError, GatewayTimeoutException):
            self._on_invoke_timeout()
        except Exception as exc:  # noqa: BLE001 — any refusal ends the session; the event carries it
            _logger.warning("remote drive '%s': send failed: %s", self._handle.device_name, exc)
            self._fail(RemoteDriveEventKind.SEND_FAILED, error=exc)
        else:
            self._timeouts = 0

    def _on_invoke_timeout(self) -> None:
        if self._phase not in _DRIVING:
            return
        self._timeouts += 1
        if self._timeouts < INVOKE_TIMEOUTS_TO_FAULT:
            self._oneshot(self._resend_after_timeout)
            return
        self._timeouts = 0
        self._fail(RemoteDriveEventKind.NETWORK_POOR)

    async def _resend_after_timeout(self) -> None:
        if self._phase not in _DRIVING:
            return
        self._reset_seq()
        self._awaiting = False
        self._in_flight = -1
        if (pending := self._pending) is not None:
            self._pending = None
            await self._send_frame(*pending, await_ack=True)
            return
        last = self._last_sent
        await self._send_frame(last.linear, last.angular, await_ack=last.await_ack, fixed_seq=last.fixed_seq)

    async def _on_message(self, message: object) -> None:
        if not isinstance(message, LubaMsg) or (driver := message.driver) is None:
            return
        if (ack := driver.toapp_session_ctrl_ack) is not None:
            self._on_ack(ack)
        elif (notice := driver.toapp_session_exit_nfty) is not None:
            _logger.debug("remote drive '%s': device exit notice %s", self._handle.device_name, notice)

    def _on_ack(self, ack: DrvSessionCtrlAck) -> None:
        self._vehicle_ts = ack.vehicle_send_ts_ms
        if not (self._awaiting and ack.ctrl_seq == self._in_flight):
            _logger.debug("remote drive '%s': ack %d is not in flight", self._handle.device_name, ack.ctrl_seq)
            return
        self._awaiting = False
        self._in_flight = -1
        self._timeouts = 0
        now = self._clock.now_ms()
        sent_at = ack.app_send_ts_ms if ack.app_send_ts_ms > 0 else self._last_send_at
        rtt = max(now - sent_at, 0) if sent_at > 0 else 0
        if (result := int(ack.result)) in _ACK_OK:
            self._after_ack(rtt)
            self._check_fence(ack.fence_exceed_distance, localization_valid=ack.localization_valid)
            self._check_latency(ack.measured_delay_ms)
            return
        match _ACK_FAULTS.get(result):
            case None:
                self._pending = None
                self._fail(RemoteDriveEventKind.ENV_NOT_READY, str(result))
            case RemoteDriveEventKind.TOKEN_EXPIRED:
                self._fail(RemoteDriveEventKind.TOKEN_EXPIRED, str(result))
            case RemoteDriveEventKind.BLE_PREEMPT:
                account = str(ack.preempt_account) if ack.preempt_account else None
                self._fail(RemoteDriveEventKind.BLE_PREEMPT, mask_account(account))
            case kind:
                self._fail(kind)

    def _after_ack(self, rtt_ms: int) -> None:
        """Queue the next frame 150 ms after the last send, repeating a held non-zero speed."""
        if self._phase is not RemoteDrivePhase.ACTIVE or self._fence_paused:
            self._pending = None
            return
        last = self._last_sent
        if self._pending is None and (last.linear or last.angular):
            self._pending = (last.linear, last.angular)
        if self._pending is not None and not self._awaiting:
            self._schedule_flush(max(MIN_FRAME_INTERVAL_MS - rtt_ms, 0) / 1000)

    def _check_fence(self, distance: float, *, localization_valid: bool) -> None:
        if not localization_valid:
            return
        if distance < APPROACH_FENCE_DISTANCE_M:
            self._fence_latched = self._fence_paused = False
            return
        if self._phase is not RemoteDrivePhase.ACTIVE or self._fence_latched:
            return
        self._fence_latched = self._fence_paused = True
        self._clear_idle()
        self._halt_pending()
        self._oneshot(self._fence_stop)

    async def _fence_stop(self) -> None:
        # _check_fence already cleared the queue; input the host sent after an early acknowledge must survive.
        await self._send_frame(0, 0, await_ack=False)
        await self._emit(RemoteDriveEventKind.APPROACH_FENCE)

    def _check_latency(self, measured_ms: int) -> None:
        if self._phase is not RemoteDrivePhase.ACTIVE or self._latency_warned:
            return
        if (threshold := self._latency_warn_ms) is None or measured_ms < threshold:
            return
        self._latency_warned = True
        self._oneshot(lambda: self._emit(RemoteDriveEventKind.LATENCY_HIGH, str(measured_ms)))

    def _oneshot(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Run *callback* on the next clock turn rather than inline (never send from the broker's handler)."""
        timer: DriveTimer | None = None

        async def _run() -> None:
            self._oneshots.discard(timer)  # type: ignore[arg-type]
            await callback()

        timer = self._clock.call_later(0, _run)
        self._oneshots.add(timer)

    @staticmethod
    def _cancel(*timers: DriveTimer | None) -> None:
        for timer in timers:
            if timer is not None:
                timer.cancel()


_LIVE = frozenset({RemoteDrivePhase.REQUESTING_TOKEN, RemoteDrivePhase.SAFETY_NOTICE, RemoteDrivePhase.ACTIVE})
_DRIVING = frozenset({RemoteDrivePhase.SAFETY_NOTICE, RemoteDrivePhase.ACTIVE})
