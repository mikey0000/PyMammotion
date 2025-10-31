import asyncio
import logging
import os

from aiohttp import ClientSession

from pymammotion import MammotionHTTP
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.const import MAMMOTION_DOMAIN
from pymammotion.mqtt import AliyunMQTT

logger = logging.getLogger(__name__)


async def run():
    EMAIL = os.environ.get("EMAIL")
    PASSWORD = os.environ.get("PASSWORD")

    

    async with ClientSession(MAMMOTION_DOMAIN) as session:
        mammotion = MammotionHTTP()
        luba_http = await mammotion.login(EMAIL, PASSWORD)
        # print(luba_http.data)
        data = mammotion.login_info
        #error_codes = await mammotion.get_all_error_codes()
        #firmware = await mammotion.get_device_ota_firmware(["UTpbwGC7vxd4DpNvbFGL000000"])
        print(mammotion.login_info)
        res = await mammotion.refresh_token()
        print(res)
        return
        cloud_client = CloudIOTGateway(mammotion)

        country_code = data.userInformation.domainAbbreviation
        logger.debug("CountryCode: " + country_code)
        logger.debug("AuthCode: " + data.authorization_code)
        # error_codes = await mammotion.get_all_error_codes()
        # print(error_codes)
        await cloud_client.get_region(country_code)
        await cloud_client.connect()
        await cloud_client.login_by_oauth(country_code)
        await cloud_client.aep_handle()
        await cloud_client.session_by_auth_code()

        await cloud_client.list_binding_by_account()
    logging.basicConfig(level=logging.DEBUG)
    logger.getChild("paho").setLevel(logging.WARNING)

    luba = AliyunMQTT(region_id=cloud_client.region_response.data.regionId,
                      product_key=cloud_client.aep_response.data.productKey,
                      device_name=cloud_client.aep_response.data.deviceName,
                      device_secret=cloud_client.aep_response.data.deviceSecret,
                      iot_token=cloud_client.session_by_authcode_response.data.iotToken,
                      client_id=cloud_client.client_id, cloud_client=cloud_client)

    # luba.connect() blocks further calls
    luba.connect_async()

if __name__ ==  '__main__':
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    cloud_client = event_loop.run_until_complete(run())

    # logging.basicConfig(level=logging.DEBUG)
    # logger.getChild("paho").setLevel(logging.WARNING)
    #
    # luba = MammotionMQTT(region_id=cloud_client.region_response.data.regionId,
    #                 product_key=cloud_client.aep_response.data.productKey,
    #                 device_name=cloud_client.aep_response.data.deviceName,
    #                 device_secret=cloud_client.aep_response.data.deviceSecret, iot_token=cloud_client.session_by_authcode_response.data.iotToken, client_id=cloud_client.client_id, cloud_client=cloud_client)


    #luba.connect() blocks further calls
    # luba.connect_async()

    event_loop.run_forever()