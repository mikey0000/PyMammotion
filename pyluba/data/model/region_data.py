from typing import List, Optional


class RegionData:
    def __init__(self):
        self.Hash: Optional[int] = None
        self.action: int = 0
        self.currentFrame: int = 0
        self.dataHash: Optional[int] = None
        self.dataLen: int = 0
        self.pHashA: Optional[int] = None
        self.pHashB: Optional[int] = None
        self.path: List[List[float]] = []
        self.pver: int = 0
        self.result: int = 0
        self.subCmd: int = 0
        self.totalFrame: int = 0
        self.type: int = 0

    def setHash(self, l: int) -> None:
        self.Hash = l

    def getDataLen(self) -> int:
        return self.dataLen

    def setDataLen(self, i: int) -> None:
        self.dataLen = i

    def getPver(self) -> int:
        return self.pver

    def setPver(self, i: int) -> None:
        self.pver = i

    def getSubCmd(self) -> int:
        return self.subCmd

    def setSubCmd(self, i: int) -> None:
        self.subCmd = i

    def getResult(self) -> int:
        return self.result

    def setResult(self, i: int) -> None:
        self.result = i

    def getAction(self) -> int:
        return self.action

    def setAction(self, i: int) -> None:
        self.action = i

    def getType(self) -> int:
        return self.type

    def setType(self, i: int) -> None:
        self.type = i

    def getTotalFrame(self) -> int:
        return self.totalFrame

    def setTotalFrame(self, i: int) -> None:
        self.totalFrame = i

    def getCurrentFrame(self) -> int:
        return self.currentFrame

    def setCurrentFrame(self, i: int) -> None:
        self.currentFrame = i

    def getPath(self) -> List[List[float]]:
        return self.path

    def setPath(self, lst: List[List[float]]) -> None:
        self.path = lst

    def getHash(self) -> Optional[int]:
        return self.Hash

    def setHash(self, j: int) -> None:
        self.Hash = j

    def getDataHash(self) -> Optional[int]:
        return self.dataHash

    def setDataHash(self, j: int) -> None:
        self.dataHash = j

    def getpHashA(self) -> Optional[int]:
        return self.pHashA

    def setpHashA(self, j: int) -> None:
        self.pHashA = j

    def getpHashB(self) -> Optional[int]:
        return self.pHashB

    def setpHashB(self, j: int) -> None:
        self.pHashB = j

    def __str__(self) -> str:
        return "RegionalDataBean{pver=" + str(self.pver) + ", subCmd=" + str(self.subCmd) + ", result=" + str(self.result) + ", action=" + str(self.action) + ", type=" + str(self.type) + ", Hash=" + str(self.Hash) + ", totalFrame=" + str(self.totalFrame) + ", currentFrame=" + str(self.currentFrame) + ", path="+ str(self.path) + ", dataHash=" + str(self.dataHash) + ", pHashA=" + str(self.pHashA) + ", pHashB=" + str(self.pHashB)
