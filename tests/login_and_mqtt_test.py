import asyncio
import logging
import os

from aiohttp import ClientSession

from pyluba import LubaHTTP
from pyluba.aliyun.cloud_gateway import CloudIOTGateway
from pyluba.const import MAMMOTION_DOMAIN
from pyluba.mammotion.commands.mammotion_command import MammotionCommand
from pyluba.mqtt.mqtt import LubaMQTT, logger
from pyluba.mammotion.devices.luba_cloud import MammotionBaseCloudDevice

logger = logging.getLogger(__name__)


async def run():
    EMAIL = os.environ.get('EMAIL')
    PASSWORD = os.environ.get('PASSWORD')
    cloud_client = CloudIOTGateway()

    

    async with ClientSession(MAMMOTION_DOMAIN) as session:
        luba_http = await LubaHTTP.login(session, EMAIL, PASSWORD)
        country_code = luba_http.data.userInformation.domainAbbreviation
        logger.debug("CountryCode: " + country_code)
        logger.debug("AuthCode: " + luba_http.data.authorization_code)
        cloud_client.get_region(country_code, luba_http.data.authorization_code)
        await cloud_client.connect()
        await cloud_client.login_by_oauth(country_code, luba_http.data.authorization_code)
        cloud_client.aep_handle()
        cloud_client.session_by_auth_code()

        cloud_client.list_binding_by_account()
        return cloud_client

if __name__ ==  '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.getChild("paho").setLevel(logging.WARNING)
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    cloud_client = event_loop.run_until_complete(run())

    

    _luba_mqtt = LubaMQTT(region_id=cloud_client._region.data.regionId,
                    product_key=cloud_client._aep_response.data.productKey,
                    device_name=cloud_client._aep_response.data.deviceName,
                    device_secret=cloud_client._aep_response.data.deviceSecret, iot_token=cloud_client._session_by_authcode_response.data.iotToken, client_id=cloud_client._client_id)

    _luba_mqtt._cloud_client = cloud_client
    #luba.connect() blocks further calls
    _luba_mqtt.connect_async()

    _devices_list = []
    for device in cloud_client._listing_dev_by_account_response.data.data:
        if(device.deviceName.startswith(("Luba-", "Yuka-"))):
            dev = MammotionBaseCloudDevice (
                mqtt_client=_luba_mqtt,
                iot_id=device.iotId,
                device_name=device.deviceName,
                nick_name=device.nickName
            )
            _devices_list.append(dev)

    #Assign callback based on iotId
    _luba_mqtt.on_message = lambda topic, payload, iotId: [
        device._on_mqtt_message(topic, payload) for device in _devices_list if device.iot_id == iot_id
    ]

    logger.debug(_devices_list)

    event_loop.run_forever()