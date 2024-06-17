import asyncio
import os

from aiohttp import ClientSession

from pyluba import LubaHTTP
from pyluba.aliyun.cloud_gateway import CloudIOTGateway


async def run():
    EMAIL = os.environ.get("EMAIL")
    PASSWORD = os.environ.get("PASSWORD")

    cloud_client = CloudIOTGateway()

   # aep_result = cloud_client.aep_handle()
    # gives us a device secret / key etc
   # connect_result = cloud_client.connect()
    # returns the vid used with loginbyoauth

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

        cloud_client.session_by_auth_code()

        cloud_client.list_binding_by_account()
        #cloud_client.aep_handle()
        # should return new device secrete / key etc

        # gives us devices and iotId for querying APIs


if __name__ ==  '__main__':
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    asyncio.run(run())
