"""The surface the per-transport activity loops need from their owning device.

``mqtt_loop``, ``ble_loop`` and ``dynamics_line_loop`` are free coroutines that
take the object driving them and own no state of their own.  That contract used to
be implicit, and the loops reached into ~22 private attributes to satisfy it; this
Protocol states it instead, so a change to :class:`~pymammotion.device.handle.DeviceHandle`
that breaks a loop is a type error rather than an ``AttributeError`` at runtime.

Lives in its own module for the same reason ``modes.py`` does: ``handle.py``
imports the loops, so a loop cannot import ``handle.py`` at runtime.
"""

# D102: every member below is a one-line signature under a section comment that
# already says what the group is for; per-stub docstrings would only restate them.
# ruff: noqa: D102

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pymammotion.data.model.device import MowingDevice
    from pymammotion.device.modes import _DeviceMode
    from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
    from pymammotion.messaging.saga import Saga
    from pymammotion.proto import RptAct
    from pymammotion.state.device_state import DeviceAvailability
    from pymammotion.transport.base import Transport, TransportType


class _QueueView(Protocol):
    """The one queue field the loops consult before sending."""

    @property
    def is_saga_active(self) -> bool: ...


class _SnapshotView(Protocol):
    """The one snapshot field the dynamics-line loop reads."""

    @property
    def raw(self) -> MowingDevice: ...


class LoopHost(Protocol):
    """What an activity loop may use on the device it drives.

    Deliberately narrow: everything here is read or called by at least one of the
    three loops (verified by ``tests/unit/device/test_loop_host.py``).  Adding a
    member means a loop grew a new dependency on its host.
    """

    # --- identity, for logging and command construction
    @property
    def device_name(self) -> str: ...
    @property
    def iot_id(self) -> str: ...
    @property
    def firmware_version(self) -> str: ...
    @property
    def commands(self) -> MammotionCommand: ...

    # --- lifecycle and the wake signal that interrupts a long sleep
    @property
    def is_stopping(self) -> bool: ...
    def record_user_command(self) -> None: ...
    async def sleep_or_rearm(self, seconds: float) -> bool: ...

    # --- what may be sent right now
    @property
    def has_any_transport(self) -> bool: ...
    @property
    def has_usable_transport(self) -> bool: ...
    @property
    def availability(self) -> DeviceAvailability: ...
    def get_transport(self, transport_type: TransportType) -> Transport | None: ...
    def cloud_transport(self) -> TransportType | None: ...

    # --- cadence inputs
    def cadence_mode(self) -> _DeviceMode: ...
    def in_no_request_mode(self) -> bool: ...
    @property
    def last_report_at(self) -> float: ...
    @property
    def last_transport_activity(self) -> float: ...

    # --- BLE continuous-stream bookkeeping (read *and* written by ble_loop)
    ble_stream_active: bool
    ble_heartbeat_failures: int

    # --- the sends themselves
    @property
    def queue(self) -> _QueueView: ...
    @property
    def snapshot(self) -> _SnapshotView: ...
    async def send_raw(self, payload: bytes) -> None: ...
    async def send_one_shot_report(self) -> None: ...
    async def send_report_stream_keep(self) -> None: ...
    async def enqueue_ble_stream_command(self, act: RptAct, count: int) -> None: ...
    async def enqueue_saga(self, saga: Saga, *args: Any, **kwargs: Any) -> Any: ...
