"""StateReducer — decodes LubaMsg and applies it to a MowingDevice copy."""

from __future__ import annotations

import copy
import dataclasses
import logging
from typing import TYPE_CHECKING

import betterproto2

from pymammotion.data.model.device_info import SideLight
from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    CommDataCouple,
    EdgePoints,
    MowPath,
    NavGetCommData,
    NavGetHashListData,
    Plan,
    SvgMessage,
)
from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.proto import (
    AppGetAllAreaHashName,
    AppGetCutterWorkMode,
    AppSetCutterWorkMode,
    CoverPathUploadT,
    DeviceFwInfo,
    DeviceProductTypeInfoT,
    DrvDevInfoResp,
    DrvDevInfoResult,
    DrvKnifeChangeReport,
    DrvSrSpeed,
    DrvUpgradeReport,
    Getlamprsp,
    GetMnetInfoRsp,
    GetNetworkInfoRsp,
    LoraCfgRsp,
    LubaMsg,
    MulSetAudio,
    NavEdgePoints,
    NavGetAllPlanTask,
    NavGetCommDataAck,
    NavGetHashListAck,
    NavPlanJobSet,
    NavReqCoverPath,
    NavSysParamMsg,
    NavUnableTimeSet,
    SvgMessageAckT,
    SysCommCmd,
    TimeCtrlLight,
    WifiIotStatusReport,
    WorkReportInfoAck,
)

if TYPE_CHECKING:
    from pymammotion.data.model.device import MowingDevice

_logger = logging.getLogger(__name__)


class StateReducer:
    """Decodes incoming LubaMsg bytes and applies them to a MowingDevice.

    Pure-ish: takes current MowingDevice, returns updated MowingDevice.
    Side-effect free except for logging.
    Does NOT fire any callbacks — broker request/response correlation handles that.
    """

    def apply(self, current: MowingDevice, message: LubaMsg) -> MowingDevice:
        """Apply a decoded LubaMsg to the current state, return updated state.

        Uses selective deep-copying: only the sub-trees that a given message type
        can modify are deep-copied. All other sub-objects are shared with ``current``
        via a shallow dataclasses.replace() copy, avoiding the cost of deep-copying
        the large map data (HashList with area/path/obstacle dicts) on every message.

        The hot path during mowing is ``system_tard_state_tunnel`` (rapid state,
        ~4x/sec). That message only touches ``mowing_state`` and ``location``, so
        the expensive ``map`` object is never deep-copied for those messages.

        Returns the updated copy regardless of whether anything changed.
        """
        res = betterproto2.which_one_of(message, "LubaSubMsg")
        sub_msg_type = res[0]

        # Shallow copy — all sub-objects are initially shared with current
        device: MowingDevice = dataclasses.replace(current)

        # Mark online on any incoming message
        if not device.online:
            device.online = True

        match sub_msg_type:
            case "nav":
                # nav messages may modify map, work, mower_state, non_work_hours,
                # and work_session_result — deep-copy all of those.
                device.map = copy.deepcopy(current.map)
                device.work = copy.deepcopy(current.work)
                device.mower_state = copy.deepcopy(current.mower_state)
                device.non_work_hours = copy.deepcopy(current.non_work_hours)
                device.work_session_result = copy.deepcopy(current.work_session_result)
                self._update_nav_data(device, message)

            case "sys":
                # Dispatch based on the inner sys sub-message to be more granular.
                # The most frequent message (system_tard_state_tunnel) only needs
                # mowing_state + location, so we avoid deep-copying report_data /
                # device_firmwares / events on those calls.
                sys_msg = betterproto2.which_one_of(message.sys, "SubSysMsg")
                match sys_msg[0]:
                    case "system_tard_state_tunnel":
                        # Hot path: ~4x/sec during mowing — minimal copy.
                        device.mowing_state = copy.deepcopy(current.mowing_state)
                        device.location = copy.deepcopy(current.location)
                    case "system_update_buf":
                        # Touches location and errors only.
                        device.location = copy.deepcopy(current.location)
                        device.errors = copy.deepcopy(current.errors)
                        device.events = copy.deepcopy(current.events)
                    case "toapp_report_data":
                        # Touches report_data, location, map, work, device_firmwares.
                        device.report_data = copy.deepcopy(current.report_data)
                        device.location = copy.deepcopy(current.location)
                        device.map = copy.deepcopy(current.map)
                        device.work = copy.deepcopy(current.work)
                        device.device_firmwares = copy.deepcopy(current.device_firmwares)
                    case _:
                        # Other sys messages (firmware info, light, product type, etc.)
                        # touch mower_state and device_firmwares.
                        device.mower_state = copy.deepcopy(current.mower_state)
                        device.device_firmwares = copy.deepcopy(current.device_firmwares)
                self._update_sys_data(device, message)

            case "driver":
                # driver messages touch mower_state and events.
                device.mower_state = copy.deepcopy(current.mower_state)
                device.events = copy.deepcopy(current.events)
                self._update_driver_data(device, message)

            case "net":
                # net messages touch mower_state, report_data, device_firmwares, events.
                device.mower_state = copy.deepcopy(current.mower_state)
                device.report_data = copy.deepcopy(current.report_data)
                device.device_firmwares = copy.deepcopy(current.device_firmwares)
                device.events = copy.deepcopy(current.events)
                self._update_net_data(device, message)

            case "mul":
                # mul messages touch mower_state only.
                device.mower_state = copy.deepcopy(current.mower_state)
                self._update_mul_data(device, message)

            case "ota":
                pass  # OTA updates are informational only; nothing to update yet

        return device

    # ------------------------------------------------------------------
    # Private helpers — mirror MowerStateManager._update_*_data() logic
    # without the callback invocations.
    # ------------------------------------------------------------------

    def _update_nav_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update navigation data fields on *device* in-place."""
        nav_msg = betterproto2.which_one_of(message.nav, "SubNavMsg")
        match nav_msg[0]:
            case "toapp_gethash_ack":
                hashlist_ack: NavGetHashListAck = nav_msg[1]
                device.map.update_root_hash_list(
                    NavGetHashListData.from_dict(hashlist_ack.to_dict(casing=betterproto2.Casing.SNAKE))
                )
            case "toapp_get_commondata_ack":
                common_data: NavGetCommDataAck = nav_msg[1]
                device.map.update(NavGetCommData.from_dict(common_data.to_dict(casing=betterproto2.Casing.SNAKE)))
            case "cover_path_upload":
                mow_path: CoverPathUploadT = nav_msg[1]
                device.map.update_mow_path(MowPath.from_dict(mow_path.to_dict(casing=betterproto2.Casing.SNAKE)))
            case "todev_planjob_set":
                planjob: NavPlanJobSet = nav_msg[1]
                device.map.update_plan(Plan.from_dict(planjob.to_dict(casing=betterproto2.Casing.SNAKE)))
            case "all_plan_task":
                all_tasks: NavGetAllPlanTask = nav_msg[1]
                incoming_ids = {t.id for t in all_tasks.tasks}
                # Remove plans that no longer exist on the device
                for removed_id in set(device.map.plan.keys()) - incoming_ids:
                    device.map.plan.pop(removed_id, None)
                # Signal a re-fetch if any plan IDs are new
                if incoming_ids - set(device.map.plan.keys()):
                    device.map.plans_stale = True
            case "toapp_svg_msg":
                common_svg_data: SvgMessageAckT = nav_msg[1]
                device.map.update(SvgMessage.from_dict(common_svg_data.to_dict(casing=betterproto2.Casing.SNAKE)))
            case "toapp_all_hash_name":
                hash_names: AppGetAllAreaHashName = nav_msg[1]
                if hash_names.hashnames:
                    device.map.area_name = [
                        AreaHashNameList(name=item.name, hash=item.hash) for item in hash_names.hashnames
                    ]
                elif device.map.area:
                    # Device returned no names (user hasn't named areas) — generate
                    # fallback labels from known area hashes so HA has something to show.
                    device.map.area_name = [
                        AreaHashNameList(name=f"area {i + 1}", hash=h)
                        for i, h in enumerate(sorted(device.map.area.keys()))
                    ]
                # else: no areas fetched yet — leave area_name alone; HashList.update()
                # will generate fallback names as each area chunk arrives.
            case "bidire_reqconver_path":
                work_settings: NavReqCoverPath = nav_msg[1]
                current_task = CurrentTaskSettings.from_dict(work_settings.to_dict(casing=betterproto2.Casing.SNAKE))
                if current_task.path_hash == 0:
                    device.map.current_mow_path = {}
                    device.map.generated_mow_path_geojson = {}
                device.work = current_task
            case "nav_sys_param_cmd":
                settings: NavSysParamMsg = nav_msg[1]
                match settings.id:
                    case 3:
                        device.mower_state.rain_detection = bool(settings.context)
                    case 6:
                        device.mower_state.turning_mode = settings.context
                    case 7:
                        device.mower_state.traversal_mode = settings.context
                    case 11:
                        device.mower_state.collect_grass_enable = settings.context
                    case 12:
                        device.mower_state.animal_protection.mode = settings.context
                    case 13:
                        device.mower_state.animal_protection.status = settings.context
            case "todev_unable_time_set":
                nav_non_work_time: NavUnableTimeSet = nav_msg[1]
                device.non_work_hours.non_work_sub_cmd = nav_non_work_time.sub_cmd
                device.non_work_hours.start_time = nav_non_work_time.unable_start_time
                device.non_work_hours.end_time = nav_non_work_time.unable_end_time
            case "toapp_edge_points":
                edge_msg: NavEdgePoints = nav_msg[1]
                hash_key = edge_msg.hash
                existing = device.map.edge_points.get(hash_key)
                if existing is None:
                    existing = EdgePoints(
                        hash=hash_key,
                        action=edge_msg.action,
                        type=edge_msg.type,
                        total_frame=edge_msg.total_frame,
                    )
                    device.map.edge_points[hash_key] = existing
                else:
                    # Update metadata in case it changed (e.g. total_frame)
                    existing.total_frame = edge_msg.total_frame
                points = [CommDataCouple(x=p.x, y=p.y) for p in edge_msg.data_couple]
                existing.frames[edge_msg.current_frame] = points
            case "toapp_work_report_ack" | "toapp_work_report_upload":
                work_report: WorkReportInfoAck = nav_msg[1]
                device.work_session_result.interrupt_flag = work_report.interrupt_flag
                device.work_session_result.start_work_time = work_report.start_work_time
                device.work_session_result.end_work_time = work_report.end_work_time
                device.work_session_result.work_time_used = work_report.work_time_used
                device.work_session_result.work_area = work_report.work_ares  # proto typo: work_ares
                device.work_session_result.work_progress = work_report.work_progress
                device.work_session_result.height_of_knife = work_report.height_of_knife
                device.work_session_result.work_type = work_report.work_type
                device.work_session_result.work_result = work_report.work_result

    def _update_sys_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update system data fields on *device* in-place."""
        sys_msg = betterproto2.which_one_of(message.sys, "SubSysMsg")
        match sys_msg[0]:
            case "system_update_buf":
                device.buffer(sys_msg[1])
            case "toapp_report_data":
                device.update_report_data(sys_msg[1])
            case "mow_to_app_info":
                device.mow_info(sys_msg[1])
            case "system_tard_state_tunnel":
                device.run_state_update(sys_msg[1])
            case "bidire_comm_cmd":
                comm_cmd: SysCommCmd = sys_msg[1]
                match comm_cmd.id:
                    case 3:
                        device.mower_state.rain_detection = bool(comm_cmd.context)
                    case 12:
                        device.mower_state.animal_protection.mode = comm_cmd.context
                    case 13:
                        device.mower_state.animal_protection.status = comm_cmd.context
            case "todev_time_ctrl_light":
                ctrl_light: TimeCtrlLight = sys_msg[1]
                side_led: SideLight = SideLight.from_dict(ctrl_light.to_dict(casing=betterproto2.Casing.SNAKE))
                device.mower_state.side_led = side_led
            case "toapp_lora_cfg_rsp":
                lora_cfg: LoraCfgRsp = sys_msg[1]
                device.mower_state.lora_config = lora_cfg.cfg
            case "device_product_type_info":
                device_product_type: DeviceProductTypeInfoT = sys_msg[1]
                if device_product_type.main_product_type != "" or device_product_type.sub_product_type != "":
                    device.mower_state.model_id = device_product_type.main_product_type
                    device.mower_state.sub_model_id = device_product_type.sub_product_type
            case "toapp_dev_fw_info":
                device_fw_info: DeviceFwInfo = sys_msg[1]
                if device_fw_info.result != 0:
                    device.device_firmwares.device_version = device_fw_info.version
                    device.mower_state.swversion = device_fw_info.version
                    device.update_device_firmwares(device_fw_info)

    def _update_driver_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update driver/cutter data fields on *device* in-place."""
        driver_msg = betterproto2.which_one_of(message.driver, "SubDrvMsg")
        match driver_msg[0]:
            case "current_cutter_mode":
                cutter_work_mode: AppGetCutterWorkMode = driver_msg[1]
                device.mower_state.cutter_mode = cutter_work_mode.current_cutter_mode
                device.mower_state.cutter_rpm = cutter_work_mode.current_cutter_rpm
            case "cutter_mode_ctrl_by_hand":
                cutter_work_mode_set: AppSetCutterWorkMode = driver_msg[1]
                device.mower_state.cutter_mode = cutter_work_mode_set.cutter_mode
            case "bidire_speed_read_set":
                speed_msg: DrvSrSpeed = driver_msg[1]
                device.mower_state.travel_speed = speed_msg.speed
            case "toapp_knife_status_change":
                knife_report: DrvKnifeChangeReport = driver_msg[1]
                device.events.blade_height_event.is_start = knife_report.is_start
                device.events.blade_height_event.start_height = knife_report.start_height
                device.events.blade_height_event.end_height = knife_report.end_height
                device.events.blade_height_event.cur_height = knife_report.cur_height

    def _update_net_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update network data fields on *device* in-place."""
        net_msg = betterproto2.which_one_of(message.net, "NetSubType")
        match net_msg[0]:
            case "toapp_wifi_iot_status":
                wifi_iot_status: WifiIotStatusReport = net_msg[1]
                device.mower_state.product_key = wifi_iot_status.productkey
            case "toapp_devinfo_resp":
                toapp_devinfo_resp: DrvDevInfoResp = net_msg[1]
                for resp in toapp_devinfo_resp.resp_ids:
                    if resp.res == DrvDevInfoResult.DRV_RESULT_SUC and resp.id == 1 and resp.type == 6:
                        device.mower_state.swversion = resp.info
                        device.device_firmwares.device_version = resp.info
            case "toapp_networkinfo_rsp":
                get_network_info_resp: GetNetworkInfoRsp = net_msg[1]
                device.mower_state.wifi_mac = get_network_info_resp.wifi_mac
            case "toapp_upgrade_report":
                upgrade_report: DrvUpgradeReport = net_msg[1]
                device.events.ota_progress.devname = upgrade_report.devname
                device.events.ota_progress.otaid = upgrade_report.otaid
                device.events.ota_progress.version = upgrade_report.version
                device.events.ota_progress.progress = upgrade_report.progress
                device.events.ota_progress.result = upgrade_report.result
                device.events.ota_progress.message = upgrade_report.message
                device.events.ota_progress.recv_cnt = upgrade_report.recv_cnt
            case "toapp_mnet_info_rsp":
                mnet_info_rsp: GetMnetInfoRsp = net_msg[1]
                if mnet_info_rsp.mnet is not None:
                    device.report_data.dev.mnet_info = device.report_data.dev.mnet_info.from_dict(
                        mnet_info_rsp.mnet.to_dict(casing=betterproto2.Casing.SNAKE)
                    )

    def _update_mul_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update media/light data fields on *device* in-place."""
        mul_msg = betterproto2.which_one_of(message.mul, "SubMul")
        match mul_msg[0]:
            case "set_audio":
                audio_msg: MulSetAudio = mul_msg[1]
                if audio_msg.au_language is not None:
                    device.mower_state.audio.language = audio_msg.au_language.name
                if audio_msg.at_switch is not None:
                    device.mower_state.audio.volume = audio_msg.at_switch
            case "get_lamp_rsp":
                lamp_resp: Getlamprsp = mul_msg[1]
                device.mower_state.lamp_info.lamp_bright = lamp_resp.lamp_bright
                if lamp_resp.get_ids in (1126, 1127):
                    device.mower_state.lamp_info.lamp_bright = lamp_resp.lamp_bright
                    device.mower_state.lamp_info.manual_light = bool(lamp_resp.lamp_manual_ctrl.value) or bool(
                        lamp_resp.lamp_bright
                    )
                if lamp_resp.get_ids == 1123:
                    device.mower_state.lamp_info.lamp_bright = lamp_resp.lamp_bright
                    device.mower_state.lamp_info.night_light = bool(lamp_resp.lamp_ctrl.value) or bool(
                        lamp_resp.lamp_bright
                    )
