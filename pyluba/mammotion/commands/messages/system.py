# === sendOrderMsg_Sys ===
import datetime
from typing import List
from pyluba.mammotion.commands.abstract_message import AbstractMessage
from pyluba.mammotion.commands.messages.navigation import MessageNavigation
from pyluba.proto import luba_msg_pb2, mctrl_sys_pb2
from pyluba.proto.mctrl_sys import RptInfoType
from pyluba.utility.device_type import DeviceType


class MessageSystem(AbstractMessage):
    messageNavigation: MessageNavigation = MessageNavigation()

    def send_order_msg_sys(self, sys):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MSG_CMD_TYPE_EMBED_SYS,
            sender=luba_msg_pb2.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.DEV_MAINCTL,
            sys=sys
        )

        return luba_msg.SerializeToString()

    def reset_system(self):
        build = mctrl_sys_pb2.MctlSys(todev_reset_system=1)
        print("Send command - send factory reset")
        return self.send_order_msg_sys(build)


    async def set_blade_control(self, on_off: int):
        mctlsys = mctrl_sys_pb2.MctlSys()
        sysKnifeControl = mctrl_sys_pb2.SysKnifeControl()
        sysKnifeControl.knife_status = on_off
        mctlsys.todev_knife_ctrl.CopyFrom(sysKnifeControl)

        return self.send_order_msg_sys(mctlsys)

    def get_device_product_model(self):
        return self.send_order_msg_sys(mctrl_sys_pb2.MctlSys(device_product_type_info=mctrl_sys_pb2.device_product_type_info_t()), 12, True)

    def read_and_set_sidelight(self, is_sidelight: bool, operate: int):
        if is_sidelight:
            build = mctrl_sys_pb2.TimeCtrlLight(
                operate=operate, enable=0, action=0, start_hour=0, start_min=0, end_hour=0, end_min=0)
        else:
            build = mctrl_sys_pb2.TimeCtrlLight(
                operate=operate, enable=1, action=0, start_hour=0, start_min=0, end_hour=0, end_min=0)
        print(f"Send read and write sidelight command is_sidelight:{
            is_sidelight}, operate:{operate}")
        build2 = mctrl_sys_pb2.MctlSys(todev_time_ctrl_light=build)
        print(f"Send command - send read and write sidelight command is_sidelight:{
            is_sidelight}, operate:{operate}, timeCtrlLight:{build}")
        return self.send_order_msg_sys(build2)

    def test_tool_order_to_sys(self, sub_cmd: int, param_id: int, param_value: List[int]):
        build = mctrl_sys_pb2.mCtrlSimulationCmdData(
            sub_cmd=sub_cmd, param_id=param_id, param_value=param_value)
        print(f"Send tool test command: subCmd={sub_cmd}, param_id:{
            param_id}, param_value={param_value}")
        build2 = mctrl_sys_pb2.MctlSys(simulation_cmd=build)
        print(f"Send tool test command: subCmd={sub_cmd}, param_id:{
            param_id}, param_value={param_value}")
        return self.send_order_msg_sys(build2)

    def read_and_set_rt_k_paring_code(self, op: int, cgf: str):
        print(f"Send read and write base station configuration quality op:{
            op}, cgf:{cgf}")
        return self.send_order_msg_sys(mctrl_sys_pb2.MctlSys(todev_lora_cfg_req=mctrl_sys_pb2.LoraCfgReq(op=op, cfg=cgf)))

    def allpowerfull_rw(self, id: int, context: int, rw: int):
        if (id == 6 or id == 3 or id == 7) and DeviceType.is_luba_2(self.get_device_name()):
            self.messageNavigation.allpowerfull_rw_adapter_x3(id, context, rw)
            return
        build = mctrl_sys_pb2.MctlSys(
            bidire_comm_cmd=mctrl_sys_pb2.SysCommCmd(id=id, context=context, rw=rw))
        print(
            f"Send command - 9 general read and write command id={id}, context={context}, rw={rw}")
        if id == 5:
            # This logic doesnt make snese, but its what they had so..
            return self.send_order_msg_sys(build)
        return self.send_order_msg_sys(build)

    # Commented out as not needed and too many refs to try fix up
    # def factory_test_order(self, test_id: int, test_duration: int, expect: str):
    #     new_builder = mctrl_sys_pb2.mow_to_app_qctools_info_t.Builder()
    #     print(f"Factory tool print, expect={expect}")
    #     if not expect:
    #         build = new_builder.set_type_value(
    #             test_id).set_time_of_duration(test_duration).build()
    #     else:
    #         try:
    #             json_array = json.loads(expect)
    #             z2 = True
    #             for i in range(len(json_array)):
    #                 new_builder2 = mctrl_sys_pb2.QCAppTestExcept.Builder()
    #                 json_object = json_array[i]
    #                 if "except_type" in json_object:
    #                     string = json_object["except_type"]
    #                     if "conditions" in json_object:
    #                         json_array2 = json_object["conditions"]
    #                         for i2 in range(len(json_array2)):
    #                             json_object2 = json_array2[i2]
    #                             new_builder3 = mctrl_sys_pb2.QCAppTestConditions.Builder()
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
    #     print(f"Factory tool print, mow_to_app_qctools_info_t={
    #         build.except_count}, mow_to_app_qctools_info_t22={build.except_list}")
    #     build2 = mctrl_sys_pb2.MctlSys(mow_to_app_qctools_info=build)
    #     print(f"Send command - factory tool test command testId={
    #         test_id}, testDuration={test_duration}", "Factory tool print222", True)
    #     return self.send_order_msg_sys(build2)

    def send_sys_set_date_time(self):
        calendar = datetime.now()
        i = calendar.year
        i2 = calendar.month
        i3 = calendar.day
        i4 = calendar.isoweekday()
        i5 = calendar.hour
        i6 = calendar.minute
        i7 = calendar.second
        i8 = calendar.utcoffset().total_seconds() // 60 if calendar.utcoffset() else 0
        i9 = 1 if calendar.dst() else 0
        print(f"Print time zone, time zone={
            i8}, daylight saving time={i9} week={i4}")
        build = mctrl_sys_pb2.MctlSys(todev_data_time=mctrl_sys_pb2.SysSetDateTime(
            year=i, month=i2, date=i3, week=i4, hours=i5, minutes=i6, seconds=i7, time_zone=i8, daylight=i9))
        print(f"Send command - synchronize time zone={i8}, daylight saving time={i9} week={i4}, day:{
            i3}, month:{i2}, hours:{i5}, minutes:{i6}, seconds:{i7}, year={i}", "Time synchronization", True)
        return self.send_order_msg_sys(build)

    def get_device_version_info(self):
        return self.send_order_msg_sys(mctrl_sys_pb2.MctlSys(todev_get_dev_fw_info=1))

    # === sendOrderMsg_Sys2 ===

    def request_iot_sys(self, rpt_act: mctrl_sys_pb2.rpt_act, rpt_info_type: List[int], timeout: int, period: int, no_change_period: int, count: int) -> None:
        build = mctrl_sys_pb2.MctlSys(todev_report_cfg=mctrl_sys_pb2.report_info_cfg(
            rpt_act=rpt_act,
            rpt_info_type=rpt_info_type,
            timeout=timeout,
            period=period,
            no_change_period=no_change_period,
            count=count
        ))
        print(f"Send command==== IOT slim data Act {
            build.todev_report_cfg.act} {build}")
        return self.send_order_msg_sys(build)



    def get_report_cfg(self, timeout: int = 10000, period: int = 1000, no_change_period: int = 2000):
        mctlsys = mctrl_sys_pb2.MctlSys(
            todev_report_cfg=mctrl_sys_pb2.report_info_cfg(
                timeout=timeout,
                period=period,
                no_change_period=no_change_period,
                count=1
            )
        )

        mctlsys.todev_report_cfg.sub.append(
            RptInfoType.RIT_CONNECT.value
        )
        mctlsys.todev_report_cfg.sub.append(
            RptInfoType.RIT_RTK.value
        )
        mctlsys.todev_report_cfg.sub.append(
            RptInfoType.RIT_DEV_LOCAL.value
        )
        mctlsys.todev_report_cfg.sub.append(
            RptInfoType.RIT_WORK.value
        )
        mctlsys.todev_report_cfg.sub.append(
            RptInfoType.RIT_DEV_STA.value
        )
        mctlsys.todev_report_cfg.sub.append(
            RptInfoType.RIT_VISION_POINT.value
        )
        mctlsys.todev_report_cfg.sub.append(
            RptInfoType.RIT_VIO.value
        )
        mctlsys.todev_report_cfg.sub.append(
            RptInfoType.RIT_VISION_STATISTIC.value
        )

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_EMBED_SYS
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.DEV_MAINCTL
        lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.sys.CopyFrom(mctlsys)
        return lubaMsg.SerializeToString()
