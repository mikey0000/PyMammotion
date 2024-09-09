from io import BytesIO

"""Notify data object"""


class BlufiNotifyData:
    """generated source for class BlufiNotifyData"""

    def __init__(self) -> None:
        self.mDataOS = BytesIO()
        self.mFrameCtrlValue = 0
        self.mPkgType = 0
        self.mSubType = 0
        self.mTypeValue = 0

    def getType(self):
        """Generated source for method getType"""
        return self.mTypeValue

    #  JADX INFO: Access modifiers changed from: package-private
    def setType(self, i) -> None:
        """Generated source for method setType"""
        self.mTypeValue = i

    #  JADX INFO: Access modifiers changed from: package-private
    def getPkgType(self):
        """Generated source for method getPkgType"""
        return self.mPkgType

    #  JADX INFO: Access modifiers changed from: package-private
    def setPkgType(self, i) -> None:
        """Generated source for method setPkgType"""
        self.mPkgType = i

    #  JADX INFO: Access modifiers changed from: package-private
    def getSubType(self):
        """Generated source for method getSubType"""
        return self.mSubType

    #  JADX INFO: Access modifiers changed from: package-private
    def setSubType(self, i) -> None:
        """Generated source for method setSubType"""
        self.mSubType = i

    def getFrameCtrl(self):
        """Generated source for method getFrameCtrl"""
        return self.mFrameCtrlValue

    #  JADX INFO: Access modifiers changed from: package-private
    def setFrameCtrl(self, i) -> None:
        """Generated source for method setFrameCtrl"""
        self.mFrameCtrlValue = i

    #  JADX INFO: Access modifiers changed from: package-private
    def addData(self, bArr, i) -> None:
        """Generated source for method addData"""
        self.mDataOS.write(bArr[i:])

    #  JADX INFO: Access modifiers changed from: package-private
    def getDataArray(self):
        """Generated source for method getDataArray"""
        return self.mDataOS.getvalue()
