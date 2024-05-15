# __init__.py

# version of Luba API
# TODO export the three interface types
__version__ = "0.0.5"

# works outside HA on its own
from pyluba.bluetooth.ble import (
    LubaBLE
)

# TODO make a working device that will work outside HA too.
from pyluba.mammotion.devices import (
    MammotionBaseBLEDevice
)

from pyluba.mqtt.mqtt import (
    LubaMQTT
)

from pyluba.http.http import (
    LubaHTTP,
    connect_http
)




# TODO provide interface to pick between mqtt/cloud/bluetooth

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logger.getChild("paho").setLevel(logging.WARNING)
    PRODUCT_KEY = os.environ.get("PRODUCT_KEY")
    DEVICE_NAME = os.environ.get("DEVICE_NAME")
    DEVICE_SECRET = os.environ.get("DEVICE_SECRET")
    luba = LubaMQTT(product_key=PRODUCT_KEY, device_name=DEVICE_NAME, device_secret=DEVICE_SECRET, client_id="asdf")
    luba.connect_async()
