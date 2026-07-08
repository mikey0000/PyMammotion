# === sendOrderMsg_Sys ===
from abc import ABC
import dataclasses
import datetime
import time

from pymammotion import logger
from pymammotion.data.model.pool_state import PoolPlan
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
    FileTransferResponse,
    FileTransferResult,
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
    PlanJobSet,
    PoolBottomTypeE,
    QcAppTestId,
    RemoteResetReqT,
    ReportInfoCfg,
    RptAct,
    RptInfoType,
    RtkUsedType,
    SpinoCtrl,
    SysCommCmd,
    SysKnifeControl,
    SysSetDateTime,
    TaskReportInteractionT,
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
        mctlsys = MctlSys(blade_used_warn_time=UserSetBladeUsedWarnTime(blade_used_warn_time=seconds))
        logger.debug(f"Send command - set blade replacement warning time: hours={hours}, seconds={seconds}")
        return self.send_order_msg_sys(mctlsys)

    def get_device_product_model(self) -> bytes:
        """Request the device product type and model information."""
        return self.send_order_msg_sys(MctlSys(device_product_type_info=DeviceProductTypeInfoT(result=1)))

    def read_and_set_sidelight(self, is_sidelight: bool, operate: int) -> bytes:
        """Read or set the side LED.

        is_sidelight=True  → enable=0 (light on)
        is_sidelight=False → enable=1 (light off)
        operate=0 → write (set), operate=1 → read (query current state).
        """
        build = TimeCtrlLight(
            operate=operate,
            enable=0 if is_sidelight else 1,
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

    def allpowerfull_rw(self, rw_id: int, context: int, rw: int) -> bytes:
        """Send a general-purpose bidirectional read/write command to the device by ID, context, and direction."""
        build = MctlSys(bidire_comm_cmd=SysCommCmd(id=rw_id, context=context, rw=rw))
        logger.debug(f"Send command - 9 general read and write command id={rw_id}, context={context}, rw={rw}")
        return self.send_order_msg_sys(build)

    def send_sys_set_date_time(self) -> bytes:
        """Synchronize the device clock with the current local date, time, timezone, and DST settings."""
        # astimezone() makes the datetime timezone-aware — a naive now() always
        # reports utcoffset()/dst() as None, silently sending timezone 0 / DST 0.
        calendar = datetime.datetime.now().astimezone()
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
                time_zone=int(i8),
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
        rpt_info_type: list[RptInfoType],
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
        logger.debug(f"Send command==== IOT slim data Act {build.todev_report_cfg.act}")  # type: ignore
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
        report_cfg = ReportInfoCfg(
            act=RptAct.RPT_STOP,
            timeout=timeout,
            period=period,
            no_change_period=no_change_period,
            count=0,
        )
        report_cfg.sub.append(RptInfoType.RIT_CONNECT)
        report_cfg.sub.append(RptInfoType.RIT_RTK)
        report_cfg.sub.append(RptInfoType.RIT_DEV_LOCAL)
        report_cfg.sub.append(RptInfoType.RIT_WORK)
        report_cfg.sub.append(RptInfoType.RIT_DEV_STA)
        report_cfg.sub.append(RptInfoType.RIT_VISION_POINT)
        report_cfg.sub.append(RptInfoType.RIT_VIO)
        report_cfg.sub.append(RptInfoType.RIT_VISION_STATISTIC)
        mctl_sys = MctlSys(todev_report_cfg=report_cfg)

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
        no_change_period: int = 4000,
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
        report_cfg = ReportInfoCfg(
            act=RptAct.RPT_START,
            timeout=timeout,
            period=period,
            no_change_period=no_change_period,
            count=count,
        )
        report_cfg.sub.append(RptInfoType.RIT_CONNECT)
        report_cfg.sub.append(RptInfoType.RIT_RTK)
        report_cfg.sub.append(RptInfoType.RIT_DEV_LOCAL)
        report_cfg.sub.append(RptInfoType.RIT_WORK)
        report_cfg.sub.append(RptInfoType.RIT_DEV_STA)
        report_cfg.sub.append(RptInfoType.RIT_VISION_POINT)
        report_cfg.sub.append(RptInfoType.RIT_VIO)
        report_cfg.sub.append(RptInfoType.RIT_VISION_STATISTIC)
        report_cfg.sub.append(RptInfoType.RIT_BASESTATION_INFO)
        report_cfg.sub.append(RptInfoType.RIT_FW_INFO)
        mctl_sys = MctlSys(todev_report_cfg=report_cfg)

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

    def get_report_cfg_spino(
        self,
        count: int = 1,
        timeout: int = 10000,
        period: int = 1000,
        no_change_period: int = 4000,
    ) -> bytes:
        """Start status reporting for a Spino pool cleaner.

        Pool cleaners only surface ``RIT_DEV_STA`` (``dev_statue_t`` → sys_status
        / work_mode / battery, applied by ``PoolStateReducer``) plus
        ``RIT_CONNECT`` for connectivity.  The mower-only channels (RTK, WORK,
        VISION, BASESTATION, …) don't apply, so the subscription is deliberately
        minimal — this mirrors the APK's ``requestHomeConnectStatus``
        (``{RIT_CONNECT, RIT_DEV_STA}``).

        ``count=0`` streams continuously until ``get_report_cfg_stop``; the
        default ``count=1`` is a one-shot poll (used by the refresh-status
        button). See :meth:`get_report_cfg` for the full field reference.
        """
        report_cfg = ReportInfoCfg(
            act=RptAct.RPT_START,
            timeout=timeout,
            period=period,
            no_change_period=no_change_period,
            count=count,
        )
        report_cfg.sub.append(RptInfoType.RIT_CONNECT)
        report_cfg.sub.append(RptInfoType.RIT_DEV_STA)
        mctl_sys = MctlSys(todev_report_cfg=report_cfg)

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
            force_reset: Force reset flag.
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

    # === Work report ===

    def send_receive_work_report(self, cmd: int = 0) -> bytes:
        """Signal the device that the app is ready to receive a work-session report.

        Sent before the device begins transmitting the report payload.
        ``cmd`` is an optional sub-command code (default 0).
        """
        build = MctlSys(task_report_interaction=TaskReportInteractionT(cmd=cmd))
        logger.debug("Send command - Ready to receive work report")
        return self.send_order_msg_sys(build)

    def send_complete_report(self, biz_id: str, result: int) -> bytes:
        """Acknowledge receipt of a complete work-session report.

        ``biz_id`` is the business-transaction identifier returned by the device
        in the report header.  ``result`` is 0 for success, non-zero for error.
        """
        build = MctlSys(task_report_result=FileTransferResult(biz_id=biz_id, result=result))
        logger.debug(f"Send command - Complete report biz_id={biz_id}, result={result}")
        return self.send_order_msg_sys(build)

    def send_confirm_report(self, biz_id: str, result: int, progress: int) -> bytes:
        """Confirm a partial or complete report transfer frame.

        ``biz_id`` identifies the transfer session; ``result`` is the per-frame
        error code (0 = OK); ``progress`` is the transfer progress percentage.
        """
        build = MctlSys(task_report_resp=FileTransferResponse(biz_id=biz_id, result=result, progress=progress))
        logger.debug(f"Send command - Confirm report biz_id={biz_id}, result={result}, progress={progress}")
        return self.send_order_msg_sys(build)

    # ==================================================================
    # Spino schedule plan CRUD — wraps ``SpinoCtrl(plan_job_set=...)``
    # in ``LubaMsg.ctrl`` (msgtype = MSG_CMD_TYPE_SPINO_CTRL).  See
    # ``docs/tasks_and_schedules.md`` § 2 for the wire protocol.
    # ==================================================================

    def send_order_spino_ctrl(self, ctrl: SpinoCtrl) -> bytes:
        """Serialise a ``SpinoCtrl`` payload as a LubaMsg request (msgtype=253).

        Mirrors the APK helper ``sendOrderSpino_Ctrl``
        (``command/app/MACommandApiHelper.java:342-345``) — the Spino plan
        path uses its own envelope distinct from ``EMBED_SYS``.
        """
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.SPINO_CTRL,
            msgattr=MsgAttr.REQ,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=MsgDevice.DEV_MAINCTL,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            ctrl=ctrl,
            timestamp=round(time.time() * 1000),
        )
        return bytes(luba_msg.SerializeToString())

    @staticmethod
    def _pool_plan_to_proto(plan: PoolPlan, cmd: int) -> PlanJobSet:
        """Encode a ``PoolPlan`` to the wire proto with the right ``cmd``.

        Crucially, the wire ``enable`` field is INVERTED: ``0 == enabled,
        1 == disabled``.  Keep that inversion strictly inside this helper
        so ``PoolPlan.enabled`` is a natural ``bool`` everywhere else.
        """
        return PlanJobSet(
            cmd=cmd,
            work_mode=plan.work_mode,
            sub_mode=list(plan.sub_mode),
            userid=plan.userid,
            deviceid=plan.deviceid,
            starttime=plan.starttime,
            totalplannum=plan.totalplannum,
            planindex=plan.planindex,
            result=plan.result,
            speed=plan.speed,
            operating_power=plan.operating_power,
            jobname=plan.jobname,
            jobid=plan.jobid,
            startdate=plan.startdate,
            enddate=plan.enddate,
            triggertype=plan.triggertype,
            day=plan.day,
            weeks=list(plan.weeks),
            remained_seconds=plan.remained_seconds,
            enable=0 if plan.enabled else 1,
        )

    def _send_spino_plan(self, plan: PoolPlan, cmd: int) -> bytes:
        """Internal: build a full-plan SpinoCtrl frame with the given ``cmd``."""
        wire = self._pool_plan_to_proto(plan, cmd)
        return self.send_order_spino_ctrl(SpinoCtrl(plan_job_set=wire))

    def read_spino_plan(self, plan_index: int = 0) -> bytes:
        """Read one Spino plan by index (``cmd = QUERY = 2``).

        The fetch saga loops ``plan_index`` 0..total_plan_num−1; the device
        replies with one ``plan_job_set`` per index.
        """
        return self.send_order_spino_ctrl(
            SpinoCtrl(plan_job_set=PlanJobSet(cmd=2, planindex=plan_index)),
        )

    def create_spino_plan(self, plan: PoolPlan) -> bytes:
        """Create a new Spino plan (``cmd = ADD = 1``).

        ``plan.jobid`` MUST be a fresh 64-bit id — re-using an existing
        jobid would be treated as an edit by the device.
        """
        return self._send_spino_plan(plan, cmd=1)

    def edit_spino_plan(self, plan: PoolPlan) -> bytes:
        """Edit an existing Spino plan (``cmd = EDIT = 4``)."""
        return self._send_spino_plan(plan, cmd=4)

    def delete_spino_plan(self, jobid: int) -> bytes:
        """Delete the Spino plan identified by ``jobid`` (``cmd = DELETE = 3``)."""
        return self.send_order_spino_ctrl(
            SpinoCtrl(plan_job_set=PlanJobSet(cmd=3, jobid=jobid)),
        )

    def delete_all_spino_plans(self) -> bytes:
        """Wipe every Spino plan on the device (``cmd = DELETE_ALL = 5``)."""
        return self.send_order_spino_ctrl(
            SpinoCtrl(plan_job_set=PlanJobSet(cmd=5)),
        )

    def enable_spino_plan(self, plan: PoolPlan, enabled: bool) -> bytes:
        """Toggle a Spino plan's enable flag (resent as ``cmd = EDIT = 4``)."""
        return self.edit_spino_plan(plan.with_enabled(enabled))

    def rename_spino_plan(self, plan: PoolPlan, new_name: str) -> bytes:
        """Rename a Spino plan (resent as ``cmd = EDIT = 4``)."""
        return self.edit_spino_plan(plan.with_renamed(new_name))

    def copy_spino_plan(self, plan: PoolPlan, new_name: str, new_jobid: int) -> bytes:
        """Duplicate *plan* under a new jobid + name (``cmd = ADD = 1``).

        Caller supplies ``new_jobid`` (a fresh 64-bit int — generate with
        ``secrets.randbits(63) | 1``) and ``new_name`` (e.g. via
        :func:`pymammotion.utility.plan_id.make_copy_name`).
        """
        clone = dataclasses.replace(plan, jobid=new_jobid, jobname=new_name)
        return self.create_spino_plan(clone)
