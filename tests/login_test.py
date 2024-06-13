import asyncio
import os

from aiohttp import ClientSession

from pyluba import LubaHTTP
from pyluba.aliyun.cloud_gateway import CloudIOTGateway

async def run():
    EMAIL = os.environ.get("EMAIL")
    PASSWORD = os.environ.get("PASSWORD")

    async with ClientSession("https://domestic.mammotion.com") as session:
        lubaHttp = await LubaHTTP.login(session, EMAIL, PASSWORD)
        # print(lubaHttp.data)
        countryCode = lubaHttp.data.userInformation.domainAbbreviation
# countryCode, lubaHttp.authorization_code
        CloudIOTGateway.get_region(countryCode, lubaHttp.data.authorization_code)

        # TODO
        # POST https://living-account.ap-southeast-1.aliyuncs.com/api/prd/loginbyoauth.json
        # figure out what calls give us the data required to then call
        # POST
        # https://ap-southeast-1.api-iot.aliyuncs.com/app/aepauth/handle
        # which gives MQTT details


if __name__ ==  '__main__':
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    asyncio.run(run())
