from jsonic import Serializable
from typing import List


class ExecuteBorderParams(object):
    """ generated source for class ExecuteBorderParamsBean """
    border = list()
    currentFrame = int()
    jobIndex = str()

    def __init__(self, i, str_, list_):
        """ generated source for method __init__ """
        self.currentFrame = i
        self.border = list_
        self.jobIndex = str_

    def getCurrentFrame(self):
        """ generated source for method getCurrentFrame """
        return self.currentFrame

    def setCurrentFrame(self, i):
        """ generated source for method setCurrentFrame """
        self.currentFrame = i

    def getJobIndex(self):
        """ generated source for method getJobIndex """
        return self.jobIndex

    def setJobIndex(self, str_):
        """ generated source for method setJobIndex """
        self.jobIndex = str_

    def getBorder(self):
        """ generated source for method getBorder """
        return self.border

    def setBorder(self, list_):
        """ generated source for method setBorder """
        self.border = list_

    def __str__(self):
        """ generated source for method toString """
        return "ExecuteBorderParamsBean{currentFrame=" + self.currentFrame + ", jobIndex='" + self.jobIndex + "', border=" + self.border + '}'