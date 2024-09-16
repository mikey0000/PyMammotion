# __init__.py

# version of Luba API
# TODO export the three interface types
__version__ = "0.0.5"

import asyncio
import logging
import os

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway

# works outside HA on its own
from pymammotion.bluetooth.ble import MammotionBLE
from pymammotion.http.http import MammotionHTTP, connect_http

# TODO make a working device that will work outside HA too.
from pymammotion.mqtt import MammotionMQTT

__all__ = ["MammotionBLE", "MammotionHTTP", "connect_http", "MammotionMQTT"]

logger = logging.getLogger(__name__)

# TODO provide interface to pick between mqtt/cloud/bluetooth

if __name__ == "__main__":
    """Values are generated from calls to aliyun APIs, can find what order is required in the login_test.py."""
    logging.basicConfig(level=logging.DEBUG)
    logger.getChild("paho").setLevel(logging.WARNING)
    PRODUCT_KEY = os.environ.get("PRODUCT_KEY")
    DEVICE_NAME = os.environ.get("DEVICE_NAME")
    DEVICE_SECRET = os.environ.get("DEVICE_SECRET")
    CLIENT_ID = os.environ.get("CLIENT_ID")
    IOT_TOKEN = os.environ.get("IOT_TOKEN")
    REGION = os.environ.get("REGION")
    cloud_client = CloudIOTGateway()
    luba = MammotionMQTT(
        iot_token=IOT_TOKEN or "",
        region_id=REGION or "",
        product_key=PRODUCT_KEY or "",
        device_name=DEVICE_NAME or "",
        device_secret=DEVICE_SECRET or "",
        client_id=CLIENT_ID or "",
        cloud_client=cloud_client,
    )
    luba.connect_async()

    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    event_loop.run_forever()
