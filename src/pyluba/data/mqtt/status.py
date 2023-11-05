from enum import Enum
from typing import Literal, Any

from pydantic import BaseModel


class GroupIdListItem(BaseModel):
    groupId: str
    groupType: Literal["ISOLATION"]


# are there other values?
class StatusType(Enum):
    CONNECTED = 1
    DISCONNECTED = 3


class Status(BaseModel):
    time: int
    value: StatusType


class Params(BaseModel):
    groupIdList: list[GroupIdListItem]
    netType: Literal["NET_WIFI"]
    activeTime: int
    ip: str
    aliyunCommodityCode: Literal["iothub_senior"]
    categoryKey: Literal["LawnMower"]
    nodeType: Literal["DEVICE"]
    productKey: str
    statusLast: int
    deviceName: str
    iotId: str
    namespace: str
    tenantId: str
    thingType: Literal["DEVICE"]
    tenantInstanceId: str
    categoryId: int
    status: Status


class ThingStatusMessage(BaseModel):
    method: Literal["thing.status"]
    id: str
    params: Params
    version: Literal["1.0"]
