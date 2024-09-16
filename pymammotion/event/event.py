import asyncio
from typing import Any


class Event:
    def __init__(self) -> None:
        self.__eventhandlers = []

    def __iadd__(self, handler):
        self.__eventhandlers.append(handler)
        return self

    def __isub__(self, handler):
        self.__eventhandlers.remove(handler)
        return self

    async def __call__(self, *args, **kwargs) -> None:
        await asyncio.gather(*[handler(*args, **kwargs) for handler in self.__eventhandlers])


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
        self.on_data_event -= obj_method
