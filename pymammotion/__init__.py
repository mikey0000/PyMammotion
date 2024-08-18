# __init__.py

# version of Luba API
# TODO export the three interface types
__version__ = "0.0.5"

import asyncio
import logging
import os

# works outside HA on its own
from pymammotion.bluetooth.ble import LubaBLE
from pymammotion.http.http import MammotionHTTP, connect_http

# TODO make a working device that will work outside HA too.
from pymammotion.mammotion.devices import MammotionBaseBLEDevice
from pymammotion.mqtt import MammotionMQTT

__all__ = ["LubaBLE", "MammotionHTTP", "connect_http", "MammotionBaseBLEDevice", "MammotionMQTT"]

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
    luba = MammotionMQTT(
        iot_token=IOT_TOKEN,
        region_id=REGION,
        product_key=PRODUCT_KEY,
        device_name=DEVICE_NAME,
        device_secret=DEVICE_SECRET,
        client_id=CLIENT_ID,
    )
    luba.connect_async()

    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    event_loop.run_forever()
