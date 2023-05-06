from io import BytesIO

"""Notify data object"""
class BlufiNotifyData(object):
    """ generated source for class BlufiNotifyData """
    def __init__(self):
        self.mDataOS = BytesIO()
        self.mFrameCtrlValue = 0
        self.mPkgType = 0
        self.mSubType = 0
        self.mTypeValue = 0

    def getType(self):
        """ generated source for method getType """
        return self.mTypeValue

    #  JADX INFO: Access modifiers changed from: package-private 
    def setType(self, i):
        """ generated source for method setType """
        self.mTypeValue = i

    #  JADX INFO: Access modifiers changed from: package-private 
    def getPkgType(self):
        """ generated source for method getPkgType """
        return self.mPkgType

    #  JADX INFO: Access modifiers changed from: package-private 
    def setPkgType(self, i):
        """ generated source for method setPkgType """
        self.mPkgType = i

    #  JADX INFO: Access modifiers changed from: package-private 
    def getSubType(self):
        """ generated source for method getSubType """
        return self.mSubType

    #  JADX INFO: Access modifiers changed from: package-private 
    def setSubType(self, i):
        """ generated source for method setSubType """
        self.mSubType = i

    def getFrameCtrl(self):
        """ generated source for method getFrameCtrl """
        return self.mFrameCtrlValue

    #  JADX INFO: Access modifiers changed from: package-private 
    def setFrameCtrl(self, i):
        """ generated source for method setFrameCtrl """
        self.mFrameCtrlValue = i

    #  JADX INFO: Access modifiers changed from: package-private 
    def addData(self, bArr, i):
        """ generated source for method addData """
        self.mDataOS.write(bArr[i:])

    #  JADX INFO: Access modifiers changed from: package-private 
    def getDataArray(self):
        """ generated source for method getDataArray """
        print("data Array")
        return self.mDataOS.getvalue()