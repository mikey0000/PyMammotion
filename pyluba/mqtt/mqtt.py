import hashlib
import hmac
import json
import logging
import sqlite3
from logging import getLogger
from typing import Callable, Optional, cast

from linkkit.linkkit import LinkKit
from paho.mqtt.client import Client, MQTTMessage, MQTTv311, connack_string

from pyluba.data.model import RapidState
from pyluba.data.mqtt.event import ThingEventMessage
from pyluba.data.mqtt.properties import ThingPropertiesMessage
from pyluba.data.mqtt.status import ThingStatusMessage
from pyluba.luba.base import BaseLuba
from pyluba.mammotion.commands.mammotion_command import MammotionCommand
from pyluba.proto import luba_msg_pb2

logger = getLogger(__name__)


# with sqlite3.connect("messages.db") as conn:
#     conn.execute("CREATE TABLE IF NOT EXISTS messages (topic TEXT, timestamp INTEGER, payload TEXT)")


class LubaMQTT(BaseLuba):

    _cloud_client = None
    def __init__(self, region_id: str, product_key: str, device_name: str, device_secret: str, iot_token: str,
                 client_id: Optional[str] = None):
        super().__init__()

        self.on_connected: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None

        self._product_key = product_key
        self._device_name = device_name
        self._device_secret = device_secret
        self._iot_token = iot_token
        self._mqtt_username = f"{device_name}&{product_key}"
        # linkkit provides the correct MQTT service for all of this and uses paho under the hood
        if client_id is None:
            client_id = f"python-{device_name}"
        self._mqtt_client_id = f"{client_id}|securemode=2,signmethod=hmacsha1|"
        sign_content = f"clientId{client_id}deviceName{device_name}productKey{product_key}"
        self._mqtt_password = hmac.new(
            device_secret.encode("utf-8"), sign_content.encode("utf-8"),
            hashlib.sha1
        ).hexdigest()

        self._client_id = client_id

        self._linkkit_client = LinkKit(region_id, product_key, device_name, device_secret, auth_type="",
                                       client_id=client_id, password=self._mqtt_password, username=self._mqtt_username)

        self._linkkit_client.enable_logger(level=logging.DEBUG)
        self._linkkit_client.on_connect = self._thing_on_connect
        self._linkkit_client.on_disconnect = self._on_disconnect
        self._linkkit_client.on_thing_enable = self._thing_on_thing_enable
        self._linkkit_client.on_topic_message = self._thing_on_topic_message
        #        self._mqtt_host = "public.itls.eu-central-1.aliyuncs.com"
        self._mqtt_host = f"{self._product_key}.iot-as-mqtt.{region_id}.aliyuncs.com"

        self._client = Client(
            client_id=self._mqtt_client_id,
            protocol=MQTTv311,
        )
        self._client.on_message = self._on_message
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.username_pw_set(self._mqtt_username, self._mqtt_password)
        self._client.enable_logger(logger.getChild("paho"))

    # region Connection handling
    def connect(self):
        logger.info("Connecting...")
        self._client.connect(host=self._mqtt_host)
        self._client.loop_forever()

    def connect_async(self):
        logger.info("Connecting...")
        self._linkkit_client.thing_setup()
        self._linkkit_client.connect_async()
        # self._client.connect_async(host=self._mqtt_host)
        # self._client.loop_start()
        self._linkkit_client.start_worker_loop()

    def disconnect(self):
        logger.info("Disconnecting...")
        self._linkkit_client.disconnect()
        self._client.disconnect()
        self._client.loop_stop()

    def _thing_on_thing_enable(self, user_data):
        print("on_thing_enable")
        # print('subscribe_topic, topic:%s' % echo_topic)
        # self._linkkit_client.subscribe_topic(echo_topic, 0)
        self._linkkit_client.subscribe_topic(f"/sys/{self._product_key}/{self._device_name}/app/down/account/bind_reply")
        self._linkkit_client.subscribe_topic(f"/sys/{self._product_key}/{self._device_name}/app/down/thing/event/property/post_reply")
        self._linkkit_client.subscribe_topic(f"/sys/{self._product_key}/{self._device_name}/app/down/thing/events")
        self._linkkit_client.subscribe_topic(f"/sys/{self._product_key}/{self._device_name}/app/down/thing/status")
        self._linkkit_client.subscribe_topic(f"/sys/{self._product_key}/{self._device_name}/app/down/thing/properties")
        self._linkkit_client.subscribe_topic(f"/sys/{self._product_key}/{self._device_name}/app/down/thing/model/down_raw")

        self._linkkit_client.publish_topic(f"/sys/{self._product_key}/{self._device_name}/app/up/account/bind",
                                           json.dumps({
                                               "id": "msgid1",
                                               "version": "1.0",
                                               "request": {
                                                   "clientId": self._mqtt_username
                                               },
                                               "params": {
                                                   "iotToken": self._iot_token
                                               }
                                           })
                                           )

        # self._linkkit_client.query_ota_firmware()
        command = MammotionCommand(device_name="Luba")
        self._cloud_client.send_cloud_command(command.get_report_cfg())

    def _thing_on_topic_message(self, topic, payload, qos, user_data):
        print("on_topic_message, receive message, topic:%s, payload:%s, qos:%d" % (topic, payload, qos))

    def _thing_on_connect(self, session_flag, rc, user_data):
        print("on_connect, session_flag:%d, rc:%d" % (session_flag, rc))

        # self._linkkit_client.subscribe_topic(f"/sys/{self._product_key}/{self._device_name}/#")


    def _on_connect(self, _client, _userdata, _flags: dict, rc: int):
        if rc == 0:
            logger.info("Connected")
            self._client.subscribe(f"/sys/{self._product_key}/{self._device_name}/#")
            self._client.subscribe(f"/sys/{self._product_key}/{self._device_name}/app/down/account/bind_reply")

            self._client.publish(f"/sys/{self._product_key}/{self._device_name}/app/up/account/bind",
                                 json.dumps({
                                     "id": "msgid1",
                                     "version": "1.0",
                                     "request": {
                                         "clientId": self._mqtt_username
                                     },
                                     "params": {
                                         "iotToken": self._iot_token
                                     }
                                 })
                                 )

            if self.on_connected:
                self.on_connected()
        else:
            logger.error("Could not connect %s", connack_string(rc))
            if self.on_error:
                self.on_error(connack_string(rc))

    def _on_disconnect(self, _client, _userdata, rc: int):
        logger.info("Disconnected")
        logger.debug(rc)
        if self.on_disconnected:
            self.on_disconnected()

    # endregion

    def _on_message(self, _client, _userdata, message: MQTTMessage):
        logger.info("Message on topic %s", message.topic)
        # with sqlite3.connect("messages.db") as conn:
        #     conn.execute("INSERT INTO messages (topic, timestamp, payload) VALUES (?, ?, ?)",
        #                  (message.topic, int(message.timestamp), message.payload.decode("utf-8")))

        payload = json.loads(message.payload)
        if message.topic.endswith("/app/down/thing/events"):
            event = ThingEventMessage(**payload)
            params = event.params
            if params.identifier == "device_protobuf_msg_event":
                content = cast(luba_msg_pb2, params.value.content)
                if content.WhichOneof("subMsg") == "sys" and content.sys.WhichOneof("subSysMsg") == "systemRapidState":
                    state = RapidState.from_raw(content.sys.systemRapidState.data)
                    self._set_rapid_state(state)
                else:
                    logger.info("Unhandled protobuf event: %s", content.WhichOneof("subMsg"))
            elif params.identifier == "device_warning_event":
                if self.on_warning:
                    self.on_warning(params.value.code)
            else:
                logger.info("Unhandled event: %s", params.identifier)
        elif message.topic.endswith("/app/down/thing/status"):
            status = ThingStatusMessage(**payload)
            self._set_status(status.params.status.value)
        elif message.topic.endswith("/app/down/thing/properties"):
            properties = ThingPropertiesMessage(**payload)
        else:
            logger.info("Unhandled topic: %s", message.topic)
            logger.debug(payload)