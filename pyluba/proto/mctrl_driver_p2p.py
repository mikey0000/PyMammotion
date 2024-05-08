# This is an automatically generated file, please do not change
# gen by protobuf_to_pydantic[v0.2.6.2](https://github.com/so1n/protobuf_to_pydantic)
# Protobuf Version: 5.26.1 
# Pydantic Version: 2.6.2 
from google.protobuf.message import Message  # type: ignore
from protobuf_to_pydantic.customer_validator import check_one_of
from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator


class DrvMotionCtrl(BaseModel):
    setAngularSpeed: int = Field(default=0) 
    setLinearSpeed: int = Field(default=0) 

class DrvKnifeHeight(BaseModel):
    knifeHeight: int = Field(default=0) 

class DrvSrSpeed(BaseModel):
    rw: int = Field(default=0) 
    speed: float = Field(default=0.0) 

class DrvKnifeStatus(BaseModel):
    knife_status: int = Field(default=0) 

class MctrlDriver(BaseModel):
    _one_of_dict = {"MctrlDriver.SubDrvMsg": {"fields": {"bidire_knife_height_report", "bidire_speed_read_set", "toapp_knife_status", "todev_devmotion_ctrl", "todev_knife_height_set"}}}
    one_of_validator = model_validator(mode="before")(check_one_of)
    todev_devmotion_ctrl: DrvMotionCtrl = Field() 
    todev_knife_height_set: DrvKnifeHeight = Field() 
    bidire_speed_read_set: DrvSrSpeed = Field() 
    bidire_knife_height_report: DrvKnifeHeight = Field() 
    toapp_knife_status: DrvKnifeStatus = Field() 
