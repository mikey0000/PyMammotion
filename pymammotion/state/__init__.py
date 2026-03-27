"""Device state management — immutable snapshots and availability tracking."""

from __future__ import annotations

from pymammotion.state.device_state import (
    ConnectionStateChangedEvent,
    DeviceAvailability,
    DeviceConnectionState,
    DeviceSnapshot,
    DeviceStateMachine,
    StateChangedEvent,
    TransportAvailability,
)

__all__ = [
    "ConnectionStateChangedEvent",
    "DeviceAvailability",
    "DeviceConnectionState",
    "DeviceSnapshot",
    "DeviceStateMachine",
    "StateChangedEvent",
    "TransportAvailability",
]
