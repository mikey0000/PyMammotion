import asyncio


class Event:
    def __init__(self):
        self.__eventhandlers = []

    def __iadd__(self, handler):
        self.__eventhandlers.append(handler)
        return self

    def __isub__(self, handler):
        self.__eventhandlers.remove(handler)
        return self

    async def __call__(self, *args, **kwargs):
        await asyncio.gather(*[handler(*args, **kwargs) for handler in self.__eventhandlers])


class MoveEvent:
    def __init__(self):
        self.OnMoveFinished = Event()

    async def MoveFinished(self):
        # This function will be executed once blufi finishes after a movement command and will
        # raise an event
        await self.OnMoveFinished()

    def AddSubscribersForMoveFinishedEvent(self, objMethod):
        self.OnMoveFinished += objMethod

    def RemoveSubscribersForMoveFinishedEvent(self, objMethod):
        self.OnMoveFinished -= objMethod


class BleNotificationEvent:
    def __init__(self):
        self.OnBleNotification = Event()

    async def BleNotification(self, data: bytearray):
        # This function will be executed when data is received.
        await self.OnBleNotification(data)

    def AddSubscribersForBleNotificationEvent(self, objMethod):
        self.OnBleNotification += objMethod

    def RemoveSubscribersForBleNotificationEvent(self, objMethod):
        self.OnBleNotification -= objMethod


class DataEvent:
    """Callbacks for data events."""

    def __init__(self):
        self.on_data_event = Event()

    async def data_event(self, data):
        # This function will be executed when data is received.
        await self.on_data_event(data)

    def add_subscribers(self, obj_method):
        self.on_data_event += obj_method

    def remove_subscribers(self, obj_method):
        self.on_data_event -= obj_method
