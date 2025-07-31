import asyncio
from collections.abc import Callable
from types import MethodType
from typing import Any
import weakref


class Event:
    def __init__(self) -> None:
        self.__eventhandlers: list[weakref.ReferenceType] = []

    def __iadd__(self, handler: Callable) -> "Event":
        if isinstance(handler, MethodType):
            # Instance method, use WeakMethod
            ref = weakref.WeakMethod(handler)
        else:
            # Function or static method, use weakref.ref
            ref = weakref.ref(handler)
        self.__eventhandlers.append(ref)
        return self

    def __isub__(self, handler: Callable) -> "Event":
        self.__eventhandlers = [ref for ref in self.__eventhandlers if ref() is not handler]
        return self

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
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
    def __init__(self) -> None:
        self.OnMoveFinished = Event()

    async def MoveFinished(self) -> None:
        # This function will be executed once blufi finishes after a movement command and will
        # raise an event
        await self.OnMoveFinished()

    def AddSubscribersForMoveFinishedEvent(self, objMethod) -> None:
        self.OnMoveFinished += objMethod

    def RemoveSubscribersForMoveFinishedEvent(self, objMethod) -> None:
        self.OnMoveFinished -= objMethod


class BleNotificationEvent:
    def __init__(self) -> None:
        self.OnBleNotification = Event()

    async def BleNotification(self, data: bytearray) -> None:
        # This function will be executed when data is received.
        await self.OnBleNotification(data)

    def AddSubscribersForBleNotificationEvent(self, objMethod) -> None:
        self.OnBleNotification += objMethod

    def RemoveSubscribersForBleNotificationEvent(self, objMethod) -> None:
        self.OnBleNotification -= objMethod


class DataEvent:
    """Callbacks for data events."""

    def __init__(self) -> None:
        self.on_data_event = Event()

    async def data_event(self, data: Any) -> None:
        # This function will be executed when data is received.
        if data:
            await self.on_data_event(data)
        else:
            await self.on_data_event()

    def add_subscribers(self, obj_method) -> None:
        self.on_data_event += obj_method

    def remove_subscribers(self, obj_method) -> None:
        try:
            self.on_data_event -= obj_method
        except ValueError:
            """Subscription object no longer there."""
