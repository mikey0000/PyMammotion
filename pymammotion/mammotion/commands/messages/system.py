# === sendOrderMsg_Sys ===
import datetime
from abc import ABC

from pymammotion import logger
from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.mammotion.commands.messages.navigation import MessageNavigation
from pymammotion.proto.luba_msg import LubaMsg, MsgAttr, MsgCmdType, MsgDevice
from pymammotion.proto.mctrl_sys import (
    DeviceProductTypeInfoT,
    LoraCfgReq,
    MctlSys,
    MCtrlSimulationCmdData,
    ReportInfoCfg,
    RptAct,
    RptInfoType,
    SysCommCmd,
    SysKnifeControl,
    SysSetDateTime,
    TimeCtrlLight,
)
from pymammotion.utility.device_type import DeviceType


class MessageSystem(AbstractMessage, ABC):
    messageNavigation: MessageNavigation = MessageNavigation()

    def send_order_msg_sys(self, sys):
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.MSG_CMD_TYPE_EMBED_SYS,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.MSG_CMD_TYPE_EMBED_SYS, MsgDevice.DEV_MAINCTL),
            sys=sys,
        )

        return luba_msg.SerializeToString()

    def send_order_msg_sys_legacy(self, sys):
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.MSG_CMD_TYPE_EMBED_SYS,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=MsgDevice.DEV_MAINCTL,
            sys=sys,
        )

        return luba_msg.SerializeToString()

    def reset_system(self):
        build = MctlSys(todev_reset_system=1)
        logger.debug("Send command - send factory reset")
        return self.send_order_msg_sys(build)

    def set_blade_control(self, on_off: int):
        mctlsys = MctlSys()
        sys_knife_control = SysKnifeControl()
        sys_knife_control.knife_status = on_off
        mctlsys.todev_knife_ctrl = sys_knife_control

        return self.send_order_msg_sys(mctlsys)

    def get_device_product_model(self):
        return self.send_order_msg_sys(MctlSys(device_product_type_info=DeviceProductTypeInfoT()))

    def read_and_set_sidelight(self, is_sidelight: bool, operate: int):
        """Read state of sidelight as well as set it."""
        if is_sidelight:
            build = TimeCtrlLight(
                operate=operate,
                enable=0,
                action=0,
                start_hour=0,
                start_min=0,
                end_hour=0,
                end_min=0,
            )
        else:
            build = TimeCtrlLight(
                operate=operate,
                enable=1,
                action=0,
                start_hour=0,
                start_min=0,
                end_hour=0,
                end_min=0,
            )
        logger.debug(f"Send read and write sidelight command is_sidelight:{
            is_sidelight}, operate:{operate}")
        build2 = MctlSys(todev_time_ctrl_light=build)
        logger.debug(f"Send command - send read and write sidelight command is_sidelight:{
            is_sidelight}, operate:{operate}, timeCtrlLight:{build}")
        return self.send_order_msg_sys(build2)

    def test_tool_order_to_sys(self, sub_cmd: int, param_id: int, param_value: list[int]):
        build = MCtrlSimulationCmdData(sub_cmd=sub_cmd, param_id=param_id, param_value=param_value)
        logger.debug(f"Send tool test command: subCmd={sub_cmd}, param_id:{
            param_id}, param_value={param_value}")
        build2 = MctlSys(simulation_cmd=build)
        logger.debug(f"Send tool test command: subCmd={sub_cmd}, param_id:{
            param_id}, param_value={param_value}")
        return self.send_order_msg_sys(build2)

    def read_and_set_rtk_paring_code(self, op: int, cgf: str | None = None):
        logger.debug(f"Send read and write base station configuration quality op:{
            op}, cgf:{cgf}")
        return self.send_order_msg_sys(MctlSys(todev_lora_cfg_req=LoraCfgReq(op=op, cfg=cgf)))

    def allpowerfull_rw(self, id: int, context: int, rw: int):
        if (id == 6 or id == 3 or id == 7) and DeviceType.is_luba_2(self.get_device_name()):
            self.messageNavigation.allpowerfull_rw_adapter_x3(id, context, rw)
            return
        build = MctlSys(bidire_comm_cmd=SysCommCmd(id=id, context=context, rw=rw))
        logger.debug(f"Send command - 9 general read and write command id={id}, context={context}, rw={rw}")
        if id == 5:
            # This logic doesnt make snese, but its what they had so..
            return self.send_order_msg_sys(build)
        return self.send_order_msg_sys(build)

    # Commented out as not needed and too many refs to try fix up
    # def factory_test_order(self, test_id: int, test_duration: int, expect: str):
    #     new_builder = mow_to_app_qctools_info_t.Builder()
    #     logger.debug(f"Factory tool logger.debug, expect={expect}")
    #     if not expect:
    #         build = new_builder.set_type_value(
    #             test_id).set_time_of_duration(test_duration).build()
    #     else:
    #         try:
    #             json_array = json.loads(expect)
    #             z2 = True
    #             for i in range(len(json_array)):
    #                 new_builder2 = QCAppTestExcept.Builder()
    #                 json_object = json_array[i]
    #                 if "except_type" in json_object:
    #                     string = json_object["except_type"]
    #                     if "conditions" in json_object:
    #                         json_array2 = json_object["conditions"]
    #                         for i2 in range(len(json_array2)):
    #                             json_object2 = json_array2[i2]
    #                             new_builder3 = QCAppTestConditions.Builder()
    #                             if "cond_type" in json_object2:
    #                                 new_builder3.set_cond_type(
    #                                     json_object2["cond_type"])
    #                             else:
    #                                 z2 = False
    #                             if "value" in json_object2:
    #                                 obj = json_object2["value"]
    #                                 if string == "int":
    #                                     new_builder3.set_int_val(int(obj))
    #                                 elif string == "float":
    #                                     new_builder3.set_float_val(float(obj))
    #                                 elif string == "double":
    #                                     new_builder3.set_double_val(float(obj))
    #                                 elif string == "string":
    #                                     new_builder3.set_string_val(str(obj))
    #                                 else:
    #                                     z2 = False
    #                                 new_builder2.add_conditions(new_builder3)
    #                             else:
    #                                 z2 = False
    #                     new_builder2.set_except_type(string)
    #                     new_builder.add_except(new_builder2)
    #                     new_builder2.clear()
    #             z = z2
    #         except json.JSONDecodeError:
    #             z = False
    #         if z:
    #             build = new_builder.set_type_value(
    #                 test_id).set_time_of_duration(test_duration).build()
    #         else:
    #             build = new_builder.set_type_value(
    #                 test_id).set_time_of_duration(test_duration).build()
    #     logger.debug(f"Factory tool logger.debug, mow_to_app_qctools_info_t={
    #         build.except_count}, mow_to_app_qctools_info_t22={build.except_list}")
    #     build2 = MctlSys(mow_to_app_qctools_info=build)
    #     logger.debug(f"Send command - factory tool test command testId={
    #         test_id}, testDuration={test_duration}", "Factory tool logger.debug222", True)
    #     return self.send_order_msg_sys(build2)

    def send_sys_set_date_time(self):
        calendar = datetime.datetime.now()
        i = calendar.year
        i2 = calendar.month
        i3 = calendar.day
        i4 = calendar.isoweekday()
        i5 = calendar.hour
        i6 = calendar.minute
        i7 = calendar.second
        i8 = calendar.utcoffset().total_seconds() // 60 if calendar.utcoffset() else 0
        i9 = 1 if calendar.dst() else 0
        logger.debug(f"Print time zone, time zone={
            i8}, daylight saving time={i9} week={i4}")
        build = MctlSys(
            todev_data_time=SysSetDateTime(
                year=i,
                month=i2,
                date=i3,
                week=i4,
                hours=i5,
                minutes=i6,
                seconds=i7,
                time_zone=i8,
                daylight=i9,
            )
        )
        logger.debug(
            f"Send command - synchronize time zone={i8}, daylight saving time={i9} week={i4}, day:{
            i3}, month:{i2}, hours:{i5}, minutes:{i6}, seconds:{i7}, year={i}",
            "Time synchronization",
            True,
        )
        return self.send_order_msg_sys(build)

    def get_device_version_info(self):
        return self.send_order_msg_sys(MctlSys(todev_get_dev_fw_info=1))

    # === sendOrderMsg_Sys2 ===

    def request_iot_sys(
        self,
        rpt_act: RptAct,
        rpt_info_type: list[RptInfoType | str] | None,
        timeout: int,
        period: int,
        no_change_period: int,
        count: int,
    ) -> bytes:
        build = MctlSys(
            todev_report_cfg=ReportInfoCfg(
                act=rpt_act,
                sub=rpt_info_type,
                timeout=timeout,
                period=period,
                no_change_period=no_change_period,
                count=count,
            )
        )
        logger.debug(f"Send command==== IOT slim data Act {
            build.todev_report_cfg.act} {build}")
        return self.send_order_msg_sys_legacy(build)

    def get_report_cfg_stop(self, timeout: int = 10000, period: int = 1000, no_change_period: int = 1000):
        # TODO use send_order_msg_sys_legacy
        mctlsys = MctlSys(
            todev_report_cfg=ReportInfoCfg(
                act=RptAct.RPT_STOP,
                timeout=timeout,
                period=period,
                no_change_period=no_change_period,
                count=1,
            )
        )

        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_CONNECT)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_RTK)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_DEV_LOCAL)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_WORK)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_DEV_STA)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_MAINTAIN)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_VISION_POINT)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_VIO)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_VISION_STATISTIC)

        lubaMsg = LubaMsg()
        lubaMsg.msgtype = MsgCmdType.MSG_CMD_TYPE_EMBED_SYS
        lubaMsg.sender = MsgDevice.DEV_MOBILEAPP
        lubaMsg.rcver = MsgDevice.DEV_MAINCTL
        lubaMsg.msgattr = MsgAttr.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.sys = mctlsys
        return lubaMsg.SerializeToString()

    def get_report_cfg(self, timeout: int = 10000, period: int = 1000, no_change_period: int = 2000):
        # TODO use send_order_msg_sys_legacy
        mctlsys = MctlSys(
            todev_report_cfg=ReportInfoCfg(
                act=RptAct.RPT_START,
                timeout=timeout,
                period=period,
                no_change_period=no_change_period,
                count=1,
            )
        )

        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_CONNECT)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_RTK)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_DEV_LOCAL)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_WORK)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_DEV_STA)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_MAINTAIN)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_VISION_POINT)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_VIO)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_VISION_STATISTIC)
        mctlsys.todev_report_cfg.sub.append(RptInfoType.RIT_BASESTATION_INFO)

        lubaMsg = LubaMsg()
        lubaMsg.msgtype = MsgCmdType.MSG_CMD_TYPE_EMBED_SYS
        lubaMsg.sender = MsgDevice.DEV_MOBILEAPP
        lubaMsg.rcver = MsgDevice.DEV_MAINCTL
        lubaMsg.msgattr = MsgAttr.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.sys = mctlsys
        return lubaMsg.SerializeToString()
