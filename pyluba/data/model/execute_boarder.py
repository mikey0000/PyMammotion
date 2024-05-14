from jsonic.serializable import serialize, Serializable
from .excute_boarder_params import ExecuteBorderParams


class ExecuteBorder(Serializable):
    """ generated source for class ExecuteBorderBean """
    cmd = int()
    params = ExecuteBorderParams(None, None, None)

    def __init__(self, i, execute_border_params: ExecuteBorderParams):
        """ generated source for method __init__ """
        super().__init__()
        self.cmd = i
        self.params = execute_border_params

    def get_cmd(self):
        """ generated source for method getCmd """
        return self.cmd

    def set_cmd(self, i):
        """ generated source for method setCmd """
        self.cmd = i

    def get_params(self):
        """ generated source for method getParams """
        return self.params

    def set_params(self, execute_border_params):
        """ generated source for method setParams """
        self.params = execute_border_params

    def __str__(self):
        """ generated source for method toString """
        return "ExecuteBean{cmd=" + self.cmd + ", params=" + self.params + '}'
