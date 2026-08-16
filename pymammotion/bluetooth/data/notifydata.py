from io import BytesIO

"""Notify data object"""


class BlufiNotifyData:
    """Accumulator for a fragmented BluFi notification frame."""

    def __init__(self) -> None:
        self.mDataOS = BytesIO()
        self.mFrameCtrlValue = 0
        self.mPkgType = 0
        self.mSubType = 0
        self.mTypeValue = 0

    def getType(self):
        """Return the BluFi frame type value."""
        return self.mTypeValue

    #  JADX INFO: Access modifiers changed from: package-private
    def setType(self, i) -> None:
        """Set the BluFi frame type value."""
        self.mTypeValue = i

    #  JADX INFO: Access modifiers changed from: package-private
    def getPkgType(self):
        """Return the BluFi package type."""
        return self.mPkgType

    #  JADX INFO: Access modifiers changed from: package-private
    def setPkgType(self, i) -> None:
        """Set the BluFi package type."""
        self.mPkgType = i

    #  JADX INFO: Access modifiers changed from: package-private
    def getSubType(self):
        """Return the BluFi frame subtype."""
        return self.mSubType

    #  JADX INFO: Access modifiers changed from: package-private
    def setSubType(self, i) -> None:
        """Set the BluFi frame subtype."""
        self.mSubType = i

    def getFrameCtrl(self):
        """Return the BluFi frame-control byte."""
        return self.mFrameCtrlValue

    #  JADX INFO: Access modifiers changed from: package-private
    def setFrameCtrl(self, i) -> None:
        """Set the BluFi frame-control byte."""
        self.mFrameCtrlValue = i

    #  JADX INFO: Access modifiers changed from: package-private
    def addData(self, bArr, i) -> None:
        """Append the payload of a fragment, skipping the first ``i`` header bytes."""
        self.mDataOS.write(bArr[i:])

    #  JADX INFO: Access modifiers changed from: package-private
    def getDataArray(self) -> bytes:
        """Return the reassembled payload accumulated from all fragments."""
        return self.mDataOS.getvalue()
