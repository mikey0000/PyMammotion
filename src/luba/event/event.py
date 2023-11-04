class Event(object):
 
    def __init__(self):
        self.__eventhandlers = []
 
    def __iadd__(self, handler):
        self.__eventhandlers.append(handler)
        return self
 
    def __isub__(self, handler):
        self.__eventhandlers.remove(handler)
        return self
 
    def __call__(self, *args, **keywargs):
        for eventhandler in self.__eventhandlers:
            eventhandler(*args, **keywargs)


class MoveEvent(object):
         
    def __init__(self):
        self.OnMoveFinished = Event()
         
    def MoveFinished(self):
        # This function will be executed once blufi finishes after a movement command and will
        # raise an event
        self.OnMoveFinished()
         
    def AddSubscribersForMoveFinishedEvent(self,objMethod):
        self.OnMoveFinished += objMethod
         
    def RemoveSubscribersForMoveFinishedEvent(self,objMethod):
        self.OnMoveFinished -= objMethod


class BleNotificationEvent(object):
         
    def __init__(self):
        self.OnBleNotification = Event()
         
    def BleNotification(self, data: bytearray):
        # This function will be executed when data is received.
        self.OnBleNotification(data)
         
    def AddSubscribersForBleNotificationEvent(self,objMethod):
        self.OnBleNotification += objMethod
         
    def RemoveSubscribersForBleNotificationEvent(self,objMethod):
        self.OnBleNotification -= objMethod