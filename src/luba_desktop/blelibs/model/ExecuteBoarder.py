from jsonic import Serializable
from luba_desktop.blelibs.model.ExcuteBoarderParams import ExecuteBorderParams


class ExecuteBorder(Serializable):
    """ generated source for class ExecuteBorderBean """
    cmd = int()
    params = ExecuteBorderParams(None, None, None)

    def __init__(self, i, executeBorderParams: ExecuteBorderParams):
        """ generated source for method __init__ """
        self.cmd = i
        self.params = executeBorderParams

    def getCmd(self):
        """ generated source for method getCmd """
        return self.cmd

    def setCmd(self, i):
        """ generated source for method setCmd """
        self.cmd = i

    def getParams(self):
        """ generated source for method getParams """
        return self.params

    def setParams(self, executeBorderParams):
        """ generated source for method setParams """
        self.params = executeBorderParams

    def __str__(self):
        """ generated source for method toString """
        return "ExecuteBean{cmd=" + self.cmd + ", params=" + self.params + '}'