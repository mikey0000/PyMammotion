import asyncio
import logging
import os

from aiohttp import ClientSession

from pymammotion import MammotionHTTP
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.const import MAMMOTION_DOMAIN
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.mqtt.mqtt import LubaMQTT, logger

logger = logging.getLogger(__name__)


async def run():
    EMAIL = os.environ.get("EMAIL")
    PASSWORD = os.environ.get("PASSWORD")
    cloud_client = CloudIOTGateway()

    

    async with ClientSession(MAMMOTION_DOMAIN) as session:
        luba_http = await MammotionHTTP.login(session, EMAIL, PASSWORD)
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
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    cloud_client = event_loop.run_until_complete(run())

    logging.basicConfig(level=logging.DEBUG)
    logger.getChild("paho").setLevel(logging.WARNING)

    luba = LubaMQTT(region_id=cloud_client._region.data.regionId,
                    product_key=cloud_client._aep_response.data.productKey,
                    device_name=cloud_client._aep_response.data.deviceName,
                    device_secret=cloud_client._aep_response.data.deviceSecret, iot_token=cloud_client._session_by_authcode_response.data.iotToken, client_id=cloud_client._client_id)

    luba._cloud_client = cloud_client
    #luba.connect() blocks further calls
    luba.connect_async()

    event_loop.run_forever()