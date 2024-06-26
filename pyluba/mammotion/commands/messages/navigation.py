# === sendOrderMsg_Nav ===
from pyluba.data.model import GenerateRouteInformation
from pyluba.data.model.plan import Plan
from pyluba.proto import luba_msg_pb2, mctrl_nav_pb2


class MessageNavigation:
    def send_order_msg_nav(self, build):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            net=build)

        return luba_msg.SerializeToString()

    def allpowerfull_rw_adapter_x3(self, id: int, context: int, rw: int) -> None:
        build = mctrl_nav_pb2.MctlNav(
            nav_sys_param_cmd=mctrl_nav_pb2.nav_sys_param_msg(
                id=id, context=context, rw=rw
            )
        )
        print(
            f"Send command--9 general read and write command id={id}, context={context}, rw={rw}")
        return self.send_order_msg_nav(build)

 # === Below are the previous functions. These are going to be updated ===

    def get_hash(self):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_NONE,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_gethash=mctrl_nav_pb2.NavGetHashList(
                    pver=1,
                )
            )
        )

        return luba_msg.SerializeToString()

    def get_all_boundary_hash_list(self, i: int):
        """.getAllBoundaryHashList(3); 0"""
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_NONE,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_gethash=mctrl_nav_pb2.NavGetHashList(
                    pver=1,
                    subCmd=i
                )
            )
        )

        return luba_msg.SerializeToString()

    def get_line_info(self, i: int):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_zigzag_ack=mctrl_nav_pb2.NavUploadZigZagResultAck(
                    pver=1,
                    currentHash=i,
                    subCmd=0
                )
            ),
        )
        return luba_msg.SerializeToString()

    def get_hash_response(self, totalFrame: int, currentFrame: int):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_gethash=mctrl_nav_pb2.NavGetHashList(
                    pver=1,
                    subCmd=2,
                    action=8,
                    type=3,
                    currentFrame=currentFrame,
                    totalFrame=totalFrame
                )
            )
        )
        return luba_msg.SerializeToString()


    def get_area_tobe_transferred(self):
        commondata = mctrl_nav_pb2.NavGetCommData(
            pver=1,
            subCmd=1,
            action=8,
            type=3
        )

        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_get_commondata=commondata
            )
        )
        return luba_msg.SerializeToString()

    def synchronize_hash_data(self, hash_int: int):
        commondata = mctrl_nav_pb2.NavGetCommData(
            pver=1,
            subCmd=1,
            action=8,
            Hash=hash_int
        )

        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_get_commondata=commondata
            )
        )
        return luba_msg.SerializeToString()

    def start_work_job(self):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_taskctrl=mctrl_nav_pb2.NavTaskCtrl(
                    type=1,
                    action=1,
                    result=0
                )
            )
        )

        return luba_msg.SerializeToString()

    def read_plan(self, i: int):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_planjob_set=mctrl_nav_pb2.NavPlanJobSet(
                    subCmd=i,
                )
            )
        )
        return luba_msg.SerializeToString()

    # (2, 0);

    def read_plan_index(self, i: int, i2: int):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_planjob_set=mctrl_nav_pb2.NavPlanJobSet(
                    subCmd=i,
                    planIndex=i2
                )
            )
        )
        return luba_msg.SerializeToString()

    def read_plan_unable_time(self, i):
        build = mctrl_nav_pb2.NavUnableTimeSet()
        build.subCmd = i

        luba_msg = luba_msg_pb2.LubaMsg()
        luba_msg.msgtype = luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV
        luba_msg.sender = luba_msg_pb2.MsgDevice.DEV_MOBILEAPP
        luba_msg.rcver = luba_msg_pb2.MsgDevice.DEV_MAINCTL
        luba_msg.msgattr = luba_msg_pb2.MsgAttr.MSG_ATTR_REQ
        luba_msg.seqs = 1
        luba_msg.version = 1
        luba_msg.subtype = 1
        luba_msg.nav.todev_unable_time_set.CopyFrom(build)

        return luba_msg.SerializeToString()

    def send_plan2(self, plan: Plan):
        navPlanJobSet = luba_msg_pb2.NavPlanJobSet()
        navPlanJobSet.pver = plan.pver
        navPlanJobSet.subCmd = plan.subCmd
        navPlanJobSet.area = plan.area
        navPlanJobSet.deviceId = plan.deviceId
        navPlanJobSet.workTime = plan.workTime
        navPlanJobSet.version = plan.version
        navPlanJobSet.id = plan.id
        navPlanJobSet.userId = plan.userId
        navPlanJobSet.planId = plan.planId
        navPlanJobSet.taskId = plan.taskId
        navPlanJobSet.jobId = plan.jobId
        navPlanJobSet.startTime = plan.startTime
        navPlanJobSet.endTime = plan.endTime
        navPlanJobSet.week = plan.week
        navPlanJobSet.knifeHeight = plan.knifeHeight
        navPlanJobSet.model = plan.model
        navPlanJobSet.edgeMode = plan.edgeMode
        navPlanJobSet.requiredTime = plan.requiredTime
        navPlanJobSet.routeAngle = plan.routeAngle
        navPlanJobSet.routeModel = plan.routeModel
        navPlanJobSet.routeSpacing = plan.routeSpacing
        navPlanJobSet.ultrasonicBarrier = plan.ultrasonicBarrier
        navPlanJobSet.totalPlanNum = plan.totalPlanNum
        navPlanJobSet.planIndex = plan.planIndex
        navPlanJobSet.result = plan.result
        navPlanJobSet.speed = plan.speed
        navPlanJobSet.taskName = plan.taskName
        navPlanJobSet.jobName = plan.jobName
        navPlanJobSet.zoneHashs.extend(plan.zoneHashs)
        navPlanJobSet.reserved = plan.reserved

        luba_msg = luba_msg_pb2.luba_msg()
        luba_msg.msgtype = luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV
        luba_msg.sender = luba_msg_pb2.MsgDevice.DEV_MOBILEAPP
        luba_msg.rcver = luba_msg_pb2.MsgDevice.DEV_MAINCTL
        luba_msg.msgattr = luba_msg_pb2.MsgAttr.MSG_ATTR_REQ
        luba_msg.seqs = 1
        luba_msg.version = 1
        luba_msg.subtype = 1
        luba_msg.nav.todevPlanjobSet.CopyFrom(navPlanJobSet)

        return luba_msg.SerializeToString()

    def get_reserved(self, generate_route_information):
        return bytes([generate_route_information.path_order, generate_route_information.obstacle_laps]).decode('utf-8')

    def generate_route_information(self, generate_route_information: GenerateRouteInformation):
        """How you start a manual job, then call startjob"""

        nav_req_cover_path = mctrl_nav_pb2.NavReqCoverPath()
        nav_req_cover_path.pver = 1
        nav_req_cover_path.subCmd = 0
        nav_req_cover_path.zoneHashs.extend(
            generate_route_information.one_hashs)
        nav_req_cover_path.jobMode = generate_route_information.job_mode  # grid type
        nav_req_cover_path.edgeMode = generate_route_information.edge_mode  # border laps
        nav_req_cover_path.knifeHeight = generate_route_information.knife_height
        nav_req_cover_path.speed = generate_route_information.speed
        nav_req_cover_path.ultraWave = generate_route_information.ultra_wave
        nav_req_cover_path.channelWidth = generate_route_information.channel_width  # mow width
        nav_req_cover_path.channelMode = generate_route_information.channel_mode
        nav_req_cover_path.toward = generate_route_information.toward
        nav_req_cover_path.reserved = self.get_reserved(
            generate_route_information)  # grid or border first

        luba_msg = luba_msg_pb2.LubaMsg()
        luba_msg.msgtype = luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV
        luba_msg.sender = luba_msg_pb2.MsgDevice.DEV_MOBILEAPP
        luba_msg.rcver = luba_msg_pb2.MsgDevice.DEV_MAINCTL
        luba_msg.msgattr = luba_msg_pb2.MsgAttr.MSG_ATTR_REQ
        luba_msg.seqs = 1
        luba_msg.version = 1
        luba_msg.subtype = 1

        mctl_nav = mctrl_nav_pb2.MctlNav()
        mctl_nav.bidire_reqconver_path.CopyFrom(nav_req_cover_path)
        luba_msg.nav.CopyFrom(mctl_nav)

        return luba_msg.SerializeToString()

    def start_work_order(self, job_id, job_ver, rain_tactics, job_mode, knife_height, speed, ultra_wave,
                               channel_width, channel_mode):
        """Pretty sure this starts a job too but isn't used"""
        luba_msg = luba_msg_pb2.LubaMsg()
        luba_msg.msgtype = luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV
        luba_msg.sender = luba_msg_pb2.MsgDevice.DEV_MOBILEAPP
        luba_msg.rcver = luba_msg_pb2.MsgDevice.DEV_MAINCTL
        luba_msg.msgattr = luba_msg_pb2.MsgAttr.MSG_ATTR_REQ
        luba_msg.seqs = 1
        luba_msg.version = 1
        luba_msg.subtype = 1

        nav = mctrl_nav_pb2.MctlNav()
        start_job = mctrl_nav_pb2.NavStartJob()
        start_job.jobId = job_id
        start_job.jobVer = job_ver
        start_job.rainTactics = rain_tactics
        start_job.jobMode = job_mode
        start_job.knifeHeight = knife_height
        start_job.speed = speed
        start_job.ultraWave = ultra_wave
        start_job.channelWidth = channel_width
        start_job.channelMode = channel_mode

        nav.todev_mow_task.CopyFrom(start_job)
        luba_msg.nav.CopyFrom(nav)

        return luba_msg.SerializeToString()

    def breakPointContinue(self):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_taskctrl=mctrl_nav_pb2.NavTaskCtrl(
                    type=1,
                    action=7,
                    result=0
                )
            )
        )
        return luba_msg.SerializeToString()

    def breakPointAnywhereContinue(self, refresh_loading: bool):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_taskctrl=mctrl_nav_pb2.NavTaskCtrl(
                    type=1,
                    action=9,
                    result=0
                )
            )
        )
        return luba_msg.SerializeToString()

    def pause_execute_task(self):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_taskctrl=mctrl_nav_pb2.NavTaskCtrl(
                    type=1,
                    action=2,
                    result=0
                )
            )
        )

        return luba_msg.SerializeToString()

    def resume_execute_task(self):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_taskctrl=mctrl_nav_pb2.NavTaskCtrl(
                    type=1,
                    action=3,
                    result=0
                )
            )
        )

        return luba_msg.SerializeToString()

    def return_to_dock(self):
        mctrlNav = mctrl_nav_pb2.MctlNav()
        navTaskCtrl = mctrl_nav_pb2.NavTaskCtrl()
        navTaskCtrl.type = 1
        navTaskCtrl.action = 5
        navTaskCtrl.result = 0
        mctrlNav.todev_taskctrl.CopyFrom(navTaskCtrl)

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV
        lubaMsg.sender = luba_msg_pb2.MsgDevice.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.MsgDevice.DEV_MAINCTL
        lubaMsg.msgattr = luba_msg_pb2.MsgAttr.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.nav.CopyFrom(mctrlNav)
        return lubaMsg.SerializeToString()

    def leave_dock(self):
        mctrlNav = mctrl_nav_pb2.MctlNav()
        mctrlNav.todev_one_touch_leave_pile = 1

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.DEV_MAINCTL
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.nav.CopyFrom(mctrlNav)
        return lubaMsg.SerializeToString()

    def set_data_synchronization(self, type: int):
        mctrl_nav = mctrl_nav_pb2.MctlNav(
            todev_get_commondata=mctrl_nav_pb2.NavGetCommData(
                pver=1,
                action=12,
                type=type
            )
        )

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_NAV
        lubaMsg.sender = luba_msg_pb2.DEV_MAINCTL
        lubaMsg.rcver = luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.nav.CopyFrom(mctrl_nav)
        return lubaMsg.SerializeToString()