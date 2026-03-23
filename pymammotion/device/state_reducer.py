"""StateReducer — decodes LubaMsg and applies it to a MowingDevice copy."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

import betterproto2

from pymammotion.data.model.device_info import SideLight
from pymammotion.data.model.hash_list import (
    AreaHashNameList,
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
    Getlamprsp,
    GetNetworkInfoRsp,
    LubaMsg,
    NavGetCommDataAck,
    NavGetHashListAck,
    NavPlanJobSet,
    NavReqCoverPath,
    NavSysParamMsg,
    NavUnableTimeSet,
    SvgMessageAckT,
    TimeCtrlLight,
    WifiIotStatusReport,
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

        Works on a deep copy of ``current`` so the input is never mutated.
        Returns the updated copy regardless of whether anything changed.
        """
        device: MowingDevice = copy.deepcopy(current)

        # Mark online on any incoming message
        if not device.online:
            device.online = True

        res = betterproto2.which_one_of(message, "LubaSubMsg")
        match res[0]:
            case "nav":
                self._update_nav_data(device, message)
            case "sys":
                self._update_sys_data(device, message)
            case "driver":
                self._update_driver_data(device, message)
            case "net":
                self._update_net_data(device, message)
            case "mul":
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
            case "toapp_svg_msg":
                common_svg_data: SvgMessageAckT = nav_msg[1]
                device.map.update(SvgMessage.from_dict(common_svg_data.to_dict(casing=betterproto2.Casing.SNAKE)))
            case "toapp_all_hash_name":
                hash_names: AppGetAllAreaHashName = nav_msg[1]
                converted_list = [AreaHashNameList(name=item.name, hash=item.hash) for item in hash_names.hashnames]
                device.map.area_name = converted_list
            case "bidire_reqconver_path":
                work_settings: NavReqCoverPath = nav_msg[1]
                current_task = CurrentTaskSettings.from_dict(work_settings.to_dict(casing=betterproto2.Casing.SNAKE))
                if current_task.path_hash == 0:
                    device.map.current_mow_path = {}
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
            case "todev_unable_time_set":
                nav_non_work_time: NavUnableTimeSet = nav_msg[1]
                device.non_work_hours.non_work_sub_cmd = nav_non_work_time.sub_cmd
                device.non_work_hours.start_time = nav_non_work_time.unable_start_time
                device.non_work_hours.end_time = nav_non_work_time.unable_end_time

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
            case "todev_time_ctrl_light":
                ctrl_light: TimeCtrlLight = sys_msg[1]
                side_led: SideLight = SideLight.from_dict(ctrl_light.to_dict(casing=betterproto2.Casing.SNAKE))
                device.mower_state.side_led = side_led
            case "device_product_type_info":
                device_product_type: DeviceProductTypeInfoT = sys_msg[1]
                if device_product_type.main_product_type != "" or device_product_type.sub_product_type != "":
                    device.mower_state.model_id = device_product_type.main_product_type
                    device.mower_state.sub_model_id = device_product_type.sub_product_type
            case "toapp_dev_fw_info":
                device_fw_info: DeviceFwInfo = sys_msg[1]
                device.device_firmwares.device_version = device_fw_info.version
                device.mower_state.swversion = device_fw_info.version

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

    def _update_mul_data(self, device: MowingDevice, message: LubaMsg) -> None:
        """Update media/light data fields on *device* in-place."""
        mul_msg = betterproto2.which_one_of(message.mul, "SubMul")
        match mul_msg[0]:
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
