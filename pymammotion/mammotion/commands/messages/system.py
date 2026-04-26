# === sendOrderMsg_Sys ===
from abc import ABC
import datetime
import time

from pymammotion import logger
from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import (
    AckToAppTypeE,
    AppDownlinkCmdT,
    AppDownlinkCmdTypeE,
    AppToDevSetMqttRtkT,
    DebugCfgWriteT,
    DebugEnableT,
    DebugResCfgAbilityT,
    DeviceProductTypeInfoT,
    LoraCfgReq,
    LubaMsg,
    MapInfo,
    MapPoints,
    MctlSys,
    MCtrlSimulationCmdData,
    MowToAppQctoolsInfoT,
    MsgAttr,
    MsgCmdType,
    MsgDevice,
    PoolBottomTypeE,
    QcAppTestId,
    RemoteResetReqT,
    ReportInfoCfg,
    RptAct,
    RptInfoType,
    RtkUsedType,
    SysCommCmd,
    SysKnifeControl,
    SysSetDateTime,
    TimeCtrlLight,
    UserSetBladeUsedWarnTime,
    WallMaterialE,
    WorkModeT,
)


class MessageSystem(AbstractMessage, ABC):
    """Mixin that builds and serialises system protobuf command messages (reset, clock, reporting, RTK)."""

    def send_order_msg_sys(self, sys: MctlSys) -> bytes:
        """Serialize a system (MctlSys) payload into a LubaMsg request frame targeting the main controller."""
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.EMBED_SYS,
            msgattr=MsgAttr.REQ,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.EMBED_SYS, MsgDevice.DEV_MAINCTL),
            sys=sys,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            timestamp=round(time.time() * 1000),
        )

        return bytes(luba_msg.SerializeToString())

    def send_order_msg_sys_legacy(self, sys: MctlSys) -> bytes:
        """Serialize a system payload into a LubaMsg frame using the legacy fixed receiver address."""
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.EMBED_SYS,
            msgattr=MsgAttr.REQ,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=MsgDevice.DEV_MAINCTL,
            sys=sys,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            timestamp=round(time.time() * 1000),
        )

        return bytes(luba_msg.SerializeToString())

    def reset_system(self) -> bytes:
        """Send a factory reset command to the device."""
        build = MctlSys(todev_reset_system=1)
        logger.debug("Send command - send factory reset")
        return self.send_order_msg_sys(build)

    def set_blade_control(self, on_off: int) -> bytes:
        """Send a command to turn the cutting blade on or off."""
        mctlsys = MctlSys()
        sys_knife_control = SysKnifeControl()
        sys_knife_control.knife_status = on_off
        mctlsys.todev_knife_ctrl = sys_knife_control

        return self.send_order_msg_sys(mctlsys)

    def reset_blade_time(self) -> bytes:
        """Reset the usage time of the blade.

        Returns:
            bytes: Serialized command for resetting the blade usage time.

        """
        build = MctlSys(todev_reset_blade_used_time=1)
        logger.debug("Send command - reset blade usage time")
        return self.send_order_msg_sys(build)

    def set_blade_warning_time(self, hours: int) -> bytes:
        """Set blade replacement warning time in hours.

        Args:
            hours (int): The warning time in hours.

        Returns:
            bytes: Serialized command for setting the blade warning time.

        """
        seconds = hours * 3600  # Convert hours to seconds
        mctlsys = MctlSys()
        build = mctlsys.blade_used_warn_time = UserSetBladeUsedWarnTime(blade_used_warn_time=seconds)
        logger.debug(f"Send command - set blade replacement warning time: hours={hours}, seconds={seconds}")
        return self.send_order_msg_sys(build)

    def get_device_product_model(self) -> bytes:
        """Request the device product type and model information."""
        return self.send_order_msg_sys(MctlSys(device_product_type_info=DeviceProductTypeInfoT(result=1)))

    def read_and_set_sidelight(self, is_sidelight: bool, operate: int) -> bytes:
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
        logger.debug(f"Send read and write sidelight command is_sidelight:{is_sidelight}, operate:{operate}")
        build2 = MctlSys(todev_time_ctrl_light=build)
        logger.debug(
            f"Send command - send read and write sidelight command is_sidelight:{is_sidelight}, operate:{
                operate
            }, timeCtrlLight:{build}"
        )
        return self.send_order_msg_sys(build2)

    def test_tool_order_to_sys(self, sub_cmd: int, param_id: int, param_value: list[int]) -> bytes:
        """Send a simulation/test tool command with a sub-command ID, parameter ID, and parameter values."""
        build = MCtrlSimulationCmdData(sub_cmd=sub_cmd, param_id=param_id, param_value=param_value)
        logger.debug(f"Send tool test command: subCmd={sub_cmd}, param_id:{param_id}, param_value={param_value}")
        build2 = MctlSys(simulation_cmd=build)
        logger.debug(f"Send tool test command: subCmd={sub_cmd}, param_id:{param_id}, param_value={param_value}")
        return self.send_order_msg_sys(build2)

    def read_and_set_rtk_paring_code(self, op: int, cgf: str | None = None) -> bytes:
        """Read or write the RTK base station LoRa pairing code configuration."""
        logger.debug(f"Send read and write base station configuration quality op:{op}, cgf:{cgf}")
        return self.send_order_msg_sys(MctlSys(todev_lora_cfg_req=LoraCfgReq(op=op, cfg=cgf)))

    def allpowerfull_rw(self, rw_id: int, context: int, rw: int) -> bytes:
        """Send a general-purpose bidirectional read/write command to the device by ID, context, and direction."""
        build = MctlSys(bidire_comm_cmd=SysCommCmd(id=rw_id, context=context, rw=rw))
        logger.debug(f"Send command - 9 general read and write command id={rw_id}, context={context}, rw={rw}")
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

    def send_sys_set_date_time(self) -> bytes:
        """Synchronize the device clock with the current local date, time, timezone, and DST settings."""
        # TODO get HA timezone
        calendar = datetime.datetime.now()
        i = calendar.year
        i2 = calendar.month
        i3 = calendar.day
        i4 = calendar.isoweekday()
        i5 = calendar.hour
        i6 = calendar.minute
        i7 = calendar.second
        _utcoffset = calendar.utcoffset()
        i8 = _utcoffset.total_seconds() // 60 if _utcoffset is not None else 0
        i9 = 1 if calendar.dst() else 0
        logger.debug(f"Print time zone, time zone={i8}, daylight saving time={i9} week={i4}")
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
            f"Send command - synchronize time zone={i8}, daylight saving time={i9} week={i4}, day:{i3}, month:{
                i2
            }, hours:{i5}, minutes:{i6}, seconds:{i7}, year={i}",
            "Time synchronization",
            True,
        )
        return self.send_order_msg_sys(build)

    def get_device_version_info(self) -> bytes:
        """Request the device firmware version information."""
        return self.send_order_msg_sys(MctlSys(todev_get_dev_fw_info=1))

    def read_and_set_rtk_pairing_code(self, op: int, cfg: str) -> bytes:
        """Read or write the RTK base station LoRa pairing configuration string."""
        return self.send_order_msg_sys(MctlSys(todev_lora_cfg_req=LoraCfgReq(op=op, cfg=cfg)))

    # === sendOrderMsg_Sys2 ===

    def request_iot_sys(
        self,
        rpt_act: RptAct,
        rpt_info_type: list[RptInfoType | str] | None,
        timeout: int = 10000,
        period: int = 1000,
        no_change_period: int = 1000,
        count: int = 1,
    ) -> bytes:
        """Configure the device IoT reporting subscription with the given action, info types, and timing parameters."""
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
        logger.debug(f"Send command==== IOT slim data Act {build.todev_report_cfg.act}")
        return self.send_order_msg_sys_legacy(build)

    def get_maintenance(self) -> bytes:
        """Request maintenance-related reports including blade info, base station info, and firmware info."""
        return self.request_iot_sys(
            rpt_act=RptAct.RPT_START,
            rpt_info_type=[
                RptInfoType.RIT_MAINTAIN,
                RptInfoType.RIT_BASESTATION_INFO,
                RptInfoType.RIT_FW_INFO,
            ],
            timeout=1000,
            period=1000,
            no_change_period=2000,
            count=3,
        )

    def get_report_cfg_stop(self, timeout: int = 10000, period: int = 1000, no_change_period: int = 1000) -> bytes:
        """Send a command to stop all active IoT status reporting subscriptions on the device."""
        # TODO use send_order_msg_sys_legacy
        mctl_sys = MctlSys(
            todev_report_cfg=ReportInfoCfg(
                act=RptAct.RPT_STOP,
                timeout=timeout,
                period=period,
                no_change_period=no_change_period,
                count=1,
            )
        )

        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_CONNECT)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_RTK)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_DEV_LOCAL)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_WORK)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_DEV_STA)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_VISION_POINT)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_VIO)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_VISION_STATISTIC)

        luba_msg = LubaMsg(
            msgtype=MsgCmdType.EMBED_SYS,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=MsgDevice.DEV_MAINCTL,
            msgattr=MsgAttr.REQ,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            sys=mctl_sys,
            timestamp=round(time.time() * 1000),
        )

        return bytes(luba_msg.SerializeToString())

    def get_report_cfg(
        self,
        timeout: int = 10000,
        period: int = 1000,
        no_change_period: int = 2000,
        count: int = 1,
    ) -> bytes:
        """Start full-status IoT reporting covering connectivity, RTK, work, vision, and base station info.

        Wraps the ``todev_report_cfg`` (``ReportInfoCfg``) protobuf sent to the
        device.  Field mapping (from ``MctrlSys.java`` in the APK):

        ============================  =========================================
        Field                          Purpose
        ============================  =========================================
        ``act``                        ``RPT_START`` (0) to begin reporting,
                                       ``RPT_STOP`` (1) to end it.
        ``timeout``                    Request timeout in milliseconds.  The
                                       device drops the subscription if no new
                                       config arrives within this window.
        ``period``                     Interval between reports in ms.  Lower
                                       = faster updates (e.g. 250 ms → 4 Hz).
        ``no_change_period``           Report interval in ms when the data
                                       hasn't changed.  Keeps a heartbeat alive
                                       without spamming identical payloads.
        ``count``                      Number of reports before auto-stop.
                                       ``1`` = one-shot poll (default, matches
                                       ``homeassistant/mower_api.py`` usage).
                                       ``0`` = continuous stream until
                                       ``get_report_cfg_stop`` is sent — use
                                       this for a live view.
        ``sub``                        Repeated ``rpt_info_type`` list selecting
                                       which report channels to subscribe to.
                                       Populated below: ``RIT_CONNECT``,
                                       ``RIT_RTK``, ``RIT_DEV_LOCAL``,
                                       ``RIT_WORK``, ``RIT_DEV_STA``,
                                       ``RIT_VISION_POINT``, ``RIT_VIO``,
                                       ``RIT_VISION_STATISTIC``,
                                       ``RIT_BASESTATION_INFO``.
        ============================  =========================================

        The ~4 Hz ``system_tard_state_tunnel`` frames observed during active
        mowing are a separate always-on channel (not controlled by this cfg).
        """
        # TODO use send_order_msg_sys_legacy
        mctl_sys = MctlSys(
            todev_report_cfg=ReportInfoCfg(
                act=RptAct.RPT_START,
                timeout=timeout,
                period=period,
                no_change_period=no_change_period,
                count=count,
            )
        )

        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_CONNECT)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_RTK)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_DEV_LOCAL)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_WORK)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_DEV_STA)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_VISION_POINT)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_VIO)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_VISION_STATISTIC)
        mctl_sys.todev_report_cfg.sub.append(RptInfoType.RIT_BASESTATION_INFO)

        luba_msg = LubaMsg(
            msgtype=MsgCmdType.EMBED_SYS,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=MsgDevice.DEV_MAINCTL,
            msgattr=MsgAttr.REQ,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            sys=mctl_sys,
            timestamp=round(time.time() * 1000),
        )
        return bytes(luba_msg.SerializeToString())

    def remote_restart(self, force_reset: int = 1) -> bytes:
        """Send a remote restart command.
        force_reset: 0 - normal restart, 1 - force restart
        Args:
            force_reset: Force reset flag
        """
        mctl_sys = MctlSys(
            to_dev_remote_reset=RemoteResetReqT(
                magic=1916956532,
                bizid=round(time.time() * 1000),
                reset_mode=0,
                force_reset=force_reset,
                account=self.user_account,
            )
        )
        logger.debug(f"Send command - remote restart command status={force_reset}")
        return self.send_order_msg_sys(mctl_sys)

    # === iNavi / Network RTK link mode ===

    def cancel_inavi_calibration(self) -> bytes:
        """Cancel iNavi (network RTK) calibration in progress."""
        build = MctlSys(app_to_dev_set_mqtt_rtk_msg=AppToDevSetMqttRtkT(stop_nrtk_flag=1))
        logger.debug("Send command - Cancel iNavi calibration")
        return self.send_order_msg_sys(build)

    def set_inavi_net_connect_type(self, mode: int) -> bytes:
        """Set network type used by iNavi (0=WiFi, 1=4G, etc.)."""
        build = MctlSys(app_to_dev_set_mqtt_rtk_msg=AppToDevSetMqttRtkT(set_nrtk_net_mode=mode))
        logger.debug(f"Send command - Set iNavi network connect type mode={mode}")
        return self.send_order_msg_sys(build)

    def set_net_rtk_link_mode(self, mode: int) -> bytes:
        """Set RTK link channel. mode: 0=LoRa data transmission, 1=network, 2=nRTK."""
        build = MctlSys(app_to_dev_set_mqtt_rtk_msg=AppToDevSetMqttRtkT(set_rtk_mode=RtkUsedType(mode)))
        logger.debug(f"Send command - Set network RTK link mode mode={mode}")
        return self.send_order_msg_sys(build)

    # === Debug configuration ===

    def set_debug_enable(self, enable: int) -> bytes:
        """Set global debug switch (0=off, 1=on)."""
        build = MctlSys(debug_enable=DebugEnableT(enbale=enable))
        logger.debug(f"Send command - Set debug enable={enable}")
        return self.send_order_msg_sys(build)

    def set_debug_config(self, key: str, value: str) -> bytes:
        """Write a single debug configuration key/value pair."""
        build = MctlSys(debug_cfg_write=DebugCfgWriteT(key=key, value=value))
        logger.debug(f"Send command - Set debug config key={key}")
        return self.send_order_msg_sys(build)

    def set_all_debug_config(self) -> bytes:
        """Read/reset all debug configuration entries."""
        build = MctlSys(debug_res_cfg_ability=DebugResCfgAbilityT(total_keys=0, cur_key_id=-1, value="", keys=""))
        logger.debug("Send command - Read/reset all debug config")
        return self.send_order_msg_sys(build)

    # === Factory test ===

    def send_factory_test_complete(self, result: int) -> bytes:
        """Signal factory test completion with result status."""
        build = MctlSys(
            mow_to_app_qctools_info=MowToAppQctoolsInfoT(
                type=QcAppTestId.QC_APP_TEST_COMPLETE_SIGNAL,
                result=result,
            )
        )
        logger.debug(f"Send command - Factory test complete result={result}")
        return self.send_order_msg_sys(build)

    # === Swimming pool / Spino work mode ===

    def set_swimming_work_mode(self, work_mode: int) -> bytes:
        """Switch pool cleaner (Spino) work mode."""
        build = MctlSys(set_work_mode=WorkModeT(work_mode=work_mode))
        logger.debug(f"Send command - Set swimming work mode={work_mode}")
        return self.send_order_msg_sys(build)

    def get_sp_map(self) -> bytes:
        """Request swimming pool map from device (Spino)."""
        build = MctlSys(
            app_downlink_cmd=AppDownlinkCmdT(
                cmd=AppDownlinkCmdTypeE.app_get_map_cmd,
                ack=AckToAppTypeE.WAIT_ACK,
                map_info=MapInfo(
                    tag=1,
                    total_points=1,
                    pack_index=1,
                    pack_num=1,
                    points=[MapPoints(x=1.0, y=1.0)],
                ),
            )
        )
        logger.debug("Send command - Get swimming pool map")
        return self.send_order_msg_sys(build)

    def get_sp_line(self) -> bytes:
        """Request swimming pool route/line from device (Spino)."""
        build = MctlSys(
            app_downlink_cmd=AppDownlinkCmdT(
                cmd=AppDownlinkCmdTypeE.app_get_line_cmd,
                ack=AckToAppTypeE.WAIT_ACK,
                map_info=MapInfo(
                    tag=1,
                    total_points=1,
                    pack_index=1,
                    pack_num=1,
                    points=[MapPoints(x=1.0, y=1.0)],
                ),
            )
        )
        logger.debug("Send command - Get swimming pool route")
        return self.send_order_msg_sys(build)

    def sp_environment_update(self, material: WallMaterialE | int, is_query: bool = False) -> bytes:
        """Set or query pool wall material (Spino). is_query=True reads current value."""
        if is_query:
            build = MctlSys(
                app_downlink_cmd=AppDownlinkCmdT(
                    cmd=AppDownlinkCmdTypeE.app_wall_material_cmd,
                    ack=AckToAppTypeE.INQUIRY,
                    wall_material=1,
                )
            )
        else:
            build = MctlSys(
                app_downlink_cmd=AppDownlinkCmdT(
                    cmd=AppDownlinkCmdTypeE.app_wall_material_cmd,
                    ack=AckToAppTypeE.WAIT_ACK,
                    wall_material=int(material),
                )
            )
        logger.debug(f"Send command - SP environment update material={material}, query={is_query}")
        return self.send_order_msg_sys(build)

    def sp_speed_update(self, speed: float, is_query: bool = False) -> bytes:
        """Set or query pool floor cleaning speed (Spino). is_query=True reads current value."""
        if is_query:
            build = MctlSys(
                app_downlink_cmd=AppDownlinkCmdT(
                    cmd=AppDownlinkCmdTypeE.app_floor_speed_cmd,
                    ack=AckToAppTypeE.INQUIRY,
                    floor_speed=0.2,
                )
            )
        else:
            build = MctlSys(
                app_downlink_cmd=AppDownlinkCmdT(
                    cmd=AppDownlinkCmdTypeE.app_floor_speed_cmd,
                    ack=AckToAppTypeE.WAIT_ACK,
                    floor_speed=speed,
                )
            )
        logger.debug(f"Send command - SP speed update speed={speed}, query={is_query}")
        return self.send_order_msg_sys(build)

    def sp_set_bottom_type(self, bottom_type: PoolBottomTypeE | int, is_query: bool = False) -> bytes:
        """Set or query pool bottom shape type (Spino). is_query=True reads current value."""
        if is_query:
            build = MctlSys(
                app_downlink_cmd=AppDownlinkCmdT(
                    cmd=AppDownlinkCmdTypeE.app_bottom_type_cmd,
                    ack=AckToAppTypeE.INQUIRY,
                    bottom_type=PoolBottomTypeE.BOTTOM_RIGHT_ANGLE_SIMPLE_SHAPE,
                )
            )
        else:
            build = MctlSys(
                app_downlink_cmd=AppDownlinkCmdT(
                    cmd=AppDownlinkCmdTypeE.app_bottom_type_cmd,
                    ack=AckToAppTypeE.WAIT_ACK,
                    bottom_type=PoolBottomTypeE(int(bottom_type)),
                )
            )
        logger.debug(f"Send command - SP bottom type update bottom_type={bottom_type}, query={is_query}")
        return self.send_order_msg_sys(build)
