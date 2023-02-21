class Event(object):
 
    def __init__(self):
        self.__eventhandlers = []
 
    def __iadd__(self, handler):
        self.__eventhandlers.append(handler)
        return self
 
    def __isub__(self, handler):
        self.__eventhandlers.remove(handler)
        return self
 
    async def __call__(self, *args, **keywargs):
        for eventhandler in self.__eventhandlers:
            await eventhandler(*args, **keywargs)