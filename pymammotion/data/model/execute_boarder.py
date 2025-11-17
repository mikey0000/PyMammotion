from jsonic.serializable import Serializable

from .excute_boarder_params import ExecuteBorderParams


class ExecuteBorder(Serializable):
    """generated source for class ExecuteBorderBean"""

    cmd = 0
    params = ExecuteBorderParams()

    def __init__(self, i: int, execute_border_params: ExecuteBorderParams) -> None:
        """Generated source for method __init__"""
        super().__init__()
        self.cmd = i
        self.params = execute_border_params

    def get_cmd(self) -> int:
        """Generated source for method getCmd"""
        return self.cmd

    def set_cmd(self, i) -> None:
        """Generated source for method setCmd"""
        self.cmd = i

    def get_params(self) -> ExecuteBorderParams:
        """Generated source for method getParams"""
        return self.params

    def set_params(self, execute_border_params: ExecuteBorderParams) -> None:
        """Generated source for method setParams"""
        self.params = execute_border_params

    def __str__(self) -> str:
        """Generated source for method toString"""
        return f"ExecuteBean cmd={self.cmd}, params={self.params}"
