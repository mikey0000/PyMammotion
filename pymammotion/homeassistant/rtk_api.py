import json

from pymammotion.aliyun.cloud_gateway import DeviceOfflineException, GatewayTimeoutException, SetupException
from pymammotion.data.model.device import RTKDevice
from pymammotion.http.model.http import CheckDeviceVersion
from pymammotion.mammotion.devices.mammotion import Mammotion


class HomeAssistantRTKApi:
    def __init__(self) -> None:
        self._mammotion = Mammotion()

    @property
    def mammotion(self) -> Mammotion:
        return self._mammotion

    async def update(self, device_name: str) -> RTKDevice:
        """Update RTK data."""
        device = self.mammotion.get_rtk_device_by_name(device_name)
        try:
            response = await device.cloud_client.get_device_properties(device.iot_id)
            if response.code == 200:
                if data := response.data:
                    if ota_progress := data.otaProgress:
                        device.state.update_check = CheckDeviceVersion.from_dict(ota_progress.value)
                    if network_info := data.networkInfo:
                        network = json.loads(network_info.value)
                        device.state.wifi_rssi = network["wifi_rssi"]
                        device.state.wifi_sta_mac = network["wifi_sta_mac"]
                        device.state.bt_mac = network["bt_mac"]
                    if coordinate := data.coordinate:
                        coord_val = json.loads(coordinate.value)
                        if device.state.lat == 0:
                            device.state.lat = coord_val["lat"]
                        if device.state.lon == 0:
                            device.state.lon = coord_val["lon"]
                    if device_version := data.deviceVersion:
                        device.state.device_version = device_version.value
            device.state.online = True

            ota_info = await device.cloud_client.mammotion_http.get_device_ota_firmware([device.state.iot_id])
            if check_versions := ota_info.data:
                for check_version in check_versions:
                    if check_version.device_id == device.state.iot_id:
                        device.state.update_check = check_version
            return device.state
        except SetupException:
            """Cloud IOT Gateway is not setup."""
            return device.state
        except DeviceOfflineException:
            device.state.online = False
        except GatewayTimeoutException:
            """Gateway is timing out again."""
        return device.state
