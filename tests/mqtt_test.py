import hashlib
import hmac
import json
import os

from linkkit.linkkit import LinkKit
from paho.mqtt.client import Client, MQTTv311, MQTTMessage, connack_string

from pyluba.data.mqtt.event import ThingEventMessage

PRODUCT_KEY = os.environ.get("PRODUCT_KEY")
DEVICE_NAME = os.environ.get("DEVICE_NAME")
DEVICE_SECRET = os.environ.get("DEVICE_SECRET")


def on_message(client, userdata, message: MQTTMessage):
    if message.topic.endswith("/app/down/thing/events"):
        msg = ThingEventMessage(**json.loads(message.payload))
        print(message.topic, repr(msg))
    else:
        print(message.topic, message.payload)
def on_connect(client, userdata, flags, rc):
    print("connected", connack_string(rc))
    client.subscribe("/sys/+/+/app/#")
def on_disconnect(client, userdata, rc):
    print("disconnected", rc)

client_id_ = "asdf"
client_id = f"{client_id_}|securemode=2,signmethod=hmacsha1|"
username = f"{DEVICE_NAME}&{PRODUCT_KEY}"
sign_content = f"clientId{client_id_}deviceName{DEVICE_NAME}productKey{PRODUCT_KEY}"
password = hmac.new(
    DEVICE_SECRET.encode("utf-8"), sign_content.encode("utf-8"),
    hashlib.sha1
).hexdigest()

print(client_id)
print(username)
print(password)


client = Client(
    client_id=client_id,
    protocol=MQTTv311,
)
client.enable_logger()
client.on_message = on_message
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.username_pw_set(username, password)
# TODO get regional hub for MQTT
client.connect("public.itls.eu-central-1.aliyuncs.com")
#client.connect(f"{PRODUCT_KEY}.iot-as-mqtt.eu-central-1.aliyuncs.com")
client.loop_forever()
