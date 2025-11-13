import asyncio
import logging
import os
import traceback

from pymammotion.mqtt.aliyun_mqtt import logger
from pymammotion.data.model.account import Credentials
from pymammotion.mammotion.devices.mammotion import ConnectionPreference

logger = logging.getLogger(__name__)


async def run():
    EMAIL = os.environ.get('EMAIL')
    PASSWORD = os.environ.get('PASSWORD')
    DEVICE_NAME = "Luba-VSXXXXXX"
    
    try:
        credentials = Credentials(
        email=EMAIL,
        password=PASSWORD
        )   
        _mammotion = await create_devices(ble_device=None, cloud_credentials=credentials, preference=ConnectionPreference.WIFI)



        await _mammotion.get_stream_subscription(DEVICE_NAME)
        
        return _mammotion
    except Exception as ex:
        logger.error(f"{ex}")
        logger.error(traceback.format_exc())
        return None
    

if __name__ ==  '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.getChild("paho").setLevel(logging.WARNING)
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    cloud_client = event_loop.run_until_complete(run())
    event_loop.run_forever()