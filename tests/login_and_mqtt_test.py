import asyncio
import logging
import os

from pymammotion.data.model.device import MowingDevice
from pymammotion.mammotion.devices.mammotion_cloud import MammotionCloud
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.http.http import connect_http
from pymammotion.mqtt.mammotion_mqtt import MammotionMQTT, logger
from pymammotion.mammotion.devices.mammotion import MammotionBaseCloudDevice

_LOGGER = logging.getLogger(__name__)


async def run() -> CloudIOTGateway:
    EMAIL = os.environ.get('EMAIL')
    PASSWORD = os.environ.get('PASSWORD')
    cloud_gateway = CloudIOTGateway()

    mammotion_http = await connect_http(EMAIL, PASSWORD)
    country_code = mammotion_http.login_info.userInformation.domainAbbreviation
    _LOGGER.debug("CountryCode: " + country_code)
    _LOGGER.debug("AuthCode: " + mammotion_http.login_info.authorization_code)
    cloud_gateway.get_region(country_code, mammotion_http.login_info.authorization_code)
    await cloud_gateway.connect()
    await cloud_gateway.login_by_oauth(country_code, mammotion_http.login_info.authorization_code)
    cloud_gateway.aep_handle()
    cloud_gateway.session_by_auth_code()
    # await mammotion_http.get_all_error_codes()

    print(cloud_gateway.list_binding_by_account())
    return cloud_gateway


async def sync_status_and_map(cloud_device: MammotionBaseCloudDevice):
    await asyncio.sleep(1)
    await cloud_device.start_sync(0)
    await asyncio.sleep(2)
    # await cloud_device.start_map_sync()

    while (True):
        print(cloud_device.mower)
        await asyncio.sleep(5)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.getChild("paho").setLevel(logging.WARNING)
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    cloud_client: CloudIOTGateway = event_loop.run_until_complete(run())

    _mammotion_mqtt = MammotionCloud(MammotionMQTT(region_id=cloud_client.region_response.data.regionId,
                                                   product_key=cloud_client.aep_response.data.productKey,
                                                   device_name=cloud_client.aep_response.data.deviceName,
                                                   device_secret=cloud_client.aep_response.data.deviceSecret,
                                                   iot_token=cloud_client.session_by_authcode_response.data.iotToken,
                                                   client_id=cloud_client.client_id,
                                                   cloud_client=cloud_client))

    _mammotion_mqtt.connect_async()

    _devices_list = []
    for device in cloud_client.devices_by_account_response.data.data:
        if (device.deviceName.startswith(("Luba-", "Yuka-"))):
            dev = MammotionBaseCloudDevice(
                mqtt=_mammotion_mqtt,
                cloud_device=device,
                mowing_state=MowingDevice()
            )
            _devices_list.append(dev)

    event_loop.run_forever()
