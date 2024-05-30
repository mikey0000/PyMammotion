from jsonic.serializable import Serializable

from .excute_boarder_params import ExecuteBorderParams


class ExecuteBorder(Serializable):
    """generated source for class ExecuteBorderBean"""

    cmd = 0
    params = ExecuteBorderParams(None, None, None)

    def __init__(self, i, execute_border_params: ExecuteBorderParams):
        """Generated source for method __init__"""
        super().__init__()
        self.cmd = i
        self.params = execute_border_params

    def get_cmd(self):
        """Generated source for method getCmd"""
        return self.cmd

    def set_cmd(self, i):
        """Generated source for method setCmd"""
        self.cmd = i

    def get_params(self):
        """Generated source for method getParams"""
        return self.params

    def set_params(self, execute_border_params):
        """Generated source for method setParams"""
        self.params = execute_border_params

    def __str__(self):
        """Generated source for method toString"""
        return "ExecuteBean{cmd=" + self.cmd + ", params=" + self.params + '}'
