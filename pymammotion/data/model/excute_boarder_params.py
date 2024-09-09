class ExecuteBorderParams:
    """generated source for class ExecuteBorderParamsBean"""

    border = list()
    currentFrame = 0
    jobIndex = ""

    def __init__(self, i, str_, list_) -> None:
        """Generated source for method __init__"""
        self.currentFrame = i
        self.border = list_
        self.jobIndex = str_

    def get_current_frame(self):
        """Generated source for method getCurrentFrame"""
        return self.currentFrame

    def set_current_frame(self, i) -> None:
        """Generated source for method setCurrentFrame"""
        self.currentFrame = i

    def get_job_index(self):
        """Generated source for method getJobIndex"""
        return self.jobIndex

    def set_job_index(self, str_) -> None:
        """Generated source for method setJobIndex"""
        self.jobIndex = str_

    def get_border(self):
        """Generated source for method getBorder"""
        return self.border

    def set_border(self, border_list) -> None:
        """Generated source for method setBorder"""
        self.border = border_list

    def __str__(self) -> str:
        """Generated source for method toString"""
        return (
            "ExecuteBorderParamsBean{currentFrame="
            + self.currentFrame
            + ", jobIndex='"
            + self.jobIndex
            + "', border="
            + self.border
            + "}"
        )
