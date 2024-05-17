from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor
DRV_RESULT_FAIL: DrvDevInfoResult
DRV_RESULT_NOTSUP: DrvDevInfoResult
DRV_RESULT_SUC: DrvDevInfoResult
DirectConnectWifi: WifiConfType
DisconnectWifi: WifiConfType
ForgetWifi: WifiConfType
ReconnectWifi: WifiConfType

class DevNet(_message.Message):
    __slots__ = ["toapp_ListUpload", "toapp_WifiConf", "toapp_devinfo_resp", "toapp_networkinfo_rsp", "toapp_upgrade_report", "toapp_uploadfile_rsp", "toapp_wifi_iot_status", "toapp_wifimsg", "todev_ConfType", "todev_ble_sync", "todev_devinfo_req", "todev_log_data_cancel", "todev_networkinfo_req", "todev_req_log_info", "todev_uploadfile_req", "todev_wifi_configuration", "todev_wifilistupload", "todev_wifimsgupload"]
    TOAPP_DEVINFO_RESP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_LISTUPLOAD_FIELD_NUMBER: _ClassVar[int]
    TOAPP_NETWORKINFO_RSP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_UPGRADE_REPORT_FIELD_NUMBER: _ClassVar[int]
    TOAPP_UPLOADFILE_RSP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WIFICONF_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WIFIMSG_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WIFI_IOT_STATUS_FIELD_NUMBER: _ClassVar[int]
    TODEV_BLE_SYNC_FIELD_NUMBER: _ClassVar[int]
    TODEV_CONFTYPE_FIELD_NUMBER: _ClassVar[int]
    TODEV_DEVINFO_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_LOG_DATA_CANCEL_FIELD_NUMBER: _ClassVar[int]
    TODEV_NETWORKINFO_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_REQ_LOG_INFO_FIELD_NUMBER: _ClassVar[int]
    TODEV_UPLOADFILE_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_WIFILISTUPLOAD_FIELD_NUMBER: _ClassVar[int]
    TODEV_WIFIMSGUPLOAD_FIELD_NUMBER: _ClassVar[int]
    TODEV_WIFI_CONFIGURATION_FIELD_NUMBER: _ClassVar[int]
    toapp_ListUpload: DrvListUpload
    toapp_WifiConf: DrvWifiConf
    toapp_devinfo_resp: DrvDevInfoResp
    toapp_networkinfo_rsp: GetNetworkInfoRsp
    toapp_upgrade_report: int
    toapp_uploadfile_rsp: int
    toapp_wifi_iot_status: WifiIotStatusReport
    toapp_wifimsg: DrvWifiMsg
    todev_ConfType: int
    todev_ble_sync: int
    todev_devinfo_req: DrvDevInfoReq
    todev_log_data_cancel: DrvUploadFileCancel
    todev_networkinfo_req: GetNetworkInfoReq
    todev_req_log_info: int
    todev_uploadfile_req: int
    todev_wifi_configuration: DrvWifiSet
    todev_wifilistupload: DrvWifiSet
    todev_wifimsgupload: DrvWifiUpload
    def __init__(self, todev_ble_sync: _Optional[int] = ..., todev_ConfType: _Optional[int] = ..., todev_wifimsgupload: _Optional[_Union[DrvWifiUpload, _Mapping]] = ..., todev_wifilistupload: _Optional[_Union[DrvWifiSet, _Mapping]] = ..., todev_wifi_configuration: _Optional[_Union[DrvWifiSet, _Mapping]] = ..., toapp_wifimsg: _Optional[_Union[DrvWifiMsg, _Mapping]] = ..., toapp_WifiConf: _Optional[_Union[DrvWifiConf, _Mapping]] = ..., toapp_ListUpload: _Optional[_Union[DrvListUpload, _Mapping]] = ..., todev_req_log_info: _Optional[int] = ..., todev_log_data_cancel: _Optional[_Union[DrvUploadFileCancel, _Mapping]] = ..., todev_devinfo_req: _Optional[_Union[DrvDevInfoReq, _Mapping]] = ..., toapp_devinfo_resp: _Optional[_Union[DrvDevInfoResp, _Mapping]] = ..., toapp_upgrade_report: _Optional[int] = ..., toapp_wifi_iot_status: _Optional[_Union[WifiIotStatusReport, _Mapping]] = ..., todev_uploadfile_req: _Optional[int] = ..., toapp_uploadfile_rsp: _Optional[int] = ..., todev_networkinfo_req: _Optional[_Union[GetNetworkInfoReq, _Mapping]] = ..., toapp_networkinfo_rsp: _Optional[_Union[GetNetworkInfoRsp, _Mapping]] = ...) -> None: ...

class DrvDevInfoReq(_message.Message):
    __slots__ = ["req_ids"]
    REQ_IDS_FIELD_NUMBER: _ClassVar[int]
    req_ids: _containers.RepeatedCompositeFieldContainer[DrvDevInfoReqId]
    def __init__(self, req_ids: _Optional[_Iterable[_Union[DrvDevInfoReqId, _Mapping]]] = ...) -> None: ...

class DrvDevInfoReqId(_message.Message):
    __slots__ = ["id", "type"]
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    id: int
    type: int
    def __init__(self, id: _Optional[int] = ..., type: _Optional[int] = ...) -> None: ...

class DrvDevInfoResp(_message.Message):
    __slots__ = ["resp_ids"]
    RESP_IDS_FIELD_NUMBER: _ClassVar[int]
    resp_ids: _containers.RepeatedCompositeFieldContainer[DrvDevInfoRespId]
    def __init__(self, resp_ids: _Optional[_Iterable[_Union[DrvDevInfoRespId, _Mapping]]] = ...) -> None: ...

class DrvDevInfoRespId(_message.Message):
    __slots__ = ["id", "info", "res", "type"]
    ID_FIELD_NUMBER: _ClassVar[int]
    INFO_FIELD_NUMBER: _ClassVar[int]
    RES_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    id: int
    info: str
    res: int
    type: int
    def __init__(self, id: _Optional[int] = ..., type: _Optional[int] = ..., res: _Optional[int] = ..., info: _Optional[str] = ...) -> None: ...

class DrvListUpload(_message.Message):
    __slots__ = ["current", "memssid", "rssi", "status", "sum"]
    CURRENT_FIELD_NUMBER: _ClassVar[int]
    MEMSSID_FIELD_NUMBER: _ClassVar[int]
    RSSI_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    SUM_FIELD_NUMBER: _ClassVar[int]
    current: int
    memssid: str
    rssi: int
    status: int
    sum: int
    def __init__(self, current: _Optional[int] = ..., sum: _Optional[int] = ..., rssi: _Optional[int] = ..., status: _Optional[int] = ..., memssid: _Optional[str] = ...) -> None: ...

class DrvUploadFileCancel(_message.Message):
    __slots__ = ["bizId"]
    BIZID_FIELD_NUMBER: _ClassVar[int]
    bizId: int
    def __init__(self, bizId: _Optional[int] = ...) -> None: ...

class DrvUploadFileToAppReq(_message.Message):
    __slots__ = ["bizId", "num", "operation", "serverIp", "serverPort", "type"]
    BIZID_FIELD_NUMBER: _ClassVar[int]
    NUM_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    SERVERIP_FIELD_NUMBER: _ClassVar[int]
    SERVERPORT_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    bizId: int
    num: int
    operation: int
    serverIp: int
    serverPort: int
    type: int
    def __init__(self, bizId: _Optional[int] = ..., operation: _Optional[int] = ..., serverIp: _Optional[int] = ..., serverPort: _Optional[int] = ..., num: _Optional[int] = ..., type: _Optional[int] = ...) -> None: ...

class DrvWifiConf(_message.Message):
    __slots__ = ["code", "confssid", "succFlag"]
    CODE_FIELD_NUMBER: _ClassVar[int]
    CONFSSID_FIELD_NUMBER: _ClassVar[int]
    SUCCFLAG_FIELD_NUMBER: _ClassVar[int]
    code: int
    confssid: str
    succFlag: bool
    def __init__(self, succFlag: bool = ..., code: _Optional[int] = ..., confssid: _Optional[str] = ...) -> None: ...

class DrvWifiList(_message.Message):
    __slots__ = ["nVSWifiUpload"]
    NVSWIFIUPLOAD_FIELD_NUMBER: _ClassVar[int]
    nVSWifiUpload: int
    def __init__(self, nVSWifiUpload: _Optional[int] = ...) -> None: ...

class DrvWifiMsg(_message.Message):
    __slots__ = ["devicename", "iP", "msgssid", "password", "productkey", "rssi", "status1", "status2"]
    DEVICENAME_FIELD_NUMBER: _ClassVar[int]
    IP_FIELD_NUMBER: _ClassVar[int]
    MSGSSID_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    PRODUCTKEY_FIELD_NUMBER: _ClassVar[int]
    RSSI_FIELD_NUMBER: _ClassVar[int]
    STATUS1_FIELD_NUMBER: _ClassVar[int]
    STATUS2_FIELD_NUMBER: _ClassVar[int]
    devicename: str
    iP: str
    msgssid: str
    password: str
    productkey: str
    rssi: int
    status1: str
    status2: str
    def __init__(self, status1: _Optional[str] = ..., status2: _Optional[str] = ..., iP: _Optional[str] = ..., msgssid: _Optional[str] = ..., password: _Optional[str] = ..., rssi: _Optional[int] = ..., productkey: _Optional[str] = ..., devicename: _Optional[str] = ...) -> None: ...

class DrvWifiSet(_message.Message):
    __slots__ = ["confSsid", "configParam"]
    CONFIGPARAM_FIELD_NUMBER: _ClassVar[int]
    CONFSSID_FIELD_NUMBER: _ClassVar[int]
    confSsid: str
    configParam: int
    def __init__(self, configParam: _Optional[int] = ..., confSsid: _Optional[str] = ...) -> None: ...

class DrvWifiUpload(_message.Message):
    __slots__ = ["wifiMsgUpload"]
    WIFIMSGUPLOAD_FIELD_NUMBER: _ClassVar[int]
    wifiMsgUpload: int
    def __init__(self, wifiMsgUpload: _Optional[int] = ...) -> None: ...

class GetNetworkInfoReq(_message.Message):
    __slots__ = ["req_ids"]
    REQ_IDS_FIELD_NUMBER: _ClassVar[int]
    req_ids: int
    def __init__(self, req_ids: _Optional[int] = ...) -> None: ...

class GetNetworkInfoRsp(_message.Message):
    __slots__ = ["gateway", "ip", "mask", "req_ids", "wifi_mac", "wifi_rssi", "wifi_ssid"]
    GATEWAY_FIELD_NUMBER: _ClassVar[int]
    IP_FIELD_NUMBER: _ClassVar[int]
    MASK_FIELD_NUMBER: _ClassVar[int]
    REQ_IDS_FIELD_NUMBER: _ClassVar[int]
    WIFI_MAC_FIELD_NUMBER: _ClassVar[int]
    WIFI_RSSI_FIELD_NUMBER: _ClassVar[int]
    WIFI_SSID_FIELD_NUMBER: _ClassVar[int]
    gateway: int
    ip: int
    mask: int
    req_ids: int
    wifi_mac: str
    wifi_rssi: int
    wifi_ssid: str
    def __init__(self, req_ids: _Optional[int] = ..., wifi_ssid: _Optional[str] = ..., wifi_mac: _Optional[str] = ..., wifi_rssi: _Optional[int] = ..., ip: _Optional[int] = ..., mask: _Optional[int] = ..., gateway: _Optional[int] = ...) -> None: ...

class MnetInetStatus(_message.Message):
    __slots__ = ["connect", "gateway", "ip", "mask"]
    CONNECT_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_FIELD_NUMBER: _ClassVar[int]
    IP_FIELD_NUMBER: _ClassVar[int]
    MASK_FIELD_NUMBER: _ClassVar[int]
    connect: bool
    gateway: int
    ip: int
    mask: int
    def __init__(self, connect: bool = ..., ip: _Optional[int] = ..., mask: _Optional[int] = ..., gateway: _Optional[int] = ...) -> None: ...

class MnetInfo(_message.Message):
    __slots__ = ["imei", "imsi", "inet", "link_type", "model", "revision", "rssi", "sim"]
    IMEI_FIELD_NUMBER: _ClassVar[int]
    IMSI_FIELD_NUMBER: _ClassVar[int]
    INET_FIELD_NUMBER: _ClassVar[int]
    LINK_TYPE_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    RSSI_FIELD_NUMBER: _ClassVar[int]
    SIM_FIELD_NUMBER: _ClassVar[int]
    imei: str
    imsi: str
    inet: MnetInetStatus
    link_type: int
    model: str
    revision: str
    rssi: int
    sim: int
    def __init__(self, model: _Optional[str] = ..., revision: _Optional[str] = ..., imei: _Optional[str] = ..., sim: _Optional[int] = ..., imsi: _Optional[str] = ..., link_type: _Optional[int] = ..., rssi: _Optional[int] = ..., inet: _Optional[_Union[MnetInetStatus, _Mapping]] = ...) -> None: ...

class WifiIotStatusReport(_message.Message):
    __slots__ = ["devicename", "iot_connected", "productkey", "wifi_connected"]
    DEVICENAME_FIELD_NUMBER: _ClassVar[int]
    IOT_CONNECTED_FIELD_NUMBER: _ClassVar[int]
    PRODUCTKEY_FIELD_NUMBER: _ClassVar[int]
    WIFI_CONNECTED_FIELD_NUMBER: _ClassVar[int]
    devicename: str
    iot_connected: bool
    productkey: str
    wifi_connected: bool
    def __init__(self, wifi_connected: bool = ..., iot_connected: bool = ..., productkey: _Optional[str] = ..., devicename: _Optional[str] = ...) -> None: ...

class WifiConfType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class DrvDevInfoResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
