"""Immutable device snapshots, availability tracking, and state machine."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import logging
from typing import TYPE_CHECKING

from pymammotion.transport.base import TransportAvailability
from pymammotion.utility.constant.device_constant import WorkMode

if TYPE_CHECKING:
    from pymammotion.data.model.device import Device

_logger = logging.getLogger(__name__)

_WORK_MODE_TO_ACTIVITY: dict[int, str] = {
    WorkMode.MODE_READY: "ready",
    WorkMode.MODE_WORKING: "mowing",
    WorkMode.MODE_RETURNING: "returning",
    WorkMode.MODE_PAUSE: "paused",
    WorkMode.MODE_LOCK: "locked",
    WorkMode.MODE_NOT_ACTIVE: "unknown",
}


class DeviceConnectionState(Enum):
    """Overall device connection state, derived from transport availability."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class DeviceAvailability:
    """Tracks availability across MQTT and BLE transports.

    A device is available if EITHER transport can reach it.
    MQTT 'reported offline' (from thing/status events) only makes the device
    unavailable when BLE is also not reachable.
    """

    mqtt: TransportAvailability = TransportAvailability.UNKNOWN
    ble: TransportAvailability = TransportAvailability.UNKNOWN
    mqtt_reported_offline: bool = False

    @property
    def is_available(self) -> bool:
        """True if at least one transport can reach the device."""
        if self.ble == TransportAvailability.CONNECTED:
            return True
        return self.mqtt == TransportAvailability.CONNECTED and not self.mqtt_reported_offline

    @property
    def connection_state(self) -> DeviceConnectionState:
        """Derive DeviceConnectionState from transport availability."""
        if self.is_available:
            return DeviceConnectionState.CONNECTED
        if TransportAvailability.CONNECTING in (self.mqtt, self.ble):
            return DeviceConnectionState.CONNECTING
        return DeviceConnectionState.UNAVAILABLE


@dataclass(frozen=True)
class DeviceSnapshot:
    """Immutable point-in-time snapshot of key device state fields.

    The 'raw' field holds the full MowingDevice for fields not yet
    promoted to the snapshot API. Use sequence to detect missed updates.
    """

    sequence: int
    timestamp: datetime
    connection_state: DeviceConnectionState
    online: bool
    enabled: bool
    battery_level: int
    raw: Device  # full underlying device — use for fields not yet in snapshot


@dataclass(frozen=True)
class StateChangedEvent:
    """Emitted when device state changes between two snapshots."""

    device_id: str
    old: DeviceSnapshot
    new: DeviceSnapshot
    changed_fields: frozenset[str]


@dataclass(frozen=True)
class ConnectionStateChangedEvent:
    """Emitted when the device connection state transitions."""

    device_id: str
    old_state: DeviceConnectionState
    new_state: DeviceConnectionState
    reason: str | None = None


class DeviceStateMachine:
    """Manages device state as an append-only sequence of immutable snapshots.

    Each call to apply() returns a new snapshot with an incremented sequence
    number. Old snapshots remain valid — consumers can diff old vs new.
    """

    def __init__(self, device_id: str, initial: Device) -> None:
        """Initialise the state machine with a device ID and initial device."""
        self._device_id = device_id
        self._sequence = 0
        self._current = self._make_snapshot(initial, DeviceAvailability())

    @property
    def current(self) -> DeviceSnapshot:
        """The most recent immutable state snapshot."""
        return self._current

    def restore(self, device: Device) -> None:
        """Replace current state with a restored device (e.g. from HA storage)."""
        self._current = self._make_snapshot(device, DeviceAvailability())

    def apply(
        self,
        updated_device: Device,
        availability: DeviceAvailability,
    ) -> tuple[DeviceSnapshot, frozenset[str]]:
        """Apply an updated device and return (new_snapshot, changed_fields).

        changed_fields is the set of snapshot field names that changed value,
        excluding 'sequence', 'timestamp', and 'raw'.
        Returns (new_snapshot, frozenset()) if no observable fields changed.
        """
        self._sequence += 1
        new = self._make_snapshot(updated_device, availability)
        changed = self._diff(self._current, new)
        self._current = new
        return new, changed

    def _make_snapshot(
        self,
        device: Device,
        availability: DeviceAvailability | None = None,
    ) -> DeviceSnapshot:
        """Build a DeviceSnapshot from any Device subclass.

        Mower-specific fields (battery, activity, blade height) are extracted
        when present (``MowingDevice``); RTK and pool devices get neutral defaults.
        """
        if availability is None:
            availability = DeviceAvailability()

        report_data = getattr(device, "report_data", None)
        if report_data is not None:
            battery: int = report_data.dev.battery_val
        else:
            battery = 0

        return DeviceSnapshot(
            sequence=self._sequence,
            timestamp=datetime.now(tz=UTC),
            connection_state=availability.connection_state,
            online=device.online,
            enabled=device.enabled,
            battery_level=battery,
            raw=device,
        )

    def _diff(self, old: DeviceSnapshot, new: DeviceSnapshot) -> frozenset[str]:
        """Return the names of changed fields across snapshot + device model.

        Walks both the snapshot's promoted summary fields (``connection_state``,
        ``online``, ``enabled``, ``battery_level``) AND the top-level fields of
        ``raw`` (the underlying Device), so deep mutations such as
        ``report_data.dev.sys_status`` are detected.

        The state reducer shares unchanged sub-trees with the previous snapshot
        by identity, so the ``is`` check short-circuits the expensive recursive
        dataclass ``__eq__`` for most fields on every incoming message.
        """
        skip: frozenset[str] = frozenset({"sequence", "timestamp", "raw"})
        changed: set[str] = set()
        for f in dataclasses.fields(old):
            if f.name in skip:
                continue
            if getattr(old, f.name) != getattr(new, f.name):
                changed.add(f.name)
        if dataclasses.is_dataclass(old.raw) and dataclasses.is_dataclass(new.raw):
            for f in dataclasses.fields(old.raw):
                old_val = getattr(old.raw, f.name)
                new_val = getattr(new.raw, f.name)
                if old_val is not new_val and old_val != new_val:
                    changed.add(f.name)
        return frozenset(changed)
