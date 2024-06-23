import asyncio
import logging
import os

from aiohttp import ClientSession

from pyluba import LubaHTTP
from pyluba.aliyun.cloud_gateway import CloudIOTGateway
from pyluba.mammotion.commands.mammotion_command import MammotionCommand
from pyluba.mqtt.mqtt import LubaMQTT, logger


async def run():
    EMAIL = os.environ.get("EMAIL")
    PASSWORD = os.environ.get("PASSWORD")

    cloud_client = CloudIOTGateway()

   # aep_result = cloud_client.aep_handle()
    # gives us a device secret / key etc
   # connect_result = cloud_client.connect()
    # returns the vid used with loginbyoauth
    #cloud_client.aep_handle()

    
    if cloud_client.check_or_refresh_session() == False:
        async with ClientSession("https://domestic.mammotion.com") as session:
            lubaHttp = await LubaHTTP.login(session, EMAIL, PASSWORD)
            # print(lubaHttp.data)
            countryCode = lubaHttp.data.userInformation.domainAbbreviation
    # countryCode, lubaHttp.authorization_code
            print("CountryCode: " + countryCode)
            print("AuthCode: " + lubaHttp.data.authorization_code)
            cloud_client.get_region(countryCode, lubaHttp.data.authorization_code)
            await cloud_client.connect()
            await cloud_client.login_by_oauth(countryCode, lubaHttp.data.authorization_code)
            cloud_client.aep_handle()
            cloud_client.session_by_auth_code()

            cloud_client.list_binding_by_account()
            return cloud_client
    else:
        return cloud_client


        # should return new device secrete / key etc

        # gives us devices and iotId for querying APIs


if __name__ ==  '__main__':
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    cloud_client = event_loop.run_until_complete(run())

    logging.basicConfig(level=logging.DEBUG)
    logger.getChild("paho").setLevel(logging.WARNING)

    luba = LubaMQTT(region_id=cloud_client._region.get('regionId'),
                    product_key=cloud_client._mqtt_credentials['productKey'],
                    device_name=cloud_client._mqtt_credentials['deviceName'],
                    device_secret=cloud_client._mqtt_credentials['deviceSecret'], iot_token=cloud_client._iotCredentials['iotToken'], client_id=cloud_client._client_id)

    luba._cloud_client = cloud_client
    #luba.connect() blocks further calls
    luba.connect_async()

    event_loop.run_forever()