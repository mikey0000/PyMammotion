"""StateReducer — decodes LubaMsg and applies it to a Device copy.

Polymorphic dispatch by device kind:
- :class:`MowerStateReducer` — handles every LubaMsg sub-message used by lawn
  mowers (Luba, Yuka, RTK rovers).
- :class:`PoolStateReducer` — handles the (much smaller) subset used by Spino
  pool cleaners. Currently a stub that just marks the device online; the real
  Spino-specific dispatch lands in the follow-up commit that adds the
  pool_state / pool_map fields to PoolCleanerDevice.

Pick the right reducer for a device name with :func:`get_state_reducer`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import copy
import dataclasses
import json
import logging
from typing import TYPE_CHECKING

import betterproto2

from pymammotion.data.model.device_info import DeviceFirmwares, SideLight
from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    CommDataCouple,
    MowPath,
    NavGetCommData,
    NavGetHashListData,
    Plan,
    SvgMessage,
)
from pymammotion.data.model.pool_state import PoolBottomType, PoolPoint, SpinoSysStatus, SpinoWorkMode, WallMaterial
from pymammotion.data.model.report_info import BaseScore
from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.data.mqtt.properties import OTAProgressItems
from pymammotion.proto import (
    AppDownlinkCmdT,
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
    ReportInfoData,
    ReportInfoT,
    ResponseBasestationInfoT,
    SvgMessageAckT,
    SysCommCmd,
    TimeCtrlLight,
    WifiIotStatusReport,
    WorkReportInfoAck,
)

if TYPE_CHECKING:
    from pymammotion.data.model.device import Device, MowingDevice, PoolCleanerDevice, RTKBaseStationDevice
    from pymammotion.data.mqtt.properties import ThingPropertiesMessage

_logger = logging.getLogger(__name__)


class StateReducer(ABC):
    """Abstract base class for device state reducers.

    Implementations decode an incoming :class:`LubaMsg` and return an updated
    :class:`Device` copy. Pure-ish: side-effect free except for logging.
    Does NOT fire any callbacks — broker request/response correlation handles
    that.
    """

    @abstractmethod
    def apply(self, current: Device, message: LubaMsg) -> Device:
        """Apply *message* to *current* and return the updated device copy."""

    def apply_properties(self, current: Device, properties: ThingPropertiesMessage) -> Device:
        """Apply a thing/properties message to *current* and return the updated copy.

        The default implementation is a no-op — subclasses that derive meaningful
        state from JSON thing/properties (e.g. :class:`RTKStateReducer`) override
        this method. Mower state is driven entirely by LubaMsg protobuf so the
        default suffices there.
        """
        return current


class MowerStateReducer(StateReducer):
    """Reducer for lawn mowers (Luba, Yuka, RTK rovers).

    Handles every LubaMsg sub-message group: nav, sys, driver, net, mul, ota,
    base. The pre-existing reducer logic — moved here verbatim from the old
    monolithic StateReducer.
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
                # Granular dispatch — each nav sub-message only mutates a
                # subset of fields.  Copying map (HashList) on every nav
                # message was a ~150 MiB/h leak (#125).
                nav_msg_name = betterproto2.which_one_of(message.nav, "SubNavMsg")[0]
                match nav_msg_name:
                    case (
                        "toapp_gethash_ack"
                        | "toapp_get_commondata_ack"
                        | "cover_path_upload"
                        | "todev_planjob_set"
                        | "all_plan_task"
                        | "toapp_svg_msg"
                        | "toapp_all_hash_name"
                        | "toapp_edge_points"
                    ):
                        device.map = copy.deepcopy(current.map)
                    case "bidire_reqconver_path":
                        pass  # handler wholesale-rebinds device.work
                    case "nav_sys_param_cmd":
                        device.mower_state = copy.deepcopy(current.mower_state)
                    case "todev_unable_time_set":
                        device.non_work_hours = copy.deepcopy(current.non_work_hours)
                    case "toapp_work_report_ack" | "toapp_work_report_upload":
                        device.work_session_result = copy.deepcopy(current.work_session_result)
                    case _:
                        # Unknown nav sub-message — defensively copy everything.
                        device.map = copy.deepcopy(current.map)
                        device.work = copy.deepcopy(current.work)
                        device.mower_state = copy.deepcopy(current.mower_state)
                        device.non_work_hours = copy.deepcopy(current.non_work_hours)
                        device.work_session_result = copy.deepcopy(current.work_session_result)
                self._update_nav_data(device, message)

            case "sys":
                # Granular dispatch.  The hot path (system_tard_state_tunnel,
                # ~4x/sec during mowing) avoids copying mowing_state because
                # run_state_update() wholesale-rebinds it.
                sys_msg_name = betterproto2.which_one_of(message.sys, "SubSysMsg")[0]
                match sys_msg_name:
                    case "system_tard_state_tunnel":
                        # run_state_update rebinds device.mowing_state wholesale;
                        # only location is mutated in-place.
                        device.location = copy.deepcopy(current.location)
                    case "system_update_buf":
                        # buffer() mutates location, errors, and events in-place.
                        device.location = copy.deepcopy(current.location)
                        device.errors = copy.deepcopy(current.errors)
                        device.events = copy.deepcopy(current.events)
                    case "toapp_report_data":
                        # update_report_data always mutates report_data and location;
                        # map/work/device_firmwares are mutated conditionally — copy
                        # defensively since the condition isn't known in advance.
                        device.report_data = copy.deepcopy(current.report_data)
                        device.location = copy.deepcopy(current.location)
                        device.map = copy.deepcopy(current.map)
                        device.work = copy.deepcopy(current.work)
                        device.device_firmwares = copy.deepcopy(current.device_firmwares)
                    case "toapp_dev_fw_info":
                        # Only sys handler that touches both mower_state and device_firmwares.
                        device.mower_state = copy.deepcopy(current.mower_state)
                        device.device_firmwares = copy.deepcopy(current.device_firmwares)
                    case (
                        "bidire_comm_cmd"
                        | "todev_time_ctrl_light"
                        | "toapp_lora_cfg_rsp"
                        | "device_product_type_info"
                    ):
                        # These handlers only touch mower_state.
                        device.mower_state = copy.deepcopy(current.mower_state)
                    case "mow_to_app_info":
                        pass  # mow_info() is a no-op — nothing to copy.
                    case _:
                        device.mower_state = copy.deepcopy(current.mower_state)
                        device.device_firmwares = copy.deepcopy(current.device_firmwares)
                self._update_sys_data(device, message)

            case "driver":
                # Granular dispatch — knife events touch only `events`,
                # everything else only touches `mower_state`.
                drv_msg_name = betterproto2.which_one_of(message.driver, "SubDrvMsg")[0]
                match drv_msg_name:
                    case "toapp_knife_status_change":
                        device.events = copy.deepcopy(current.events)
                    case "current_cutter_mode" | "cutter_mode_ctrl_by_hand" | "bidire_speed_read_set":
                        device.mower_state = copy.deepcopy(current.mower_state)
                    case _:
                        device.mower_state = copy.deepcopy(current.mower_state)
                        device.events = copy.deepcopy(current.events)
                self._update_driver_data(device, message)

            case "net":
                # Granular dispatch — most net handlers only touch one field.
                net_msg_name = betterproto2.which_one_of(message.net, "NetSubType")[0]
                match net_msg_name:
                    case "toapp_wifi_iot_status" | "toapp_networkinfo_rsp":
                        device.mower_state = copy.deepcopy(current.mower_state)
                    case "toapp_devinfo_resp":
                        # Writes both mower_state.swversion and device_firmwares.device_version.
                        device.mower_state = copy.deepcopy(current.mower_state)
                        device.device_firmwares = copy.deepcopy(current.device_firmwares)
                    case "toapp_upgrade_report":
                        device.events = copy.deepcopy(current.events)
                    case "toapp_mnet_info_rsp":
                        device.report_data = copy.deepcopy(current.report_data)
                    case _:
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

            case "base":
                device.report_data = copy.deepcopy(current.report_data)
                self._update_base_data(device, message)

        return device

    # ------------------------------------------------------------------
    # Private helpers — mirror MowerStateManager._update_*_data() logic
    # without the callback invocations.
    # ------------------------------------------------------------------

    def _update_nav_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update navigation data fields on *device* in-place."""
        # Pool cleaners (Spino) reuse the LubaMsg envelope but do not have a
        # GNSS RTK origin or a lat/lon dock. Generating GeoJSON from a (0,0)
        # RTK origin produces nonsense at best and can crash the geometry
        # library. Bail out until a pool-specific reducer exists.
        from pymammotion.utility.device_type import DeviceType

        if DeviceType.is_swimming_pool(device.name):
            _logger.debug(
                "StateReducer: skipping nav update for swimming-pool device %s",
                device.name,
            )
            return
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
                if len(device.map.missing_hashlist(0)) == 0:
                    device.map.generate_geojson(device.location.RTK, device.location.dock)
            case "cover_path_upload":
                mow_path: CoverPathUploadT = nav_msg[1]
                device.map.update_mow_path(MowPath.from_dict(mow_path.to_dict(casing=betterproto2.Casing.SNAKE)))
                if len(device.map.find_missing_mow_path_frames()) == 0:
                    device.map.generate_mowing_geojson(device.location.RTK)
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
                device.map.upsert_edge_frame(
                    hash_key=edge_msg.hash,
                    action=edge_msg.action,
                    edge_type=edge_msg.type,
                    total_frame=edge_msg.total_frame,
                    current_frame=edge_msg.current_frame,
                    points=[CommDataCouple(x=p.x, y=p.y) for p in edge_msg.data_couple],
                )
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
        # Pool cleaners (Spino) do not have cutters, blades, or knife events.
        # Unpacking driver oneof variants into mower-specific dataclasses would
        # either silently corrupt mower fields or AttributeError on missing
        # attributes — skip until a pool-specific reducer exists.
        from pymammotion.utility.device_type import DeviceType

        if DeviceType.is_swimming_pool(device.name):
            _logger.debug(
                "StateReducer: skipping driver update for swimming-pool device %s",
                device.name,
            )
            return
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

    def _update_base_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update base station RTK data from LubaMsg.base.to_app response."""
        base_msg = betterproto2.which_one_of(message.base, "BaseStationSubType")
        match base_msg[0]:
            case "to_app":
                resp: ResponseBasestationInfoT = base_msg[1]
                info = device.report_data.basestation_info
                info.sats_num = resp.sats_num
                info.rtk_status = resp.rtk_status
                info.rtk_channel = resp.rtk_channel
                info.rtk_switch = resp.rtk_switch
                info.wifi_rssi = resp.wifi_rssi
                info.lora_channel = resp.lora_channel
                info.mqtt_rtk_status = resp.mqtt_rtk_status
                info.app_connect_type = resp.app_connect_type
                if resp.score_info is not None:
                    info.score_info = BaseScore(
                        base_score=resp.score_info.base_score,
                        base_leve=resp.score_info.base_leve,
                        base_moved=resp.score_info.base_moved,
                        base_moving=resp.score_info.base_moving,
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

    def apply_properties(self, current: MowingDevice, properties: ThingPropertiesMessage) -> MowingDevice:
        """Extract mower state from a thing/properties JSON push.

        Mirrors the mapping in :meth:`MowerDevice.update_device_firmwares` for
        firmware types, plus pulls Wi-Fi/BLE MAC + RSSI from the ``networkInfo``
        JSON blob and the LoRa radio configuration from ``loraGeneralConfig``.
        """
        device: MowingDevice = dataclasses.replace(current)
        device.mower_state = copy.deepcopy(current.mower_state)
        device.device_firmwares = copy.deepcopy(current.device_firmwares)
        device.report_data = copy.deepcopy(current.report_data)
        items = properties.params.items

        if net_prop := items.networkInfo:
            try:
                net = json.loads(net_prop.value)
                device.mower_state.wifi_mac = str(net.get("wifi_sta_mac", device.mower_state.wifi_mac))
                device.mower_state.ble_mac = str(net.get("bt_mac", device.mower_state.ble_mac))
                device.mower_state.wifi_ssid = str(net.get("ssid", device.mower_state.wifi_ssid))
                device.mower_state.ip_address = str(net.get("ip", device.mower_state.ip_address))
                device.report_data.connect.wifi_rssi = int(net.get("wifi_rssi", device.report_data.connect.wifi_rssi))
            except (ValueError, KeyError, TypeError):
                _logger.debug("MowerStateReducer: failed to parse networkInfo property")

        if dev_ver_info := items.deviceVersionInfo:
            try:
                blob = json.loads(dev_ver_info.value)
                if dev_ver := blob.get("devVer"):
                    device.device_firmwares.device_version = str(dev_ver)
                for module in blob.get("fwInfo", []):
                    fw_type = str(module.get("t", ""))
                    fw_version = str(module.get("v", ""))
                    if not fw_version:
                        continue
                    _apply_mower_fw_module(device.device_firmwares, fw_type, fw_version)
            except (ValueError, TypeError):
                _logger.debug("MowerStateReducer: failed to parse deviceVersionInfo property")

        if ver_prop := items.deviceVersion:
            device.device_firmwares.device_version = str(ver_prop.value)
        if lora_prop := items.loraGeneralConfig:
            device.mower_state.lora_config = str(lora_prop.value)
        if ext_mod := items.extMod:
            device.mower_state.model = str(ext_mod.value)
        if int_mod := items.intMod:
            device.mower_state.internal_model = str(int_mod.value)
        if bms_hw := items.bmsHardwareVersion:
            device.mower_state.battery_hardware = str(bms_hw.value)

        if other_info := items.deviceOtherInfo:
            try:
                info = json.loads(other_info.value)
                if (mileage := info.get("mileage")) is not None:
                    device.report_data.dev.mileage = int(mileage)
                if (wt_sec := info.get("wt_sec")) is not None:
                    device.report_data.dev.work_time_sec = int(wt_sec)
            except (ValueError, TypeError):
                _logger.debug("MowerStateReducer: failed to parse deviceOtherInfo property")

        # Individual firmware properties (duplicates of deviceVersionInfo.fwInfo
        # on newer devices, but some older devices may only send these).
        for prop_name, fw_type in (
            ("stm32H7Version", "1"),
            ("mcBootVersion", "8"),
            ("leftMotorVersion", "3"),
            ("rightMotorVersion", "4"),
            ("leftMotorBootVersion", "9"),
            ("rightMotorBootVersion", "10"),
            ("bmsVersion", "7"),
            ("rtkVersion", "5"),
        ):
            if prop := getattr(items, prop_name, None):
                value = str(prop.value)
                if value:
                    _apply_mower_fw_module(device.device_firmwares, fw_type, value)

        if ota_prop := items.otaProgress:
            try:
                ota = OTAProgressItems.from_dict(ota_prop.value)
                done = ota.progress == 100
                device.update_check = dataclasses.replace(
                    device.update_check,
                    progress=ota.progress,
                    isupgrading=not done,
                    upgradeable=False if done else device.update_check.upgradeable,
                )
                if done:
                    device.device_firmwares.device_version = ota.version
            except (ValueError, KeyError, TypeError):
                _logger.debug("MowerStateReducer: failed to parse otaProgress property")

        return device


def _apply_mower_fw_module(firmwares: DeviceFirmwares, fw_type: str, version: str) -> None:
    """Map a mower firmware type code to the matching DeviceFirmwares field.

    Kept aligned with :meth:`MowerDevice.update_device_firmwares`.
    """
    match fw_type:
        case "1":
            firmwares.main_controller = version
        case "3":
            firmwares.left_motor_driver = version
        case "4":
            firmwares.right_motor_driver = version
        case "5":
            firmwares.rtk_rover_station = version
        case "7":
            firmwares.bms = version
        case "8":
            firmwares.main_controller_bt = version
        case "9":
            firmwares.left_motor_driver_bt = version
        case "10":
            firmwares.right_motor_driver_bt = version
        case "11":
            firmwares.bsp = version
        case "12":
            firmwares.middleware = version
        case "14":
            firmwares.lora_module = version
        case "16":
            firmwares.lte_module = version
        case "17":
            firmwares.lidar = version
        case "201":
            # MNWheelG4 — unified wheel driver (Yuka mini & newer); single board
            # drives both wheels, so populate both legacy split fields.
            firmwares.left_motor_driver = version
            firmwares.right_motor_driver = version
        case "202":
            firmwares.left_motor_driver_bt = version
            firmwares.right_motor_driver_bt = version
        case "203":
            firmwares.cutter_driver = version
        case "204":
            firmwares.cutter_driver_bt = version


class PoolStateReducer(StateReducer):
    """Reducer for swimming-pool cleaners (Spino, Spino-S1/E1/SP).

    Spino reuses the :class:`LubaMsg` envelope but populates a much smaller
    subset of sub-messages than lawn mowers. Confirmed wire paths used by
    the Mammotion Android app:

    - ``sys.report_info`` → :class:`ReportInfoT` → :class:`DevStatueT` —
      runtime status (sys_status, work_mode, battery, …) shown on the home
      screen.
    - ``sys.app_downlink_cmd`` → :class:`AppDownlinkCmdT` — both the
      outgoing user-settings commands (wall material, bottom type, floor
      speed) and the device's ack responses that carry pool ``map_info`` /
      ``line_info`` geometry rendered by ``SwimmingMapActivity``.

    Other LubaMsg sub-message groups (``nav``, ``driver``, ``base``) are
    not used by Spino in any path the app reads, so they are intentionally
    no-ops here. Net / mul / ota will be added once their Spino usage is
    confirmed against captured traffic — leaving them out is safer than
    reusing mower dispatch on a device that has no ``mower_state``.
    """

    def apply(self, current: PoolCleanerDevice, message: LubaMsg) -> PoolCleanerDevice:
        """Apply *message* to *current* and return the updated copy."""
        device: PoolCleanerDevice = dataclasses.replace(current)
        if not device.online:
            device.online = True

        sub_msg_type = betterproto2.which_one_of(message, "LubaSubMsg")[0]
        if sub_msg_type != "sys":
            # Only the sys envelope carries Spino payloads we currently model.
            return device

        sys_msg = betterproto2.which_one_of(message.sys, "SubSysMsg")
        match sys_msg[0]:
            case "report_info":
                device.pool_state = copy.deepcopy(current.pool_state)
                self._update_report_info(device, sys_msg[1])
            case "app_downlink_cmd":
                device.pool_state = copy.deepcopy(current.pool_state)
                device.pool_map = copy.deepcopy(current.pool_map)
                self._update_app_downlink_cmd(device, sys_msg[1])
            case _:
                _logger.debug(
                    "PoolStateReducer: ignoring unhandled sys sub-message %r for %s",
                    sys_msg[0],
                    device.name,
                )

        return device

    def _update_report_info(self, device: PoolCleanerDevice, report: ReportInfoT) -> None:
        """Apply a ``ReportInfoT`` (carrying ``DevStatueT``) to *device*."""
        if report.dev_status is None:
            return
        status = report.dev_status

        # sys_status is an int on the wire — coerce to our enum, falling back
        # to the raw int if a future firmware sends a value we don't yet model.
        try:
            device.pool_state.sys_status = SpinoSysStatus(status.sys_status)
        except ValueError:
            _logger.debug(
                "PoolStateReducer: unknown sys_status=%d for %s — leaving previous value",
                status.sys_status,
                device.name,
            )
        try:
            device.pool_state.work_mode = SpinoWorkMode(status.work_mode)
        except ValueError:
            _logger.debug(
                "PoolStateReducer: unknown work_mode=%d for %s — leaving previous value",
                status.work_mode,
                device.name,
            )
        device.pool_state.battery = status.bat_val

    def _update_app_downlink_cmd(self, device: PoolCleanerDevice, cmd: AppDownlinkCmdT) -> None:
        """Apply an incoming ``AppDownlinkCmdT`` (settings ack or map data) to *device*."""
        # Settings — only update fields the device actually populated.
        if cmd.wall_material is not None:
            try:
                device.pool_state.wall_material = WallMaterial(cmd.wall_material)
            except ValueError:
                _logger.debug(
                    "PoolStateReducer: unknown wall_material=%d for %s",
                    cmd.wall_material,
                    device.name,
                )
        if cmd.bottom_type is not None:
            try:
                device.pool_state.bottom_type = PoolBottomType(int(cmd.bottom_type))
            except ValueError:
                _logger.debug(
                    "PoolStateReducer: unknown bottom_type=%s for %s",
                    cmd.bottom_type,
                    device.name,
                )
        if cmd.floor_speed is not None:
            device.pool_state.floor_speed = cmd.floor_speed

        # Pool geometry — boundary outline (tag=0) and cleaning path (tag=1).
        # MapInfo is sent in packets (pack_index / pack_num); the simplest
        # correct behaviour is to wait for the final packet and replace the
        # whole list. Until we see what real traffic looks like, treat each
        # incoming MapInfo as a complete payload — the proto allows
        # total_points to indicate the full length per packet.
        for map_info in (cmd.map_info, cmd.line_info):
            if map_info is None:
                continue
            points = [PoolPoint(x=p.x, y=p.y) for p in map_info.points]
            if map_info.tag == 0:
                device.pool_map.boundary = points
            elif map_info.tag == 1:
                device.pool_map.cleaning_path = points
            else:
                _logger.debug(
                    "PoolStateReducer: unknown MapInfo tag=%d for %s",
                    map_info.tag,
                    device.name,
                )


class RTKStateReducer(StateReducer):
    """Reducer for RTK base station devices (RTK, RBS03A0/A1/A2, RTKNB).

    All devices share one MQTT connection per account; messages are routed by
    ``iot_id``.  This reducer handles :class:`LubaMsg` frames that carry the
    RTK device's own ``iot_id``.  RTK base stations use a small subset of
    LubaMsg sub-messages:

    - ``sys.toapp_report_data`` → ``basestation_info`` — operational status
      and connectivity uptime (``rpt_basestation_info``, field 11 of
      ``report_info_data``).
    - ``sys.toapp_dev_fw_info`` → firmware version string.
    - ``net.toapp_wifi_iot_status`` → Aliyun product key.
    - ``net.toapp_networkinfo_rsp`` → Wi-Fi MAC address.

    Satellite count, fix quality, and LoRa channel can arrive both from the
    *mower's* ``iot_id`` (handled by :class:`MowerStateReducer._update_base_data`)
    and directly from the RTK device's own ``iot_id`` via ``base.to_app``
    (handled here).
    """

    def apply(self, current: RTKBaseStationDevice, message: LubaMsg) -> RTKBaseStationDevice:
        """Apply *message* to *current* and return the updated copy."""
        device: RTKBaseStationDevice = dataclasses.replace(current)
        if not device.online:
            device.online = True

        sub_msg_type = betterproto2.which_one_of(message, "LubaSubMsg")[0]
        match sub_msg_type:
            case "sys":
                self._update_sys_data(device, message)
            case "net":
                self._update_net_data(device, message)
            case "base":
                self._update_base_data(device, message)
            case _:
                _logger.debug(
                    "RTKStateReducer: ignoring unhandled sub-message %r for %s",
                    sub_msg_type,
                    device.name,
                )

        return device

    def _update_sys_data(self, device: RTKBaseStationDevice, message: LubaMsg) -> None:
        """Apply sys sub-messages from the base station's own connection."""
        sys_msg = betterproto2.which_one_of(message.sys, "SubSysMsg")
        match sys_msg[0]:
            case "toapp_report_data":
                report: ReportInfoData = sys_msg[1]
                if report.basestation_info is not None:
                    device.basestation_status = report.basestation_info.basestation_status
                    device.connect_status_since_poweron = report.basestation_info.connect_status_since_poweron
            case "toapp_dev_fw_info":
                fw_info: DeviceFwInfo = sys_msg[1]
                if fw_info.result != 0:
                    device.device_version = fw_info.version
            case _:
                _logger.debug(
                    "RTKStateReducer: ignoring sys sub-message %r for %s",
                    sys_msg[0],
                    device.name,
                )

    def _update_net_data(self, device: RTKBaseStationDevice, message: LubaMsg) -> None:
        """Apply net sub-messages (connectivity info) from the base station."""
        net_msg = betterproto2.which_one_of(message.net, "NetSubType")
        match net_msg[0]:
            case "toapp_wifi_iot_status":
                wifi_iot: WifiIotStatusReport = net_msg[1]
                device.product_key = wifi_iot.productkey
            case "toapp_networkinfo_rsp":
                net_info: GetNetworkInfoRsp = net_msg[1]
                device.wifi_ssid = net_info.wifi_ssid
                device.wifi_mac = net_info.wifi_mac
                device.wifi_rssi = net_info.wifi_rssi
                device.ip = net_info.ip
                device.mask = net_info.mask
                device.gateway = net_info.gateway
            case _:
                _logger.debug(
                    "RTKStateReducer: ignoring net sub-message %r for %s",
                    net_msg[0],
                    device.name,
                )

    def _update_base_data(self, device: RTKBaseStationDevice, message: LubaMsg) -> None:
        """Apply base.to_app (ResponseBasestationInfoT) from the RTK device."""
        base_msg = betterproto2.which_one_of(message.base, "BaseStationSubType")
        match base_msg[0]:
            case "to_app":
                resp: ResponseBasestationInfoT = base_msg[1]
                device.app_connect_type = resp.app_connect_type
                device.ble_rssi = resp.ble_rssi
                device.wifi_rssi = resp.wifi_rssi
                device.sats_num = resp.sats_num
                device.lora_scan = resp.lora_scan
                device.lora_channel = resp.lora_channel
                device.lora_locid = resp.lora_locid
                device.lora_netid = resp.lora_netid
                device.rtk_status = resp.rtk_status
                device.lowpower_status = resp.lowpower_status
                device.mqtt_rtk_status = resp.mqtt_rtk_status
                device.rtk_channel = resp.rtk_channel
                device.rtk_switch = resp.rtk_switch
                if resp.score_info is not None:
                    device.score_info = BaseScore(
                        base_score=resp.score_info.base_score,
                        base_leve=resp.score_info.base_leve,
                        base_moved=resp.score_info.base_moved,
                        base_moving=resp.score_info.base_moving,
                    )
            case _:
                _logger.debug(
                    "RTKStateReducer: ignoring base sub-message %r for %s",
                    base_msg[0],
                    device.name,
                )

    def apply_properties(
        self, current: RTKBaseStationDevice, properties: ThingPropertiesMessage
    ) -> RTKBaseStationDevice:
        """Extract RTK state from a thing/properties JSON push.

        RTK base stations report location (``coordinate``), connectivity
        (``networkInfo``), and firmware version (``deviceVersion``) as Aliyun
        thing/properties rather than LubaMsg protobuf fields.  This method
        converts those JSON payloads into fields on :class:`RTKBaseStationDevice`
        so the state machine stays the single source of truth.
        """
        device: RTKBaseStationDevice = dataclasses.replace(current)
        items = properties.params.items

        if coord_prop := items.coordinate:
            try:
                coord = json.loads(coord_prop.value)
                # The coordinate property is already in radians (protocol-level unit).
                if (lat := coord.get("lat")) and lat != 0:
                    device.lat = float(coord["lat"])
                if (lon := coord.get("lon")) and lon != 0:
                    device.lon = float(coord["lon"])
            except (ValueError, KeyError, TypeError):
                _logger.debug("RTKStateReducer: failed to parse coordinate property")

        if net_prop := items.networkInfo:
            try:
                net = json.loads(net_prop.value)
                device.wifi_rssi = int(net.get("wifi_rssi", device.wifi_rssi))
                device.wifi_sta_mac = str(net.get("wifi_sta_mac", device.wifi_sta_mac))
                device.bt_mac = str(net.get("bt_mac", device.bt_mac))
            except (ValueError, KeyError, TypeError):
                _logger.debug("RTKStateReducer: failed to parse networkInfo property")

        if ver_prop := items.deviceVersion:
            device.device_version = str(ver_prop.value)

        if dev_ver_info := items.deviceVersionInfo:
            try:
                blob = json.loads(dev_ver_info.value)
                if dev_ver := blob.get("devVer"):
                    device.device_version = str(dev_ver)
                    device.device_firmwares.device_version = str(dev_ver)
                for module in blob.get("fwInfo", []):
                    fw_type = str(module.get("t", ""))
                    fw_version = str(module.get("v", ""))
                    if not fw_version:
                        continue
                    match fw_type:
                        case "101":
                            device.device_firmwares.main_controller = fw_version
                        case "102":
                            device.device_firmwares.rtk_version = fw_version
                        case "103":
                            device.device_firmwares.lora_version = fw_version
            except (ValueError, TypeError):
                _logger.debug("RTKStateReducer: failed to parse deviceVersionInfo property")

        if lora_prop := items.loraGeneralConfig:
            device.lora_version = str(lora_prop.value)

        if ota_prop := items.otaProgress:
            try:
                ota = OTAProgressItems.from_dict(ota_prop.value)
                done = ota.progress == 100
                device.update_check = dataclasses.replace(
                    device.update_check,
                    progress=ota.progress,
                    isupgrading=not done,
                    upgradeable=False if done else device.update_check.upgradeable,
                )
                if done:
                    device.device_version = ota.version
            except (ValueError, KeyError, TypeError):
                _logger.debug("RTKStateReducer: failed to parse otaProgress property")

        return device


def get_state_reducer(device_name: str) -> StateReducer:
    """Return the appropriate :class:`StateReducer` for *device_name*.

    Dispatches to:
    - :class:`RTKStateReducer` for RTK base stations (RTK, RBS03A0/A1/A2, RTKNB)
    - :class:`PoolStateReducer` for Spino pool cleaners
    - :class:`MowerStateReducer` for all lawn mowers (the historical default)

    Picked once per device at handle construction time so the hot path
    doesn't pay an isinstance check on every incoming message.
    """
    # Local import to avoid a circular dependency between the reducer module
    # and the device-type helpers it consults.
    from pymammotion.utility.device_type import DeviceType

    if DeviceType.is_swimming_pool(device_name):
        return PoolStateReducer()
    if DeviceType.is_rtk(device_name):
        return RTKStateReducer()
    return MowerStateReducer()
