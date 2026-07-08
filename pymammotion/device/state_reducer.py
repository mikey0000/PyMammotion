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
import math
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
from pymammotion.data.model.pool_state import (
    MapTrans,
    PoolBottomType,
    PoolPlan,
    PoolPoint,
    SpinoErrorEntry,
    SpinoSysStatus,
    SpinoToggle,
    SpinoWorkMode,
    WallMaterial,
)
from pymammotion.data.model.report_info import BaseScore
from pymammotion.data.model.work import CurrentTaskSettings
from pymammotion.data.mqtt.properties import OTAProgressItems
from pymammotion.proto import (
    AppDownlinkCmdT,
    AppDownlinkCmdTypeE,
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
    LampCtrlSta,
    LampManualCtrlSta,
    LoraCfgRsp,
    LubaMsg,
    MulAudioCfg,
    MulSetAudio,
    NavEdgePoints,
    NavGetAllPlanTask,
    NavGetCommDataAck,
    NavGetHashListAck,
    NavMapNameMsg,
    NavPlanJobSet,
    NavReqCoverPath,
    NavSysParamMsg,
    NavTaskCtrlAck,
    NavUnableTimeSet,
    PlanJobSet,
    ReportInfoData,
    ReportInfoT,
    ResponseBasestationInfoT,
    SvgMessageAckT,
    SysCommCmd,
    SystemUpdateBufMsg,
    TimeCtrlLight,
    WifiIotStatusReport,
    WorkReportInfoAck,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from pymammotion.data.model.device import Device, MowingDevice, PoolCleanerDevice, RTKBaseStationDevice
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage, ThingPropertiesMessage

_logger = logging.getLogger(__name__)


class StateReducer(ABC):
    """Abstract base class for device state reducers.

    Implementations decode an incoming :class:`LubaMsg` and return an updated
    :class:`Device` copy. Pure-ish: side-effect free except for logging.
    Does NOT fire any callbacks — broker request/response correlation handles
    that.
    """

    def __init__(self, is_saga_active: Callable[[], bool] | None = None) -> None:
        """Initialise the reducer with an optional saga-active predicate.

        When the callable returns True, expensive opportunistic work (e.g.
        :meth:`HashList.generate_geojson`) is skipped — the saga's
        ``on_complete`` hook regenerates it once at the end instead of paying
        the cost on every frame.
        """
        self._is_saga_active: Callable[[], bool] = is_saga_active or (lambda: False)

    @abstractmethod
    def apply(self, current: Device, message: LubaMsg) -> Device:
        """Apply *message* to *current* and return the updated device copy."""

    def apply_properties(self, current: Device, _properties: ThingPropertiesMessage) -> Device:
        """Apply a thing/properties message to *current* and return the updated copy.

        The default implementation is a no-op — subclasses that derive meaningful
        state from JSON thing/properties (e.g. :class:`RTKStateReducer`) override
        this method. Mower state is driven entirely by LubaMsg protobuf so the
        default suffices there.
        """
        return current

    def apply_mammotion_properties(self, current: Device, _properties: MammotionPropertiesMessage) -> Device:
        """Apply a Mammotion MQTT flat property push to *current* and return the updated copy.

        The default is a no-op; :class:`MowerStateReducer` overrides this to
        extract battery, device state, firmware versions, network info, etc.
        """
        return current


class MowerStateReducer(StateReducer):
    """Reducer for lawn mowers (Luba, Yuka, RTK rovers).

    Handles every LubaMsg sub-message group: nav, sys, driver, net, mul, ota,
    base. The pre-existing reducer logic — moved here verbatim from the old
    monolithic StateReducer.
    """

    def apply(self, current: MowingDevice, message: LubaMsg) -> MowingDevice:  # type: ignore
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
                nav_msg_name = betterproto2.which_one_of(message.nav, "SubNavMsg")[0]  # type: ignore
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
                    case "todev_taskctrl_ack":
                        device.report_data = copy.deepcopy(current.report_data)
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
                sys_msg_name = betterproto2.which_one_of(message.sys, "SubSysMsg")[0]  # type: ignore
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
                        "bidire_comm_cmd" | "todev_time_ctrl_light" | "toapp_lora_cfg_rsp" | "device_product_type_info"
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
                drv_msg_name = betterproto2.which_one_of(message.driver, "SubDrvMsg")[0]  # type: ignore
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
                net_msg_name = betterproto2.which_one_of(message.net, "NetSubType")[0]  # type: ignore
                match net_msg_name:
                    case "toapp_wifi_iot_status":
                        device.mower_state = copy.deepcopy(current.mower_state)
                    case "toapp_networkinfo_rsp":
                        # Writes mower_state fields AND report_data.connect.wifi_rssi.
                        device.mower_state = copy.deepcopy(current.mower_state)
                        device.report_data = copy.deepcopy(current.report_data)
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
        nav_msg = betterproto2.which_one_of(message.nav, "SubNavMsg")  # type: ignore
        match nav_msg[0]:
            case "toapp_gethash_ack":
                hashlist_ack: NavGetHashListAck = nav_msg[1]  # type: ignore
                device.map.update_root_hash_list(
                    NavGetHashListData.from_dict(hashlist_ack.to_dict(casing=betterproto2.Casing.SNAKE))
                )
            case "toapp_get_commondata_ack":
                common_data: NavGetCommDataAck = nav_msg[1]  # type: ignore
                device.map.update(NavGetCommData.from_dict(common_data.to_dict(casing=betterproto2.Casing.SNAKE)))
                # Skip eager geojson regen during sagas — the saga's on_complete
                # handler regenerates once after all frames arrive instead of
                # paying the O(N) cost on every frame.
                if not self._is_saga_active() and len(device.map.missing_hashlist(0)) == 0:
                    device.map.generate_geojson(device.location.RTK, device.location.dock)
            case "cover_path_upload":
                mow_path: CoverPathUploadT = nav_msg[1]  # type: ignore
                device.map.update_mow_path(MowPath.from_dict(mow_path.to_dict(casing=betterproto2.Casing.SNAKE)))
                if not self._is_saga_active() and len(device.map.find_missing_mow_path_frames()) == 0:
                    device.map.generate_mowing_geojson(device.location.RTK)
            case "todev_planjob_set":
                planjob: NavPlanJobSet = nav_msg[1]  # type: ignore
                device.map.update_plan(Plan.from_dict(planjob.to_dict(casing=betterproto2.Casing.SNAKE)))
            case "all_plan_task":
                all_tasks: NavGetAllPlanTask = nav_msg[1]  # type: ignore
                incoming_ids = {t.id for t in all_tasks.tasks}
                # Remove plans that no longer exist on the device
                for removed_id in set(device.map.plan.keys()) - incoming_ids:
                    device.map.plan.pop(removed_id, None)
                # Signal a re-fetch if any plan IDs are new
                if incoming_ids - set(device.map.plan.keys()):
                    device.map.plans_stale = True
            case "toapp_svg_msg":
                common_svg_data: SvgMessageAckT = nav_msg[1]  # type: ignore
                device.map.update(SvgMessage.from_dict(common_svg_data.to_dict(casing=betterproto2.Casing.SNAKE)))
            case "toapp_all_hash_name":
                hash_names: AppGetAllAreaHashName = nav_msg[1]  # type: ignore
                # The area name list reflects the device's CURRENT areas.  When the
                # device's reported bol_hash no longer matches our stored root
                # manifest, the map was edited device-side — an edited area gets a new
                # content hash that isn't in our (pre-edit) root_hash_lists.  Reconcile
                # against bol_hash and wipe the stale manifest, otherwise the per-frame
                # prune in HashList.update drops the edited area's freshly-arriving
                # geometry (its hash isn't in the stale manifest) — removing the area
                # instead of replacing it.  An empty manifest makes update_hash_lists a
                # no-op, so the geometry survives until the map saga re-fetches it.
                #
                # Only do this OUTSIDE a saga: during a MapFetchSaga the saga owns
                # root_hash_lists freshness (it always re-fetches it), and the device
                # may push toapp_all_hash_name mid-fetch.  Wiping the manifest then
                # would empty find_incomplete_hashes and stop step 4 early, leaving
                # area geometry unfetched.  The saga handles staleness at its start.
                if not self._is_saga_active():
                    bol_hash = device.report_data.locations[0].bol_hash if device.report_data.locations else 0
                    if bol_hash:
                        device.map.invalidate_maps(bol_hash)
                if hash_names.hashnames:
                    device.map.area_name = [
                        AreaHashNameList(name=item.name, hash=item.hash) for item in hash_names.hashnames
                    ]
                elif device.map.area:
                    # Device returned no names — prefer name_time.name from the area
                    # frames if present, falling back to numbered labels.
                    device.map.area_name = [
                        AreaHashNameList(name=device.map.area[h].name or f"area {i + 1}", hash=h)
                        for i, h in enumerate(sorted(device.map.area.keys()))
                    ]
                # else: no areas fetched yet — leave area_name alone; HashList.update()
                # will generate fallback names as each area chunk arrives.
            case "toapp_map_name_msg":
                # Single-area rename echo (NavMapNameMsg, one per area) — the
                # device acks set_area_name with the hash + new name rather than
                # re-sending the whole toapp_all_hash_name list, so patch the one
                # entry in place. hash == 0 is the get-list request shape, ignore.
                name_msg: NavMapNameMsg = nav_msg[1]  # type: ignore
                if name_msg.hash and name_msg.name:
                    device.map.upsert_area_name(name_msg.hash, name_msg.name)
            case "bidire_reqconver_path":
                work_settings: NavReqCoverPath = nav_msg[1]  # type: ignore
                current_task = CurrentTaskSettings.from_dict(work_settings.to_dict(casing=betterproto2.Casing.SNAKE))
                device.work = current_task
            case "nav_sys_param_cmd":
                # General read/write parameter channel (nav_sys_param_msg).
                # Routed via nav on Luba Pro/X3; via sys.bidire_comm_cmd on older devices.
                # rw=0 → device reporting current value, rw=1 → app setting a new value.
                #
                # ID  Field                          context values
                # ---  -----------------------------  ------------------------------------------
                #  3   rain_detection                 0=disabled, 1=enabled
                #  5   error queries (read-only)      2=error code, 3=error timestamp — not state
                #  6   turning_mode                   0=zero-turn, 1=multipoint turn
                #  7   traversal_mode                 0=direct to dock, 1=follow perimeter
                #  8   (X3 adapter only, no known caller — ignore)
                # 10   boundary_ride_distance         0=0%, 25=25%, 50=50%
                # 11   collect_grass_enable           0=disabled, 1=enabled
                # 12   animal_protection.mode         0/1/2 (mode enum)
                # 13   animal_protection.status       0=disabled, 1=enabled
                # 20   grass-catcher bin open/close   0=close, 1=open (transient action, no state)
                settings: NavSysParamMsg = nav_msg[1]  # type: ignore
                match settings.id:
                    case 3:
                        device.mower_state.rain_detection = bool(settings.context)
                    case 6:
                        device.mower_state.turning_mode = settings.context
                    case 7:
                        device.mower_state.traversal_mode = settings.context
                    case 10:
                        device.mower_state.boundary_ride_distance = settings.context
                    case 11:
                        device.mower_state.collect_grass_enable = settings.context
                    case 12:
                        device.mower_state.animal_protection.mode = settings.context
                        if settings.context in (1, 2):
                            device.mower_state.animal_protection.status = 1
                        else:
                            device.mower_state.animal_protection.status = 0
                    case 13:
                        device.mower_state.animal_protection.status = settings.context
            case "todev_unable_time_set":
                nav_non_work_time: NavUnableTimeSet = nav_msg[1]  # type: ignore
                device.non_work_hours.non_work_sub_cmd = nav_non_work_time.sub_cmd  # type: ignore
                device.non_work_hours.start_time = nav_non_work_time.unable_start_time
                device.non_work_hours.end_time = nav_non_work_time.unable_end_time
            case "todev_taskctrl_ack":
                task_ctrl_ack: NavTaskCtrlAck = nav_msg[1]  # type: ignore
                device.report_data.dev.sys_status = task_ctrl_ack.nav_state
            case "toapp_edge_points":
                edge_msg: NavEdgePoints = nav_msg[1]  # type: ignore
                device.map.upsert_edge_frame(
                    hash_key=edge_msg.hash,
                    action=edge_msg.action,
                    edge_type=edge_msg.type,
                    total_frame=edge_msg.total_frame,
                    current_frame=edge_msg.current_frame,
                    points=[CommDataCouple(x=p.x, y=p.y) for p in edge_msg.data_couple],
                )
            case "toapp_work_report_ack" | "toapp_work_report_upload":
                work_report: WorkReportInfoAck = nav_msg[1]  # type: ignore
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
        sys_msg = betterproto2.which_one_of(message.sys, "SubSysMsg")  # type: ignore
        match sys_msg[0]:
            case "system_update_buf":
                device.buffer(sys_msg[1])  # type: ignore
                # If the RTK yaw just arrived or changed, regenerate any GeoJSON
                # that was built without (or with a different) yaw correction.
                # Skip during sagas — the saga's on_complete handler will
                # regenerate with the correct yaw once the fetch is done.
                if (
                    not self._is_saga_active()
                    and device.map.area
                    and device.map.geojson_needs_regeneration(device.location.RTK)
                ):
                    device.map.generate_geojson(device.location.RTK, device.location.dock)
            case "toapp_report_data":
                device.update_report_data(sys_msg[1])  # type: ignore
            case "mow_to_app_info":
                device.mow_info(sys_msg[1])  # type: ignore
            case "system_tard_state_tunnel":
                device.run_state_update(sys_msg[1])  # type: ignore
            case "bidire_comm_cmd":
                # General read/write channel for non-Pro (Luba 1) devices — mirrors
                # nav_sys_param_cmd for Pro/X3.  Same ID table applies; IDs 6/7/10/11
                # are only sent here on devices where is_luba_pro() is False.
                comm_cmd: SysCommCmd = sys_msg[1]  # type: ignore
                match comm_cmd.id:
                    case 3:
                        device.mower_state.rain_detection = bool(comm_cmd.context)
                    case 6:
                        device.mower_state.turning_mode = comm_cmd.context
                    case 7:
                        device.mower_state.traversal_mode = comm_cmd.context
                    case 11:
                        device.mower_state.collect_grass_enable = comm_cmd.context
                    case 12:
                        device.mower_state.animal_protection.mode = comm_cmd.context
                    case 13:
                        device.mower_state.animal_protection.status = comm_cmd.context
            case "todev_time_ctrl_light":
                ctrl_light: TimeCtrlLight = sys_msg[1]  # type: ignore
                side_led: SideLight = SideLight.from_dict(ctrl_light.to_dict(casing=betterproto2.Casing.SNAKE))
                device.mower_state.side_led = side_led
            case "toapp_lora_cfg_rsp":
                lora_cfg: LoraCfgRsp = sys_msg[1]  # type: ignore
                device.mower_state.lora_config = lora_cfg.cfg
            case "device_product_type_info":
                device_product_type: DeviceProductTypeInfoT = sys_msg[1]  # type: ignore
                if device_product_type.main_product_type != "" or device_product_type.sub_product_type != "":
                    device.mower_state.model_id = device_product_type.main_product_type
                    device.mower_state.sub_model_id = device_product_type.sub_product_type
            case "toapp_dev_fw_info":
                device_fw_info: DeviceFwInfo = sys_msg[1]  # type: ignore
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
        driver_msg = betterproto2.which_one_of(message.driver, "SubDrvMsg")  # type: ignore
        match driver_msg[0]:
            case "current_cutter_mode":
                cutter_work_mode: AppGetCutterWorkMode = driver_msg[1]  # type: ignore
                device.mower_state.cutter_mode = cutter_work_mode.current_cutter_mode
                device.mower_state.cutter_rpm = cutter_work_mode.current_cutter_rpm
            case "cutter_mode_ctrl_by_hand":
                cutter_work_mode_set: AppSetCutterWorkMode = driver_msg[1]  # type: ignore
                device.mower_state.cutter_mode = cutter_work_mode_set.cutter_mode
            case "bidire_speed_read_set":
                speed_msg: DrvSrSpeed = driver_msg[1]  # type: ignore
                device.mower_state.travel_speed = speed_msg.speed
            case "toapp_knife_status_change":
                knife_report: DrvKnifeChangeReport = driver_msg[1]  # type: ignore
                device.events.blade_height_event.is_start = knife_report.is_start
                device.events.blade_height_event.start_height = knife_report.start_height
                device.events.blade_height_event.end_height = knife_report.end_height
                device.events.blade_height_event.cur_height = knife_report.cur_height

    def _update_net_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update network data fields on *device* in-place."""
        net_msg = betterproto2.which_one_of(message.net, "NetSubType")  # type: ignore
        match net_msg[0]:
            case "toapp_wifi_iot_status":
                wifi_iot_status: WifiIotStatusReport = net_msg[1]  # type: ignore
                if wifi_iot_status.productkey:
                    # Don't clobber a product_key already seeded from the device list.
                    device.mower_state.product_key = wifi_iot_status.productkey
            case "toapp_devinfo_resp":
                toapp_devinfo_resp: DrvDevInfoResp = net_msg[1]  # type: ignore
                for resp in toapp_devinfo_resp.resp_ids:
                    if resp.res == DrvDevInfoResult.DRV_RESULT_SUC and resp.id == 1 and resp.type == 6:
                        device.mower_state.swversion = resp.info
                        device.device_firmwares.device_version = resp.info
            case "toapp_networkinfo_rsp":
                get_network_info_resp: GetNetworkInfoRsp = net_msg[1]  # type: ignore
                device.mower_state.wifi_mac = get_network_info_resp.wifi_mac
                device.mower_state.wifi_ssid = get_network_info_resp.wifi_ssid
                device.report_data.connect.wifi_rssi = get_network_info_resp.wifi_rssi
                device.mower_state.ip = get_network_info_resp.ip
                device.mower_state.mask = get_network_info_resp.mask
                device.mower_state.gateway = get_network_info_resp.gateway

            case "toapp_upgrade_report":
                upgrade_report: DrvUpgradeReport = net_msg[1]  # type: ignore
                device.events.ota_progress.devname = upgrade_report.devname
                device.events.ota_progress.otaid = upgrade_report.otaid
                device.events.ota_progress.version = upgrade_report.version
                device.events.ota_progress.progress = upgrade_report.progress
                device.events.ota_progress.result = upgrade_report.result
                device.events.ota_progress.message = upgrade_report.message
                device.events.ota_progress.recv_cnt = upgrade_report.recv_cnt
            case "toapp_mnet_info_rsp":
                mnet_info_rsp: GetMnetInfoRsp = net_msg[1]  # type: ignore
                if mnet_info_rsp.mnet is not None:
                    device.report_data.dev.mnet_info = device.report_data.dev.mnet_info.from_dict(
                        mnet_info_rsp.mnet.to_dict(casing=betterproto2.Casing.SNAKE)
                    )

    def _update_base_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update base station RTK data from LubaMsg.base.to_app response."""
        base_msg = betterproto2.which_one_of(message.base, "BaseStationSubType")  # type: ignore
        match base_msg[0]:
            case "to_app":
                resp: ResponseBasestationInfoT = base_msg[1]  # type: ignore
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
        mul_msg = betterproto2.which_one_of(message.mul, "SubMul")  # type: ignore
        match mul_msg[0]:
            case "set_audio":
                audio_msg: MulSetAudio = mul_msg[1]  # type: ignore
                if audio_msg.au_language is not None:
                    device.mower_state.audio.language = audio_msg.au_language.name
                if audio_msg.at_switch is not None:
                    device.mower_state.audio.volume = audio_msg.at_switch
                if audio_msg.sex is not None:
                    device.mower_state.audio.sex = audio_msg.sex.value
            case "audio_cfg":
                cfg_msg: MulAudioCfg = mul_msg[1]  # type: ignore
                device.mower_state.audio.volume = cfg_msg.au_switch
                device.mower_state.audio.language = cfg_msg.au_language.name
                device.mower_state.audio.sex = cfg_msg.sex.value
            case "get_lamp_rsp":
                lamp_resp: Getlamprsp = mul_msg[1]  # type: ignore
                device.mower_state.lamp_info.lamp_bright = lamp_resp.lamp_bright
                if lamp_resp.get_ids in (1126, 1127):
                    device.mower_state.lamp_info.lamp_bright = lamp_resp.lamp_bright
                    device.mower_state.lamp_info.manual_light = (
                        lamp_resp.lamp_manual_ctrl == LampManualCtrlSta.manual_power_on
                    )
                if lamp_resp.get_ids == 1123:
                    device.mower_state.lamp_info.lamp_bright = lamp_resp.lamp_bright
                    device.mower_state.lamp_info.night_light = lamp_resp.lamp_ctrl == LampCtrlSta.power_ctrl_on

    def apply_properties(self, current: MowingDevice, properties: ThingPropertiesMessage) -> MowingDevice:  # type: ignore
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
                net = json.loads(net_prop.value)  # type: ignore
                device.mower_state.wifi_mac = str(net.get("wifi_sta_mac", device.mower_state.wifi_mac))
                device.mower_state.ble_mac = str(net.get("bt_mac", device.mower_state.ble_mac))
                device.mower_state.wifi_ssid = str(net.get("ssid", device.mower_state.wifi_ssid))
                device.mower_state.ip_address = str(net.get("ip", device.mower_state.ip_address))
                device.report_data.connect.wifi_rssi = int(net.get("wifi_rssi", device.report_data.connect.wifi_rssi))
                if (bat_cycles := net.get("bat_cycles")) is not None:
                    device.report_data.maintenance.bat_cycles = int(bat_cycles)
            except (ValueError, KeyError, TypeError):
                _logger.debug("MowerStateReducer: failed to parse networkInfo property")

        if dev_ver_info := items.deviceVersionInfo:
            try:
                blob = json.loads(dev_ver_info.value)  # type: ignore
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
        if battery_prop := items.batteryPercentage:
            device.report_data.dev.battery_val = int(battery_prop.value)  # type: ignore
        if state_prop := items.deviceState:
            device.report_data.dev.sys_status = int(state_prop.value)  # type: ignore
        if knife_prop := items.knifeHeight:
            device.report_data.work.knife_height = int(knife_prop.value)  # type: ignore

        if other_info := items.deviceOtherInfo:
            try:
                info = json.loads(other_info.value)  # type: ignore
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
                ota = OTAProgressItems.from_dict(ota_prop.value)  # type: ignore
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

    def apply_mammotion_properties(  # type: ignore
        self, current: MowingDevice, properties: MammotionPropertiesMessage
    ) -> MowingDevice:
        """Extract mower state from a Mammotion MQTT flat property push.

        Mirrors :meth:`apply_properties` but reads from the already-typed
        :class:`~pymammotion.data.mqtt.mammotion_properties.DeviceProperties`
        directly (no ``Item.value`` wrappers).
        """
        device: MowingDevice = dataclasses.replace(current)
        device.mower_state = copy.deepcopy(current.mower_state)
        device.device_firmwares = copy.deepcopy(current.device_firmwares)
        device.report_data = copy.deepcopy(current.report_data)
        p = properties.params

        device.report_data.dev.battery_val = p.battery_percentage
        device.report_data.dev.sys_status = p.device_state
        device.report_data.work.knife_height = p.knife_height
        if p.device_version:
            device.device_firmwares.device_version = p.device_version
        if p.lora_general_config:
            device.mower_state.lora_config = p.lora_general_config
        if p.ext_mod:
            device.mower_state.model = p.ext_mod
        if p.int_mod:
            device.mower_state.internal_model = p.int_mod
        if p.bms_hardware_version:
            device.mower_state.battery_hardware = p.bms_hardware_version

        for attr, fw_type in (
            ("stm32_h7_version", "1"),
            ("mc_boot_version", "8"),
            ("left_motor_version", "3"),
            ("right_motor_version", "4"),
            ("left_motor_boot_version", "9"),
            ("right_motor_boot_version", "10"),
            ("bms_version", "7"),
            ("rtk_version", "5"),
        ):
            if v := getattr(p, attr, ""):
                _apply_mower_fw_module(device.device_firmwares, fw_type, v)

        try:
            if device_version_info := p.device_version_info:
                if device_version_info.dev_ver:
                    device.device_firmwares.device_version = device_version_info.dev_ver
                for module in device_version_info.fw_info:
                    if module.v:
                        _apply_mower_fw_module(device.device_firmwares, module.t, module.v)
        except (AttributeError, TypeError):
            _logger.debug("MowerStateReducer: failed to apply deviceVersionInfo (mammotion)")

        # seems to be different to the devices own lat lon for some reason
        # if coordinate := p.coordinate:
        # coordinate.lat/lon arrive in radians; device.location.device is stored in degrees.
        # if coordinate.lat != 0:
        #     device.location.device.latitude = math.degrees(coordinate.lat)
        # if coordinate.lon != 0:
        #     device.location.device.longitude = math.degrees(coordinate.lon)

        try:
            if net := p.network_info:
                device.mower_state.wifi_mac = net.wifi_sta_mac or device.mower_state.wifi_mac
                device.mower_state.ble_mac = net.bt_mac or device.mower_state.ble_mac
                device.mower_state.wifi_ssid = net.ssid or device.mower_state.wifi_ssid
                device.mower_state.ip_address = net.ip or device.mower_state.ip_address
                device.report_data.connect.wifi_rssi = net.wifi_rssi
                if net.mileage:
                    device.report_data.dev.mileage = int(net.mileage)
                if net.wt_sec is not None:
                    device.report_data.dev.work_time_sec = int(net.wt_sec)
                if net.bat_cycles:
                    device.report_data.maintenance.bat_cycles = int(net.bat_cycles)
        except (AttributeError, ValueError, TypeError):
            _logger.debug("MowerStateReducer: failed to apply networkInfo (mammotion)")

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

    def apply(self, current: PoolCleanerDevice, message: LubaMsg) -> PoolCleanerDevice:  # type: ignore
        """Apply *message* to *current* and return the updated copy."""
        device: PoolCleanerDevice = dataclasses.replace(current)
        if not device.online:
            device.online = True

        sub_msg_type = betterproto2.which_one_of(message, "LubaSubMsg")[0]
        if sub_msg_type == "ctrl":
            # ``LubaMsg.ctrl`` is the Spino-only SpinoCtrl envelope; right
            # now it only carries ``plan_job_set`` (schedule CRUD).  See
            # ``docs/tasks_and_schedules.md`` § 2.
            if message.ctrl is not None and message.ctrl.plan_job_set is not None:
                self._update_plan_job_set(device, message.ctrl.plan_job_set)
            return device
        if sub_msg_type != "sys":
            # Only the sys + ctrl envelopes carry Spino payloads we currently model.
            return device

        sys_msg = betterproto2.which_one_of(message.sys, "SubSysMsg")  # type: ignore
        match sys_msg[0]:
            case "report_info":
                device.pool_state = copy.deepcopy(current.pool_state)
                self._update_report_info(device, sys_msg[1])  # type: ignore
            case "app_downlink_cmd":
                device.pool_state = copy.deepcopy(current.pool_state)
                device.pool_map = copy.deepcopy(current.pool_map)
                self._update_app_downlink_cmd(device, sys_msg[1])  # type: ignore
            case "bidire_comm_cmd":
                device.pool_state = copy.deepcopy(current.pool_state)
                self._update_toggle(device, sys_msg[1])  # type: ignore
            case "system_update_buf":
                device.pool_state = copy.deepcopy(current.pool_state)
                self._update_system_update_buf(device, sys_msg[1])  # type: ignore
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

        # SpinoSysStatus / SpinoWorkMode are UnknownTolerantIntEnum — an unmodelled
        # wire value resolves to UNKNOWN (logged once) rather than raising.
        device.pool_state.sys_status = SpinoSysStatus(status.sys_status)
        device.pool_state.work_mode = SpinoWorkMode(status.work_mode)
        device.pool_state.battery = status.bat_val

    def _update_toggle(self, device: PoolCleanerDevice, cmd: SysCommCmd) -> None:
        """Apply a ``SysCommCmd`` (``allpowerfullRW``) read/ack to a pool toggle.

        ``cmd.id`` is the toggle (see :class:`SpinoToggle`) and ``cmd.context`` its
        0/1 value.  IDs we don't model (mower-side generic RW) are ignored.
        """
        try:
            toggle = SpinoToggle(cmd.id)
        except ValueError:
            _logger.error(
                "PoolStateReducer: ignoring unknown SysCommCmd id=%d for %s",
                cmd.id,
                device.name,
            )
            return
        setattr(device.pool_state, toggle.name, bool(cmd.context))

    def _update_app_downlink_cmd(self, device: PoolCleanerDevice, cmd: AppDownlinkCmdT) -> None:
        """Apply an incoming ``AppDownlinkCmdT`` (settings ack or map data) to *device*.

        **Map/line geometry** — the device always populates ``map_info`` (field 6)
        regardless of whether the command was ``app_get_map_cmd`` (3) or
        ``app_get_line_cmd`` (4).  The ``cmd`` field is the authoritative
        discriminant (APK source: ``MACarDataManager``, case 23).

        Multi-packet transfers use ``pack_index`` (1-based) and ``pack_num``
        alongside ``MapTrans.tag`` (1=transmitting / 0=completed / 2=failed).
        ``pack_index == 1`` signals the start of a new transfer and resets the
        accumulation buffer so stale data from a previous failed fetch is discarded.
        """
        # Settings — only update fields the device actually populated.  WallMaterial
        # / PoolBottomType are UnknownTolerantIntEnum (unknown → UNKNOWN, logged once).
        if cmd.wall_material is not None:
            device.pool_state.wall_material = WallMaterial(cmd.wall_material)
        if cmd.bottom_type is not None:
            device.pool_state.bottom_type = PoolBottomType(int(cmd.bottom_type))
        if cmd.floor_speed is not None:
            device.pool_state.floor_speed = cmd.floor_speed

        # Pool geometry — the device uses map_info (field 6) for BOTH map and line
        # responses.  line_info (field 7) is never populated in observed traffic.
        map_info = cmd.map_info
        if map_info is None or not map_info.points:
            return

        is_map = cmd.cmd == AppDownlinkCmdTypeE.app_get_map_cmd
        is_line = cmd.cmd == AppDownlinkCmdTypeE.app_get_line_cmd
        if not (is_map or is_line):
            return

        new_points = [PoolPoint(x=p.x, y=p.y) for p in map_info.points]
        tag = map_info.tag  # MapTrans raw int: 0=completed, 1=transmitting, 2=failed

        if tag == MapTrans.failed:
            _logger.warning(
                "PoolStateReducer: %s map/line fetch failed (MapTrans.failed) for %s",
                "boundary" if is_map else "route",
                device.name,
            )
            return

        # pack_index==1 means the first (or only) packet of a new transfer.
        # Reset to avoid accumulating leftover points from a previous fetch.
        existing = device.pool_map.boundary if is_map else device.pool_map.cleaning_path
        if map_info.pack_index == 1:
            accumulated = new_points
        else:
            accumulated = list(existing) + new_points

        if is_map:
            device.pool_map.boundary = accumulated
        else:
            device.pool_map.cleaning_path = accumulated

        _logger.debug(
            "PoolStateReducer: %s %s packet %d/%d (%d pts, total=%d) for %s",
            "boundary" if is_map else "route",
            "completed" if tag == MapTrans.completed else "transmitting",
            map_info.pack_index,
            map_info.pack_num,
            len(new_points),
            map_info.total_points,
            device.name,
        )

    def _update_system_update_buf(self, device: PoolCleanerDevice, buf: SystemUpdateBufMsg) -> None:
        """Parse a ``systemUpdateBuf`` message and apply it to *device*.

        Wire layout (``DeviceConstant.systemUpdateBuf``, ID constants):
          ``[0]``     type_id — only ``SYSTEM_ERR_CODE_ID = 2`` is currently
                      observed on Spino; ID 1 (init config) and 3 (zone state)
                      are mower-specific and silently ignored.
          ``[1]``     buffer length (3 header + 2 × N error pairs).
          ``[2]``     cumulative fault-event counter (``ERR_CODE_CNT_INDEX``).
          ``[3+2i]``  error code (signed int64).
          ``[4+2i]``  Unix timestamp in seconds of the fault event.

        Zero-code entries are trailing padding slots and are filtered out.
        Older firmware sends 10 pairs; newer firmware (len=43) sends 20 pairs.
        """
        data = buf.update_buf_data
        if len(data) < 3:
            return
        buf_id = data[0]
        if buf_id != 2:  # SYSTEM_ERR_CODE_ID — 1 and 3 are mower-only
            _logger.debug(
                "PoolStateReducer: unhandled systemUpdateBuf id=%d for %s",
                buf_id,
                device.name,
            )
            return
        device.pool_state.error_count = int(data[2])
        entries: list[SpinoErrorEntry] = []
        i = 3
        while i + 1 < len(data):
            code = int(data[i])
            stamp = int(data[i + 1])
            if code != 0 or stamp != 0:
                entries.append(SpinoErrorEntry(code=code, timestamp=stamp))
            i += 2
        device.pool_state.error_log = entries

    def _update_plan_job_set(self, device: PoolCleanerDevice, wire: PlanJobSet) -> None:
        """Upsert a Spino plan into ``device.plans`` from a wire ``PlanJobSet``.

        Mirror image of :meth:`MessageSystem._pool_plan_to_proto` — the only
        non-trivial conversion is the **inverted** ``enable`` field
        (``0 == enabled, 1 == disabled``).  Plans without a ``jobid`` (likely
        the empty echo of a DELETE_ALL or an error response) are ignored.

        Also maintains ``device.plans_stale``: set when the device tells us
        ``totalplannum`` is larger than the count we've actually stored,
        cleared once the two match.  The HA polling layer watches that flag
        to decide whether to enqueue another :class:`SpinoPlanFetchSaga`.
        """
        # Mutable copy of the plans dict so dataclass.replace() snapshot
        # semantics in ``apply`` still hold.
        device.plans = dict(device.plans)

        if wire.jobid:
            device.plans[wire.jobid] = PoolPlan(
                cmd=wire.cmd,
                totalplannum=wire.totalplannum,
                planindex=wire.planindex,
                result=wire.result,
                jobid=wire.jobid,
                jobname=wire.jobname,
                userid=wire.userid,
                deviceid=wire.deviceid,
                enabled=wire.enable == 0,
                work_mode=wire.work_mode,
                sub_mode=list(wire.sub_mode),
                speed=wire.speed,
                operating_power=wire.operating_power,
                starttime=wire.starttime,
                startdate=wire.startdate,
                enddate=wire.enddate,
                triggertype=wire.triggertype,
                day=wire.day,
                weeks=list(wire.weeks),
                remained_seconds=wire.remained_seconds,
            )

        if wire.totalplannum and wire.totalplannum > len(device.plans):
            device.plans_stale = True
        elif wire.totalplannum and wire.totalplannum == len(device.plans):
            device.plans_stale = False


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

    def apply(self, current: RTKBaseStationDevice, message: LubaMsg) -> RTKBaseStationDevice:  # type: ignore
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
        sys_msg = betterproto2.which_one_of(message.sys, "SubSysMsg")  # type: ignore
        match sys_msg[0]:
            case "toapp_report_data":
                report: ReportInfoData = sys_msg[1]  # type: ignore
                if report.basestation_info is not None:
                    device.basestation_status = report.basestation_info.basestation_status
                    device.connect_status_since_poweron = report.basestation_info.connect_status_since_poweron
            case "toapp_dev_fw_info":
                fw_info: DeviceFwInfo = sys_msg[1]  # type: ignore
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
        net_msg = betterproto2.which_one_of(message.net, "NetSubType")  # type: ignore
        match net_msg[0]:
            case "toapp_wifi_iot_status":
                wifi_iot: WifiIotStatusReport = net_msg[1]  # type: ignore
                if wifi_iot.productkey:
                    # Don't clobber a product_key already seeded from the device list.
                    device.product_key = wifi_iot.productkey
            case "toapp_networkinfo_rsp":
                net_info: GetNetworkInfoRsp = net_msg[1]  # type: ignore
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
        base_msg = betterproto2.which_one_of(message.base, "BaseStationSubType")  # type: ignore
        match base_msg[0]:
            case "to_app":
                resp: ResponseBasestationInfoT = base_msg[1]  # type: ignore
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

    def apply_properties(  # type: ignore
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
                coord = json.loads(coord_prop.value)  # type: ignore
                # The coordinate property is already in radians (protocol-level unit).
                if (lat := coord.get("lat")) and lat != 0:
                    raw_lat = float(lat)
                    # a1Nc68bGZzX devices report latitude 436° low (value is in radians);
                    # guard on out-of-range so a firmware fix doesn't keep shifting it.
                    if current.product_key == "a1Nc68bGZzX" and abs(raw_lat) > math.pi / 2:
                        raw_lat += math.radians(436)

                    device.lat = raw_lat
                if (lon := coord.get("lon")) and lon != 0:
                    raw_lon = float(lon)
                    if current.product_key == "a1Nc68bGZzX" and abs(raw_lon) > math.pi / 2:
                        raw_lon += math.radians(436)
                    device.lon = raw_lon
            except (ValueError, KeyError, TypeError):
                _logger.debug("RTKStateReducer: failed to parse coordinate property")

        if net_prop := items.networkInfo:
            try:
                net = json.loads(net_prop.value)  # type: ignore
                device.wifi_rssi = int(net.get("wifi_rssi", device.wifi_rssi))
                device.wifi_mac = str(net.get("wifi_sta_mac", device.wifi_mac))
                device.bt_mac = str(net.get("bt_mac", device.bt_mac))
            except (ValueError, KeyError, TypeError):
                _logger.debug("RTKStateReducer: failed to parse networkInfo property")

        if ver_prop := items.deviceVersion:
            device.device_version = str(ver_prop.value)

        if dev_ver_info := items.deviceVersionInfo:
            try:
                blob = json.loads(dev_ver_info.value)  # type: ignore
                # dataclasses.replace() is shallow — copy device_firmwares before the
                # in-place writes below or the previous snapshot is mutated too (and
                # the identity-based diff never reports the change).
                device.device_firmwares = copy.deepcopy(current.device_firmwares)
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
                ota = OTAProgressItems.from_dict(ota_prop.value)  # type: ignore
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


def get_state_reducer(device_name: str, is_saga_active: Callable[[], bool] | None = None) -> StateReducer:
    """Return the appropriate :class:`StateReducer` for *device_name*.

    Dispatches to:
    - :class:`RTKStateReducer` for RTK base stations (RTK, RBS03A0/A1/A2, RTKNB)
    - :class:`PoolStateReducer` for Spino pool cleaners
    - :class:`MowerStateReducer` for all lawn mowers (the historical default)

    *is_saga_active* — optional callable returning True while a saga holds the
    device's command queue.  Forwarded to the reducer so it can skip eager
    geojson regeneration during fetches.

    Picked once per device at handle construction time so the hot path
    doesn't pay an isinstance check on every incoming message.
    """
    # Local import to avoid a circular dependency between the reducer module
    # and the device-type helpers it consults.
    from pymammotion.utility.device_type import DeviceType

    if DeviceType.is_swimming_pool(device_name):
        return PoolStateReducer(is_saga_active)
    if DeviceType.is_rtk(device_name):
        return RTKStateReducer(is_saga_active)
    return MowerStateReducer(is_saga_active)
