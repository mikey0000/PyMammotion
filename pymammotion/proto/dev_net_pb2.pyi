from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

APN_AUTH_CHAP: apn_auth_type
APN_AUTH_NONE: apn_auth_type
APN_AUTH_PAP: apn_auth_type
APN_AUTH_PAP_CHAP: apn_auth_type
DESCRIPTOR: _descriptor.FileDescriptor
DRV_RESULT_FAIL: DrvDevInfoResult
DRV_RESULT_NOTSUP: DrvDevInfoResult
DRV_RESULT_SUC: DrvDevInfoResult
DirectConnectWifi: WifiConfType
DisconnectWifi: WifiConfType
FILE_TYPE_ALL: DrvUploadFileFileType
FILE_TYPE_NAVLOG: DrvUploadFileFileType
FILE_TYPE_RTKLOG: DrvUploadFileFileType
FILE_TYPE_SYSLOG: DrvUploadFileFileType
ForgetWifi: WifiConfType
IOT_TYPE_OFFLINE: iot_conctrl_type
IOT_TYPE_ONLINE: iot_conctrl_type
IOT_TYPE_RESET: iot_conctrl_type
MNET_LINK_2G: mnet_link_type
MNET_LINK_3G: mnet_link_type
MNET_LINK_4G: mnet_link_type
MNET_LINK_NONE: mnet_link_type
NET_TYPE_MNET: net_type
NET_TYPE_WIFI: net_type
ReconnectWifi: WifiConfType
SIM_INPUT_PIN: sim_card_sta
SIM_INPUT_PUK: sim_card_sta
SIM_INVALID: sim_card_sta
SIM_NONE: sim_card_sta
SIM_NO_CARD: sim_card_sta
SIM_OK: sim_card_sta
set_enable: WifiConfType

class BleTestBytes(_message.Message):
    __slots__ = ["data", "seqs"]
    DATA_FIELD_NUMBER: _ClassVar[int]
    SEQS_FIELD_NUMBER: _ClassVar[int]
    data: _containers.RepeatedScalarFieldContainer[int]
    seqs: int
    def __init__(self, seqs: _Optional[int] = ..., data: _Optional[_Iterable[int]] = ...) -> None: ...

class DevNet(_message.Message):
    __slots__ = ["bir_testdata", "toapp_ListUpload", "toapp_WifiConf", "toapp_WifiMsg", "toapp_devinfo_resp", "toapp_get_mnet_cfg_rsp", "toapp_mnet_info_rsp", "toapp_networkinfo_rsp", "toapp_set_mnet_cfg_rsp", "toapp_upgrade_report", "toapp_uploadfile_rsp", "toapp_wifi_iot_status", "todev_ConfType", "todev_WifiListUpload", "todev_WifiMsgUpload", "todev_Wifi_Configuration", "todev_ble_sync", "todev_devinfo_req", "todev_get_mnet_cfg_req", "todev_log_data_cancel", "todev_mnet_info_req", "todev_networkinfo_req", "todev_req_log_info", "todev_set_ble_mtu", "todev_set_dds2zmq", "todev_set_iot_offline_req", "todev_set_mnet_cfg_req", "todev_uploadfile_req"]
    BIR_TESTDATA_FIELD_NUMBER: _ClassVar[int]
    TOAPP_DEVINFO_RESP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_GET_MNET_CFG_RSP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_LISTUPLOAD_FIELD_NUMBER: _ClassVar[int]
    TOAPP_MNET_INFO_RSP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_NETWORKINFO_RSP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_SET_MNET_CFG_RSP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_UPGRADE_REPORT_FIELD_NUMBER: _ClassVar[int]
    TOAPP_UPLOADFILE_RSP_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WIFICONF_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WIFIMSG_FIELD_NUMBER: _ClassVar[int]
    TOAPP_WIFI_IOT_STATUS_FIELD_NUMBER: _ClassVar[int]
    TODEV_BLE_SYNC_FIELD_NUMBER: _ClassVar[int]
    TODEV_CONFTYPE_FIELD_NUMBER: _ClassVar[int]
    TODEV_DEVINFO_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_GET_MNET_CFG_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_LOG_DATA_CANCEL_FIELD_NUMBER: _ClassVar[int]
    TODEV_MNET_INFO_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_NETWORKINFO_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_REQ_LOG_INFO_FIELD_NUMBER: _ClassVar[int]
    TODEV_SET_BLE_MTU_FIELD_NUMBER: _ClassVar[int]
    TODEV_SET_DDS2ZMQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_SET_IOT_OFFLINE_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_SET_MNET_CFG_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_UPLOADFILE_REQ_FIELD_NUMBER: _ClassVar[int]
    TODEV_WIFILISTUPLOAD_FIELD_NUMBER: _ClassVar[int]
    TODEV_WIFIMSGUPLOAD_FIELD_NUMBER: _ClassVar[int]
    TODEV_WIFI_CONFIGURATION_FIELD_NUMBER: _ClassVar[int]
    bir_testdata: BleTestBytes
    toapp_ListUpload: DrvListUpload
    toapp_WifiConf: DrvWifiConf
    toapp_WifiMsg: DrvWifiMsg
    toapp_devinfo_resp: DrvDevInfoResp
    toapp_get_mnet_cfg_rsp: GetMnetCfgRsp
    toapp_mnet_info_rsp: GetMnetInfoRsp
    toapp_networkinfo_rsp: GetNetworkInfoRsp
    toapp_set_mnet_cfg_rsp: SetMnetCfgRsp
    toapp_upgrade_report: DrvUpgradeReport
    toapp_uploadfile_rsp: DrvUploadFileToAppRsp
    toapp_wifi_iot_status: WifiIotStatusReport
    todev_ConfType: WifiConfType
    todev_WifiListUpload: DrvWifiList
    todev_WifiMsgUpload: DrvWifiUpload
    todev_Wifi_Configuration: DrvWifiSet
    todev_ble_sync: int
    todev_devinfo_req: DrvDevInfoReq
    todev_get_mnet_cfg_req: GetMnetCfgReq
    todev_log_data_cancel: DrvUploadFileCancel
    todev_mnet_info_req: GetMnetInfoReq
    todev_networkinfo_req: GetNetworkInfoReq
    todev_req_log_info: DrvUploadFileReq
    todev_set_ble_mtu: SetDrvBleMTU
    todev_set_dds2zmq: DrvDebugDdsZmq
    todev_set_iot_offline_req: iot_conctrl_type
    todev_set_mnet_cfg_req: SetMnetCfgReq
    todev_uploadfile_req: DrvUploadFileToAppReq
    def __init__(self, todev_ble_sync: _Optional[int] = ..., todev_ConfType: _Optional[_Union[WifiConfType, str]] = ..., todev_WifiMsgUpload: _Optional[_Union[DrvWifiUpload, _Mapping]] = ..., todev_WifiListUpload: _Optional[_Union[DrvWifiList, _Mapping]] = ..., todev_Wifi_Configuration: _Optional[_Union[DrvWifiSet, _Mapping]] = ..., toapp_WifiMsg: _Optional[_Union[DrvWifiMsg, _Mapping]] = ..., toapp_WifiConf: _Optional[_Union[DrvWifiConf, _Mapping]] = ..., toapp_ListUpload: _Optional[_Union[DrvListUpload, _Mapping]] = ..., todev_req_log_info: _Optional[_Union[DrvUploadFileReq, _Mapping]] = ..., todev_log_data_cancel: _Optional[_Union[DrvUploadFileCancel, _Mapping]] = ..., todev_devinfo_req: _Optional[_Union[DrvDevInfoReq, _Mapping]] = ..., toapp_devinfo_resp: _Optional[_Union[DrvDevInfoResp, _Mapping]] = ..., toapp_upgrade_report: _Optional[_Union[DrvUpgradeReport, _Mapping]] = ..., toapp_wifi_iot_status: _Optional[_Union[WifiIotStatusReport, _Mapping]] = ..., todev_uploadfile_req: _Optional[_Union[DrvUploadFileToAppReq, _Mapping]] = ..., toapp_uploadfile_rsp: _Optional[_Union[DrvUploadFileToAppRsp, _Mapping]] = ..., todev_networkinfo_req: _Optional[_Union[GetNetworkInfoReq, _Mapping]] = ..., toapp_networkinfo_rsp: _Optional[_Union[GetNetworkInfoRsp, _Mapping]] = ..., bir_testdata: _Optional[_Union[BleTestBytes, _Mapping]] = ..., todev_mnet_info_req: _Optional[_Union[GetMnetInfoReq, _Mapping]] = ..., toapp_mnet_info_rsp: _Optional[_Union[GetMnetInfoRsp, _Mapping]] = ..., todev_get_mnet_cfg_req: _Optional[_Union[GetMnetCfgReq, _Mapping]] = ..., toapp_get_mnet_cfg_rsp: _Optional[_Union[GetMnetCfgRsp, _Mapping]] = ..., todev_set_mnet_cfg_req: _Optional[_Union[SetMnetCfgReq, _Mapping]] = ..., toapp_set_mnet_cfg_rsp: _Optional[_Union[SetMnetCfgRsp, _Mapping]] = ..., todev_set_dds2zmq: _Optional[_Union[DrvDebugDdsZmq, _Mapping]] = ..., todev_set_ble_mtu: _Optional[_Union[SetDrvBleMTU, _Mapping]] = ..., todev_set_iot_offline_req: _Optional[_Union[iot_conctrl_type, str]] = ...) -> None: ...

class DrvDebugDdsZmq(_message.Message):
    __slots__ = ["is_enable", "rx_topic_name", "tx_zmq_url"]
    IS_ENABLE_FIELD_NUMBER: _ClassVar[int]
    RX_TOPIC_NAME_FIELD_NUMBER: _ClassVar[int]
    TX_ZMQ_URL_FIELD_NUMBER: _ClassVar[int]
    is_enable: bool
    rx_topic_name: str
    tx_zmq_url: str
    def __init__(self, is_enable: bool = ..., rx_topic_name: _Optional[str] = ..., tx_zmq_url: _Optional[str] = ...) -> None: ...

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
    res: DrvDevInfoResult
    type: int
    def __init__(self, id: _Optional[int] = ..., type: _Optional[int] = ..., res: _Optional[_Union[DrvDevInfoResult, str]] = ..., info: _Optional[str] = ...) -> None: ...

class DrvListUpload(_message.Message):
    __slots__ = ["Memssid", "current", "rssi", "status", "sum"]
    CURRENT_FIELD_NUMBER: _ClassVar[int]
    MEMSSID_FIELD_NUMBER: _ClassVar[int]
    Memssid: str
    RSSI_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    SUM_FIELD_NUMBER: _ClassVar[int]
    current: int
    rssi: int
    status: int
    sum: int
    def __init__(self, sum: _Optional[int] = ..., current: _Optional[int] = ..., status: _Optional[int] = ..., Memssid: _Optional[str] = ..., rssi: _Optional[int] = ...) -> None: ...

class DrvUpgradeReport(_message.Message):
    __slots__ = ["devname", "message", "otaid", "progress", "properties", "result", "version"]
    DEVNAME_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    OTAID_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    PROPERTIES_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    devname: str
    message: str
    otaid: str
    progress: int
    properties: str
    result: int
    version: str
    def __init__(self, devname: _Optional[str] = ..., otaid: _Optional[str] = ..., version: _Optional[str] = ..., progress: _Optional[int] = ..., result: _Optional[int] = ..., message: _Optional[str] = ..., properties: _Optional[str] = ...) -> None: ...

class DrvUploadFileCancel(_message.Message):
    __slots__ = ["bizId"]
    BIZID_FIELD_NUMBER: _ClassVar[int]
    bizId: str
    def __init__(self, bizId: _Optional[str] = ...) -> None: ...

class DrvUploadFileReq(_message.Message):
    __slots__ = ["bizId", "num", "type", "url", "userId"]
    BIZID_FIELD_NUMBER: _ClassVar[int]
    NUM_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    USERID_FIELD_NUMBER: _ClassVar[int]
    bizId: str
    num: int
    type: int
    url: str
    userId: str
    def __init__(self, bizId: _Optional[str] = ..., url: _Optional[str] = ..., userId: _Optional[str] = ..., num: _Optional[int] = ..., type: _Optional[int] = ...) -> None: ...

class DrvUploadFileToAppReq(_message.Message):
    __slots__ = ["bizId", "num", "operation", "serverIp", "serverPort", "type"]
    BIZID_FIELD_NUMBER: _ClassVar[int]
    NUM_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    SERVERIP_FIELD_NUMBER: _ClassVar[int]
    SERVERPORT_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    bizId: str
    num: int
    operation: int
    serverIp: int
    serverPort: int
    type: int
    def __init__(self, bizId: _Optional[str] = ..., operation: _Optional[int] = ..., serverIp: _Optional[int] = ..., serverPort: _Optional[int] = ..., num: _Optional[int] = ..., type: _Optional[int] = ...) -> None: ...

class DrvUploadFileToAppRsp(_message.Message):
    __slots__ = ["bizId", "operation", "result"]
    BIZID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    bizId: str
    operation: int
    result: int
    def __init__(self, bizId: _Optional[str] = ..., operation: _Optional[int] = ..., result: _Optional[int] = ...) -> None: ...

class DrvWifiConf(_message.Message):
    __slots__ = ["Confssid", "code", "succFlag"]
    CODE_FIELD_NUMBER: _ClassVar[int]
    CONFSSID_FIELD_NUMBER: _ClassVar[int]
    Confssid: str
    SUCCFLAG_FIELD_NUMBER: _ClassVar[int]
    code: int
    succFlag: bool
    def __init__(self, succFlag: bool = ..., code: _Optional[int] = ..., Confssid: _Optional[str] = ...) -> None: ...

class DrvWifiList(_message.Message):
    __slots__ = ["nvs_wifi_upload"]
    NVS_WIFI_UPLOAD_FIELD_NUMBER: _ClassVar[int]
    nvs_wifi_upload: int
    def __init__(self, nvs_wifi_upload: _Optional[int] = ...) -> None: ...

class DrvWifiMsg(_message.Message):
    __slots__ = ["devicename", "ip", "msgssid", "password", "productkey", "rssi", "status1", "status2", "wifi_enable"]
    DEVICENAME_FIELD_NUMBER: _ClassVar[int]
    IP_FIELD_NUMBER: _ClassVar[int]
    MSGSSID_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    PRODUCTKEY_FIELD_NUMBER: _ClassVar[int]
    RSSI_FIELD_NUMBER: _ClassVar[int]
    STATUS1_FIELD_NUMBER: _ClassVar[int]
    STATUS2_FIELD_NUMBER: _ClassVar[int]
    WIFI_ENABLE_FIELD_NUMBER: _ClassVar[int]
    devicename: str
    ip: str
    msgssid: str
    password: str
    productkey: str
    rssi: int
    status1: bool
    status2: bool
    wifi_enable: bool
    def __init__(self, status1: bool = ..., status2: bool = ..., ip: _Optional[str] = ..., msgssid: _Optional[str] = ..., password: _Optional[str] = ..., rssi: _Optional[int] = ..., productkey: _Optional[str] = ..., devicename: _Optional[str] = ..., wifi_enable: bool = ...) -> None: ...

class DrvWifiSet(_message.Message):
    __slots__ = ["Confssid", "configParam", "wifi_enable"]
    CONFIGPARAM_FIELD_NUMBER: _ClassVar[int]
    CONFSSID_FIELD_NUMBER: _ClassVar[int]
    Confssid: str
    WIFI_ENABLE_FIELD_NUMBER: _ClassVar[int]
    configParam: int
    wifi_enable: bool
    def __init__(self, configParam: _Optional[int] = ..., Confssid: _Optional[str] = ..., wifi_enable: bool = ...) -> None: ...

class DrvWifiUpload(_message.Message):
    __slots__ = ["wifi_msg_upload"]
    WIFI_MSG_UPLOAD_FIELD_NUMBER: _ClassVar[int]
    wifi_msg_upload: int
    def __init__(self, wifi_msg_upload: _Optional[int] = ...) -> None: ...

class GetMnetCfgReq(_message.Message):
    __slots__ = ["req_ids"]
    REQ_IDS_FIELD_NUMBER: _ClassVar[int]
    req_ids: int
    def __init__(self, req_ids: _Optional[int] = ...) -> None: ...

class GetMnetCfgRsp(_message.Message):
    __slots__ = ["cfg", "req_ids", "result"]
    CFG_FIELD_NUMBER: _ClassVar[int]
    REQ_IDS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    cfg: MnetCfg
    req_ids: int
    result: int
    def __init__(self, req_ids: _Optional[int] = ..., result: _Optional[int] = ..., cfg: _Optional[_Union[MnetCfg, _Mapping]] = ...) -> None: ...

class GetMnetInfoReq(_message.Message):
    __slots__ = ["req_ids"]
    REQ_IDS_FIELD_NUMBER: _ClassVar[int]
    req_ids: int
    def __init__(self, req_ids: _Optional[int] = ...) -> None: ...

class GetMnetInfoRsp(_message.Message):
    __slots__ = ["mnet", "req_ids", "result"]
    MNET_FIELD_NUMBER: _ClassVar[int]
    REQ_IDS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    mnet: MnetInfo
    req_ids: int
    result: int
    def __init__(self, req_ids: _Optional[int] = ..., result: _Optional[int] = ..., mnet: _Optional[_Union[MnetInfo, _Mapping]] = ...) -> None: ...

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

class MnetApn(_message.Message):
    __slots__ = ["apn_alias", "apn_name", "auth", "cid", "password", "username"]
    APN_ALIAS_FIELD_NUMBER: _ClassVar[int]
    APN_NAME_FIELD_NUMBER: _ClassVar[int]
    AUTH_FIELD_NUMBER: _ClassVar[int]
    CID_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    apn_alias: str
    apn_name: str
    auth: apn_auth_type
    cid: int
    password: str
    username: str
    def __init__(self, cid: _Optional[int] = ..., apn_alias: _Optional[str] = ..., apn_name: _Optional[str] = ..., auth: _Optional[_Union[apn_auth_type, str]] = ..., username: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class MnetApnCfg(_message.Message):
    __slots__ = ["apn", "apn_used_idx"]
    APN_FIELD_NUMBER: _ClassVar[int]
    APN_USED_IDX_FIELD_NUMBER: _ClassVar[int]
    apn: _containers.RepeatedCompositeFieldContainer[MnetApn]
    apn_used_idx: int
    def __init__(self, apn_used_idx: _Optional[int] = ..., apn: _Optional[_Iterable[_Union[MnetApn, _Mapping]]] = ...) -> None: ...

class MnetApnSetCfg(_message.Message):
    __slots__ = ["cfg", "use_default"]
    CFG_FIELD_NUMBER: _ClassVar[int]
    USE_DEFAULT_FIELD_NUMBER: _ClassVar[int]
    cfg: MnetApnCfg
    use_default: bool
    def __init__(self, use_default: bool = ..., cfg: _Optional[_Union[MnetApnCfg, _Mapping]] = ...) -> None: ...

class MnetCfg(_message.Message):
    __slots__ = ["apn", "auto_select", "inet_enable", "mnet_enable", "type"]
    APN_FIELD_NUMBER: _ClassVar[int]
    AUTO_SELECT_FIELD_NUMBER: _ClassVar[int]
    INET_ENABLE_FIELD_NUMBER: _ClassVar[int]
    MNET_ENABLE_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    apn: MnetApnSetCfg
    auto_select: bool
    inet_enable: bool
    mnet_enable: bool
    type: net_type
    def __init__(self, mnet_enable: bool = ..., inet_enable: bool = ..., type: _Optional[_Union[net_type, str]] = ..., apn: _Optional[_Union[MnetApnSetCfg, _Mapping]] = ..., auto_select: bool = ...) -> None: ...

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
    inet: mnet_inet_status
    link_type: mnet_link_type
    model: str
    revision: str
    rssi: int
    sim: sim_card_sta
    def __init__(self, model: _Optional[str] = ..., revision: _Optional[str] = ..., imei: _Optional[str] = ..., sim: _Optional[_Union[sim_card_sta, str]] = ..., imsi: _Optional[str] = ..., link_type: _Optional[_Union[mnet_link_type, str]] = ..., rssi: _Optional[int] = ..., inet: _Optional[_Union[mnet_inet_status, _Mapping]] = ...) -> None: ...

class SetDrvBleMTU(_message.Message):
    __slots__ = ["mtu_count"]
    MTU_COUNT_FIELD_NUMBER: _ClassVar[int]
    mtu_count: int
    def __init__(self, mtu_count: _Optional[int] = ...) -> None: ...

class SetMnetCfgReq(_message.Message):
    __slots__ = ["cfg", "req_ids"]
    CFG_FIELD_NUMBER: _ClassVar[int]
    REQ_IDS_FIELD_NUMBER: _ClassVar[int]
    cfg: MnetCfg
    req_ids: int
    def __init__(self, req_ids: _Optional[int] = ..., cfg: _Optional[_Union[MnetCfg, _Mapping]] = ...) -> None: ...

class SetMnetCfgRsp(_message.Message):
    __slots__ = ["req_ids", "result"]
    REQ_IDS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    req_ids: int
    result: int
    def __init__(self, req_ids: _Optional[int] = ..., result: _Optional[int] = ...) -> None: ...

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

class mnet_inet_status(_message.Message):
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

class WifiConfType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class DrvUploadFileFileType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class DrvDevInfoResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class sim_card_sta(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class mnet_link_type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class apn_auth_type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class net_type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class iot_conctrl_type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
