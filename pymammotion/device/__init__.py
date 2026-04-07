"""Device handle and registry for PyMammotion."""

from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.device.state_reducer import MowerStateReducer, PoolStateReducer, StateReducer, get_state_reducer

__all__ = [
    "DeviceHandle",
    "DeviceRegistry",
    "MowerStateReducer",
    "PoolStateReducer",
    "StateReducer",
    "get_state_reducer",
]
