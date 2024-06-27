from dataclasses import dataclass
from enum import Enum
from typing import Literal

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class GroupIdListItem(DataClassORJSONMixin):
    groupId: str
    groupType: Literal["ISOLATION"]


# are there other values?
class StatusType(Enum):
    CONNECTED = 1
    DISCONNECTED = 3


@dataclass
class Status(DataClassORJSONMixin):
    time: int
    value: StatusType


@dataclass
class Params(DataClassORJSONMixin):
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


@dataclass
class ThingStatusMessage(DataClassORJSONMixin):
    method: Literal["thing.status"]
    id: str
    params: Params
    version: Literal["1.0"]
