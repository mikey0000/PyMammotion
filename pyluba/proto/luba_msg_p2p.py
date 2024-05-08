# This is an automatically generated file, please do not change
# gen by protobuf_to_pydantic[v0.2.6.2](https://github.com/so1n/protobuf_to_pydantic)
# Protobuf Version: 5.26.1 
# Pydantic Version: 2.6.2 
from .dev_net_p2p import DevNet
from .mctrl_driver_p2p import MctrlDriver
from .mctrl_nav_p2p import MctlNav
from .mctrl_sys_p2p import MctlSys
from enum import IntEnum
from google.protobuf.message import Message  # type: ignore
from protobuf_to_pydantic.customer_validator import check_one_of
from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

class MsgCmdType(IntEnum):
    MSG_CMD_TYPE_START = 0
    MSG_CMD_TYPE_NAV = 240
    MSG_CMD_TYPE_LOCALIZATION = 241
    MSG_CMD_TYPE_PLANNING = 242
    MSG_CMD_TYPE_EMBED_DRIVER = 243
    MSG_CMD_TYPE_EMBED_SYS = 244
    MSG_CMD_TYPE_EMBED_MIDWARE = 245
    MSG_CMD_TYPE_EMBED_OTA = 246
    MSG_CMD_TYPE_APPLICATION = 247
    MSG_CMD_TYPE_ESP = 248


class MsgAttr(IntEnum):
    MSG_ATTR_NONE = 0
    MSG_ATTR_REPORT = 3
    MSG_ATTR_REQ = 1
    MSG_ATTR_RESP = 2


class MsgDevice(IntEnum):
    DEV_COMM_ESP = 0
    DEV_BASESTATION = 4
    DEV_BMS = 9
    DEV_IOTSERVER = 8
    DEV_LEFTMOTOR = 2
    DEV_MAINCTL = 1
    DEV_MOBILEAPP = 7
    DEV_RIGHTMOTOR = 3
    DEV_RTKCLI = 5
    DEV_USBHOST = 6

class MsgNull(BaseModel):    pass

class LubaMsg(BaseModel):
    _one_of_dict = {"LubaMsg.LubaSubMsg": {"fields": {"driver", "nav", "net", "null", "sys"}}}
    one_of_validator = model_validator(mode="before")(check_one_of)
    msgtype: MsgCmdType = Field(default=0) 
    sender: MsgDevice = Field(default=0) 
    rcver: MsgDevice = Field(default=0) 
    msgattr: MsgAttr = Field(default=0) 
    seqs: int = Field(default=0) 
    version: int = Field(default=0) 
    subtype: int = Field(default=0) 
    timestamp: int = Field(default=0) 
    net: DevNet = Field() 
    sys: MctlSys = Field() 
    nav: MctlNav = Field() 
    driver: MctrlDriver = Field() 
    null: MsgNull = Field() 
