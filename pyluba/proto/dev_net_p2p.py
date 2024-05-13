# This is an automatically generated file, please do not change
# gen by protobuf_to_pydantic[v0.2.6.2](https://github.com/so1n/protobuf_to_pydantic)
# Protobuf Version: 5.26.1 
# Pydantic Version: 2.6.2 
from enum import IntEnum
from google.protobuf.message import Message  # type: ignore
from protobuf_to_pydantic.customer_validator import check_one_of
from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator
import typing

class WifiConfType(IntEnum):
    DisconnectWifi = 0
    ForgetWifi = 1
    DirectConnectWifi = 2
    ReconnectWifi = 3


class DrvDevInfoResult(IntEnum):
    DRV_RESULT_FAIL = 0
    DRV_RESULT_SUC = 1
    DRV_RESULT_NOTSUP = 2

class DrvWifiUpload(BaseModel):
    wifiMsgUpload: int = Field(default=0) 

class DrvWifiSet(BaseModel):
    configParam: int = Field(default=0) 
    confSsid: str = Field(default="") 

class DrvWifiMsg(BaseModel):
    status1: str = Field(default="") 
    status2: str = Field(default="") 
    iP: str = Field(default="") 
    msgssid: str = Field(default="") 
    password: str = Field(default="") 
    rssi: int = Field(default=0) 
    productkey: str = Field(default="") 
    devicename: str = Field(default="") 

class DrvWifiConf(BaseModel):
    succFlag: bool = Field(default=False) 
    code: int = Field(default=0) 
    confssid: str = Field(default="") 

class DrvListUpload(BaseModel):
    current: int = Field(default=0) 
    sum: int = Field(default=0) 
    rssi: int = Field(default=0) 
    status: int = Field(default=0) 
    memssid: str = Field(default="") 

class DrvUploadFileCancel(BaseModel):
    bizId: int = Field(default=0) 

class DrvDevInfoReqId(BaseModel):
    id: int = Field(default=0) 
    type: int = Field(default=0) 

class DrvDevInfoReq(BaseModel):
    req_ids: typing.List[DrvDevInfoReqId] = Field(default_factory=list) 

class DrvDevInfoRespId(BaseModel):
    id: int = Field(default=0) 
    type: int = Field(default=0) 
    res: int = Field(default=0) 
    info: str = Field(default="") 

class DrvDevInfoResp(BaseModel):
    resp_ids: typing.List[DrvDevInfoRespId] = Field(default_factory=list) 

class WifiIotStatusReport(BaseModel):
    wifi_connected: bool = Field(default=False) 
    iot_connected: bool = Field(default=False) 
    productkey: str = Field(default="") 
    devicename: str = Field(default="") 

class GetNetworkInfoReq(BaseModel):
    req_ids: int = Field(default=0) 

class GetNetworkInfoRsp(BaseModel):
    req_ids: int = Field(default=0) 
    wifi_ssid: str = Field(default="") 
    wifi_mac: str = Field(default="") 
    wifi_rssi: int = Field(default=0) 
    ip: int = Field(default=0) 
    mask: int = Field(default=0) 
    gateway: int = Field(default=0) 

class DevNet(BaseModel):
    _one_of_dict = {"DevNet.NetSubType": {"fields": {"toapp_ListUpload", "toapp_WifiConf", "toapp_devinfo_resp", "toapp_networkinfo_rsp", "toapp_upgrade_report", "toapp_uploadfile_rsp", "toapp_wifi_iot_status", "toapp_wifimsg", "todev_ConfType", "todev_ble_sync", "todev_devinfo_req", "todev_log_data_cancel", "todev_networkinfo_req", "todev_req_log_info", "todev_uploadfile_req", "todev_wifi_configuration", "todev_wifilistupload", "todev_wifimsgupload"}}}
    one_of_validator = model_validator(mode="before")(check_one_of)
    todev_ble_sync: int = Field(default=0) 
    todev_ConfType: int = Field(default=0) 
    todev_wifimsgupload: DrvWifiUpload = Field() 
    todev_wifilistupload: DrvWifiSet = Field() 
    todev_wifi_configuration: DrvWifiSet = Field() 
    toapp_wifimsg: DrvWifiMsg = Field() 
    toapp_WifiConf: DrvWifiConf = Field() 
    toapp_ListUpload: DrvListUpload = Field() 
    todev_req_log_info: int = Field(default=0) 
    todev_log_data_cancel: DrvUploadFileCancel = Field() 
    todev_devinfo_req: DrvDevInfoReq = Field() 
    toapp_devinfo_resp: DrvDevInfoResp = Field() 
    toapp_upgrade_report: int = Field(default=0) 
    toapp_wifi_iot_status: WifiIotStatusReport = Field() 
    todev_uploadfile_req: int = Field(default=0) 
    toapp_uploadfile_rsp: int = Field(default=0) 
    todev_networkinfo_req: GetNetworkInfoReq = Field() 
    toapp_networkinfo_rsp: GetNetworkInfoRsp = Field() 

class DrvWifiList(BaseModel):
    nVSWifiUpload: int = Field(default=0) 

class DrvUploadFileToAppReq(BaseModel):
    bizId: typing.Optional[int] = Field(default=0) 
    operation: typing.Optional[int] = Field(default=0) 
    serverIp: typing.Optional[int] = Field(default=0) 
    serverPort: typing.Optional[int] = Field(default=0) 
    num: typing.Optional[int] = Field(default=0) 
    type: typing.Optional[int] = Field(default=0) 

class MnetInetStatus(BaseModel):
    connect: bool = Field(default=False) 
    ip: int = Field(default=0) 
    mask: int = Field(default=0) 
    gateway: int = Field(default=0) 

class MnetInfo(BaseModel):
    model: str = Field(default="") 
    revision: str = Field(default="") 
    imei: str = Field(default="") 
    sim: int = Field(default=0) 
    imsi: str = Field(default="") 
    link_type: int = Field(default=0) 
    rssi: int = Field(default=0) 
    inet: MnetInetStatus = Field() 
