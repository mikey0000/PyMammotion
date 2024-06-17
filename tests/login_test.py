import asyncio
import os

from aiohttp import ClientSession

from pyluba import LubaHTTP
from pyluba.aliyun.cloud_gateway import CloudIOTGateway


async def run():
    EMAIL = os.environ.get("EMAIL")
    PASSWORD = os.environ.get("PASSWORD")

    cloud_client = CloudIOTGateway()

    aep_result = cloud_client.aep_handle()
    # gives us a device secret / key etc
    connect_result = cloud_client.connect()
    # returns the vid used with loginbyoauth

    async with ClientSession("https://domestic.mammotion.com") as session:
        lubaHttp = await LubaHTTP.login(session, EMAIL, PASSWORD)
        # print(lubaHttp.data)
        countryCode = lubaHttp.data.userInformation.domainAbbreviation
# countryCode, lubaHttp.authorization_code
        cloud_client.get_region(countryCode, lubaHttp.data.authorization_code)

        cloud_client.login_by_oauth()

        cloud_client.aep_handle()
        # should return new device secrete / key etc
        # try MQTT

        cloud_client.session_by_auth_code()
        # returns iot token

        # https://ap-southeast-1.api-iot.aliyuncs.com/uc/listBindingByAccount
        # {
        #   "id": "05088c01-c103-4f85-913b-c2e0ec3888d9",
        #   "params": {
        #     "pageSize": 100,
        #     "pageNo": 1
        #   },
        #   "request": {
        #     "apiVer": "1.0.8",
        #     "language": "en-US",
        #     "iotToken": "3faaadf229cb77de687e8085470e0b97"
        #   },
        #   "version": "1.0"
        # }
        # gives us devices and iotId for querying APIs


if __name__ ==  '__main__':
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    asyncio.run(run())
