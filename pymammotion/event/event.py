import asyncio
from collections.abc import Callable
from types import MethodType
from typing import Any
import weakref


class _StrongRef:
    """Strong-reference wrapper with the same call interface as weakref.ref.

    Used for lambdas and other non-method callables that have no other owner
    keeping them alive. Unlike weakref.ref, this prevents silent GC of the
    callable between registration and dispatch.
    """

    __slots__ = ("_obj",)

    def __init__(self, obj: Callable) -> None:
        self._obj = obj

    def __call__(self) -> Callable:
        return self._obj


class Event:
    """Async multicast event that dispatches to all registered handlers concurrently."""

    def __init__(self) -> None:
        self.__eventhandlers: list[weakref.ReferenceType | _StrongRef] = []

    def __iadd__(self, handler: Callable) -> "Event":
        if isinstance(handler, MethodType):
            # Instance method: weak reference so the Event doesn't prevent GC
            # of the owning object.
            ref: weakref.ReferenceType | _StrongRef = weakref.WeakMethod(handler)
        else:
            # Function, lambda, or partial: no owning object holds a reference,
            # so a weak ref would allow immediate GC. Store strongly instead.
            ref = _StrongRef(handler)
        self.__eventhandlers.append(ref)
        return self

    def __isub__(self, handler: Callable) -> "Event":
        # Use != rather than `is not`: bound methods are never the same object
        # across two attribute accesses (each creates a fresh MethodType), so
        # identity comparison would silently fail to remove them.  __eq__ on
        # MethodType compares the underlying function + instance, which is what
        # we want.  For _StrongRef callables the same object is stored, so both
        # == and `is` would work, but == is correct in all cases.
        self.__eventhandlers = [ref for ref in self.__eventhandlers if ref() != handler]
        return self

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        """Invoke all live registered handlers concurrently and purge any garbage-collected ones."""
        live_handlers = []
        for ref in self.__eventhandlers:
            func = ref()
            if func is not None:
                live_handlers.append(func(*args, **kwargs))
        await asyncio.gather(*live_handlers)

        # Clean up dead references
        self.__eventhandlers = [ref for ref in self.__eventhandlers if ref() is not None]

    def has_dead_handlers(self) -> bool:
        """Check if any handlers have been garbage collected."""
        return any(ref() is None for ref in self.__eventhandlers)


class MoveEvent:
    """Event source that fires when a movement command completes."""

    def __init__(self) -> None:
        self.OnMoveFinished = Event()

    async def MoveFinished(self) -> None:
        """Fire the OnMoveFinished event to notify subscribers that a movement command has completed."""
        # This function will be executed once blufi finishes after a movement command and will
        # raise an event
        await self.OnMoveFinished()

    def AddSubscribersForMoveFinishedEvent(self, objMethod) -> None:
        """Register a handler to be called when a movement command finishes."""
        self.OnMoveFinished += objMethod

    def RemoveSubscribersForMoveFinishedEvent(self, objMethod) -> None:
        """Unregister a previously registered move-finished handler."""
        self.OnMoveFinished -= objMethod


class BleNotificationEvent:
    """Event source that fires when BLE notification data is received from the device."""

    def __init__(self) -> None:
        self.OnBleNotification = Event()

    async def BleNotification(self, data: bytearray) -> None:
        """Fire the OnBleNotification event to deliver incoming BLE data to all subscribers."""
        # This function will be executed when data is received.
        await self.OnBleNotification(data)

    def AddSubscribersForBleNotificationEvent(self, objMethod) -> None:
        """Register a handler to be called when BLE notification data is received."""
        self.OnBleNotification += objMethod

    def RemoveSubscribersForBleNotificationEvent(self, objMethod) -> None:
        """Unregister a previously registered BLE notification handler."""
        self.OnBleNotification -= objMethod


class DataEvent:
    """Callbacks for data events."""

    def __init__(self) -> None:
        self.on_data_event = Event()

    async def data_event(self, data: Any) -> None:
        """Execute the data event callback."""
        # This function will be executed when data is received.
        if data:
            await self.on_data_event(data)
        else:
            await self.on_data_event()

    def add_subscribers(self, obj_method: Callable) -> None:
        """Add subscribers."""
        self.on_data_event += obj_method

    def remove_subscribers(self, obj_method: Callable) -> None:
        """Remove subscribers."""
        try:
            self.on_data_event -= obj_method
        except ValueError:
            """Subscription object no longer there."""
