from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BaseStation(_message.Message):
    __slots__ = ["app_to_base_mqtt_rtk_msg", "base_to_app_mqtt_rtk_msg", "to_app", "to_dev"]
    APP_TO_BASE_MQTT_RTK_MSG_FIELD_NUMBER: _ClassVar[int]
    BASE_TO_APP_MQTT_RTK_MSG_FIELD_NUMBER: _ClassVar[int]
    TO_APP_FIELD_NUMBER: _ClassVar[int]
    TO_DEV_FIELD_NUMBER: _ClassVar[int]
    app_to_base_mqtt_rtk_msg: app_to_base_mqtt_rtk_t
    base_to_app_mqtt_rtk_msg: base_to_app_mqtt_rtk_t
    to_app: response_basestation_info_t
    to_dev: request_basestation_info_t
    def __init__(self, to_dev: _Optional[_Union[request_basestation_info_t, _Mapping]] = ..., to_app: _Optional[_Union[response_basestation_info_t, _Mapping]] = ..., app_to_base_mqtt_rtk_msg: _Optional[_Union[app_to_base_mqtt_rtk_t, _Mapping]] = ..., base_to_app_mqtt_rtk_msg: _Optional[_Union[base_to_app_mqtt_rtk_t, _Mapping]] = ...) -> None: ...

class app_to_base_mqtt_rtk_t(_message.Message):
    __slots__ = ["rtk_password", "rtk_port", "rtk_switch", "rtk_url", "rtk_username"]
    RTK_PASSWORD_FIELD_NUMBER: _ClassVar[int]
    RTK_PORT_FIELD_NUMBER: _ClassVar[int]
    RTK_SWITCH_FIELD_NUMBER: _ClassVar[int]
    RTK_URL_FIELD_NUMBER: _ClassVar[int]
    RTK_USERNAME_FIELD_NUMBER: _ClassVar[int]
    rtk_password: str
    rtk_port: int
    rtk_switch: int
    rtk_url: str
    rtk_username: str
    def __init__(self, rtk_switch: _Optional[int] = ..., rtk_url: _Optional[str] = ..., rtk_port: _Optional[int] = ..., rtk_username: _Optional[str] = ..., rtk_password: _Optional[str] = ...) -> None: ...

class base_to_app_mqtt_rtk_t(_message.Message):
    __slots__ = ["rtk_switch_status"]
    RTK_SWITCH_STATUS_FIELD_NUMBER: _ClassVar[int]
    rtk_switch_status: int
    def __init__(self, rtk_switch_status: _Optional[int] = ...) -> None: ...

class request_basestation_info_t(_message.Message):
    __slots__ = ["request_type"]
    REQUEST_TYPE_FIELD_NUMBER: _ClassVar[int]
    request_type: int
    def __init__(self, request_type: _Optional[int] = ...) -> None: ...

class response_basestation_info_t(_message.Message):
    __slots__ = ["app_connect_type", "ble_rssi", "lora_channel", "lora_locid", "lora_netid", "lora_scan", "lowpower_status", "mqtt_rtk_status", "rtk_channel", "rtk_status", "rtk_switch", "sats_num", "system_status", "wifi_rssi"]
    APP_CONNECT_TYPE_FIELD_NUMBER: _ClassVar[int]
    BLE_RSSI_FIELD_NUMBER: _ClassVar[int]
    LORA_CHANNEL_FIELD_NUMBER: _ClassVar[int]
    LORA_LOCID_FIELD_NUMBER: _ClassVar[int]
    LORA_NETID_FIELD_NUMBER: _ClassVar[int]
    LORA_SCAN_FIELD_NUMBER: _ClassVar[int]
    LOWPOWER_STATUS_FIELD_NUMBER: _ClassVar[int]
    MQTT_RTK_STATUS_FIELD_NUMBER: _ClassVar[int]
    RTK_CHANNEL_FIELD_NUMBER: _ClassVar[int]
    RTK_STATUS_FIELD_NUMBER: _ClassVar[int]
    RTK_SWITCH_FIELD_NUMBER: _ClassVar[int]
    SATS_NUM_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_STATUS_FIELD_NUMBER: _ClassVar[int]
    WIFI_RSSI_FIELD_NUMBER: _ClassVar[int]
    app_connect_type: int
    ble_rssi: int
    lora_channel: int
    lora_locid: int
    lora_netid: int
    lora_scan: int
    lowpower_status: int
    mqtt_rtk_status: int
    rtk_channel: int
    rtk_status: int
    rtk_switch: int
    sats_num: int
    system_status: int
    wifi_rssi: int
    def __init__(self, system_status: _Optional[int] = ..., app_connect_type: _Optional[int] = ..., ble_rssi: _Optional[int] = ..., wifi_rssi: _Optional[int] = ..., sats_num: _Optional[int] = ..., lora_scan: _Optional[int] = ..., lora_channel: _Optional[int] = ..., lora_locid: _Optional[int] = ..., lora_netid: _Optional[int] = ..., rtk_status: _Optional[int] = ..., lowpower_status: _Optional[int] = ..., mqtt_rtk_status: _Optional[int] = ..., rtk_channel: _Optional[int] = ..., rtk_switch: _Optional[int] = ...) -> None: ...
