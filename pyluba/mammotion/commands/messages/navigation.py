# === sendOrderMsg_Nav ===
from asyncio import sleep
from io import BytesIO
import sys
from pyluba.bluetooth.data.framectrldata import FrameCtrlData
from pyluba.data.model.plan import Plan
from pyluba.proto import luba_msg_pb2, mctrl_nav_pb2


class MessageNavigation:
    def send_order_msg_nav(self, build):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
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

    def getTypeValue(self, type: int, subtype: int):
        return (subtype << 2) | type

    async def post_custom_data_bytes(self, data: bytes):
        if (data == None):
            return
        type_val = self.getTypeValue(1, 19)
        try:
            suc = await self.post(self.mEncrypted, self.mChecksum, self.mRequireAck, type_val, data)
            # int status = suc ? 0 : BlufiCallback.CODE_WRITE_DATA_FAILED
            # onPostCustomDataResult(status, data)
            # print(suc)
        except Exception as err:
            print(err)

    async def post_custom_data(self, data_str: str):
        data = data_str.encode()
        if (data == None):
            return
        type_val = self.getTypeValue(1, 19)
        try:
            suc = await self.post(self.mEncrypted, self.mChecksum, self.mRequireAck, type_val, data)
            # int status = suc ? 0 : BlufiCallback.CODE_WRITE_DATA_FAILED
            # onPostCustomDataResult(status, data)
        except Exception as err:
            print(err)

    async def post(self, encrypt: bool, checksum: bool, require_ack: bool, type_of: int, data: bytes) -> bool:
        if data is None:
            return await self.post_non_data(encrypt, checksum, require_ack, type_of)

        return await self.post_contains_data(encrypt, checksum, require_ack, type_of, data)

    async def post_non_data(self, encrypt: bool, checksum: bool, require_ack: bool, type_of: int) -> bool:
        sequence = self.generateSendSequence()
        postBytes = self.getPostBytes(
            type_of, encrypt, checksum, require_ack, False, sequence, None)
        posted = await self.gatt_write(postBytes)
        return posted and (not require_ack or self.receiveAck(sequence))

    async def post_contains_data(self, encrypt: bool, checksum: bool, require_ack: bool, type_of: int,
                                 data: bytes) -> bool:
        chunk_size = 517  # self.client.mtu_size - 3

        chunks = list()
        for i in range(0, len(data), chunk_size):
            if (i + chunk_size > len(data)):
                chunks.append(data[i: len(data)])
            else:
                chunks.append(data[i: i + chunk_size])
        for index, chunk in enumerate(chunks):
            frag = index != len(chunks) - 1
            sequence = self.generateSendSequence()
            postBytes = self.getPostBytes(
                type_of, encrypt, checksum, require_ack, frag, sequence, chunk)
            # print("sequence")
            # print(sequence)
            posted = await self.gatt_write(postBytes)
            if (posted != None):
                return False

            if (not frag):
                return not require_ack or self.receiveAck(sequence)

            if (require_ack and not self.receiveAck(sequence)):
                return False
            else:
                print("sleeping 0.01")
                await sleep(0.01)

    def getPostBytes(self, type: int, encrypt: bool, checksum: bool, require_ack: bool, hasFrag: bool, sequence: int,
                     data: bytes) -> bytes:

        byteOS = BytesIO()
        dataLength = (0 if data == None else len(data))
        frameCtrl = FrameCtrlData.getFrameCTRLValue(
            encrypt, checksum, 0, require_ack, hasFrag)
        byteOS.write(type.to_bytes(1, sys.byteorder))
        byteOS.write(frameCtrl.to_bytes(1, sys.byteorder))
        byteOS.write(sequence.to_bytes(1, sys.byteorder))
        byteOS.write(dataLength.to_bytes(1, sys.byteorder))

        if (data != None):
            byteOS.write(data)

        print(byteOS.getvalue())
        return byteOS.getvalue()

    async def get_hash(self):
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

        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def get_all_boundary_hash_list(self, i: int):
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

        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def get_line_info(self, i: int):
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
        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def get_hash_response(self, totalFrame: int, currentFrame: int):
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
        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    def receiveAck(self, expectAck: int) -> bool:
        try:
            ack = next(self.mAck)
            return ack == expectAck
        except Exception as err:
            print(err)
            return False

    def generateSendSequence(self):
        return next(self.mSendSequence) & 255

    async def get_area_tobe_transferred(self):
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
        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def synchronize_hash_data(self, hash_int: int):
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
        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def start_work_job(self):
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

        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def read_plan(self, i: int):
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
        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    # (2, 0);

    async def read_plan(self, i: int, i2: int):
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
        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def read_plan_unable_time(self, i):
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

        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def send_plan2(self, plan: Plan):
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

        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    def get_reserved(self, generate_route_information):
        return bytes([generate_route_information.path_order, generate_route_information.obstacle_laps]).decode('utf-8')

    async def generate_route_information(self, generate_route_information):
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

        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def start_work_order(self, job_id, job_ver, rain_tactics, job_mode, knife_height, speed, ultra_wave,
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

        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def breakPointContinue(self):
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
        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def breakPointAnywhereContinue(self, refresh_loading: bool):
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
        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

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

        byte_array = luba_msg.SerializeToString()

    async def return_to_dock(self):
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
        bytes = lubaMsg.SerializeToString()
        await self.post_custom_data_bytes(bytes)

    async def leave_dock(self):
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
        bytes = lubaMsg.SerializeToString()
        await self.post_custom_data_bytes(bytes)

    def _getTypeValue(self, type: int, subtype: int):
        return (subtype << 2) | type
