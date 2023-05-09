class Plan:
    def __init__(self):
        self.pver = 0
        self.subCmd = 0
        self.area = 0
        self.workTime = 0
        self.version = ""
        self.id = ""
        self.userId = ""
        self.deviceId = ""
        self.planId = ""
        self.taskId = ""
        self.jobId = ""
        self.startTime = ""
        self.endTime = ""
        self.week = 0
        self.knifeHeight = 0
        self.model = 0
        self.edgeMode = 0
        self.requiredTime = 0
        self.routeAngle = 0
        self.routeModel = 0
        self.routeSpacing = 0
        self.ultrasonicBarrier = 0
        self.totalPlanNum = 0
        self.PlanIndex = 0
        self.result = 0
        self.speed = 0.0
        self.taskName = ""
        self.jobName = ""
        self.zoneHashs = []
        self.reserved = ""

    def __str__(self):
        return "Plan{pver=" + str(self.pver) + ", subCmd=" + str(self.subCmd) + ", area=" + str(self.area) + ", workTime=" + str(self.workTime) + ", version='" + self.version + "', id='" + self.id + "', userId='" + self.userId + "', deviceId='" + self.deviceId + "', planId='" + self.planId + "', taskId='" + self.taskId + "', jobId='" + self.jobId + "', startTime='" + self.startTime + "', endTime='" + self.endTime + "', week=" + str(self.week) + ", knifeHeight=" + str(self.knifeHeight) + ", model=" + str(self.model) + ", edgeMode=" + str(self.edgeMode) + ", requiredTime=" + str(self.requiredTime) + ", routeAngle=" + str(self.routeAngle) + ", routeModel=" + str(self.routeModel) + ", routeSpacing=" + str(self.routeSpacing) + ", ultrasonicBarrier=" + str(self.ultrasonicBarrier) + ", totalPlanNum=" + str(self.totalPlanNum) + ", PlanIndex=" + str(self.PlanIndex) + ", result=" + str(self.result) + ", speed=" + str(self.speed) + ", taskName='" + self.taskName + "', jobName='" + self.jobName + "', zoneHashs=" + str(self.zoneHashs) + ", reserved='" + self.reserved + "'}"
