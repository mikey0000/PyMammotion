import json

from pymammotion.aliyun.exceptions import DeviceOfflineException, GatewayTimeoutException
from pymammotion.client import MammotionClient
from pymammotion.data.model.device import RTKBaseStationDevice
from pymammotion.http.model.http import CheckDeviceVersion

# TODO(task #8): RTKBaseStationDevice is a separate dataclass from MowingDevice, and the new
# MammotionClient does not yet expose CloudIOTGateway (only AliyunMQTTTransport is
# stored as _cloud_transport).  Full migration of the HTTP polling path
# (get_device_properties, get_device_ota_firmware) requires either:
#   a) storing CloudIOTGateway on MammotionClient (add _cloud_client attribute), or
#   b) moving RTK state into MowingDevice so all devices share the same model.
# Until that work is done, this file uses MammotionClient for device lookup but
# still relies on the old MammotionRTKDeviceManager (via mammotion.get_rtk_device_by_name)
# for the cloud_client and RTK-specific state.  See task #7 and #8.
from pymammotion.mammotion.devices.mammotion import Mammotion
from pymammotion.transport.base import SessionExpiredError


class HomeAssistantRTKApi:
    """Home Assistant API adapter for RTK base station devices."""

    def __init__(self) -> None:
        # TODO(task #8): Replace Mammotion() with MammotionClient() once CloudIOTGateway
        # is accessible from MammotionClient and RTK state is unified with MowingDevice.
        self._mammotion = Mammotion()
        self._client = MammotionClient()

    @property
    def mammotion(self) -> Mammotion:
        """Return the legacy Mammotion device manager used for RTK device lookup."""
        return self._mammotion

    @property
    def client(self) -> MammotionClient:
        """Return the MammotionClient instance."""
        return self._client

    async def update(self, device_name: str) -> RTKBaseStationDevice:
        """Update RTK data."""
        # TODO(task #8): Replace with self._client.mower(device_name) once RTK devices
        # are registered via MammotionClient.login_and_initiate_cloud and RTKBaseStationDevice
        # state is accessible from DeviceHandle (currently all devices use MowingDevice).
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
        except SessionExpiredError:
            """Cloud IOT session expired."""
            return device.state
        except DeviceOfflineException:
            device.state.online = False
        except GatewayTimeoutException:
            """Gateway is timing out again."""
        return device.state
