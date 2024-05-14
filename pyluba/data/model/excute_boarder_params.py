
from jsonic.serializable import serialize
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

    def get_current_frame(self):
        """ generated source for method getCurrentFrame """
        return self.currentFrame

    def set_current_frame(self, i):
        """ generated source for method setCurrentFrame """
        self.currentFrame = i

    def get_job_index(self):
        """ generated source for method getJobIndex """
        return self.jobIndex

    def set_job_index(self, str_):
        """ generated source for method setJobIndex """
        self.jobIndex = str_

    def get_border(self):
        """ generated source for method getBorder """
        return self.border

    def set_border(self, border_list):
        """ generated source for method setBorder """
        self.border = border_list

    def __str__(self):
        """ generated source for method toString """
        return "ExecuteBorderParamsBean{currentFrame=" + self.currentFrame + ", jobIndex='" + self.jobIndex + "', border=" + self.border + '}'