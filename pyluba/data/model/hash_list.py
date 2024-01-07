import typing


class HashList:
    def __init__(self):
        self.pver: int = 0
        self.subCmd: int = 0
        self.totalFrame: int = 0
        self.currentFrame: int = 0
        self.dataHash: int = 0
        self.path: typing.List[int] = []

    def __str__(self) -> str:
        return f"HashBean{{pver={self.pver}, subCmd={self.subCmd}, totalFrame={self.totalFrame}, " + \
            f"currentFrame={self.currentFrame}, dataHash={self.dataHash}, path={self.path}}}"
