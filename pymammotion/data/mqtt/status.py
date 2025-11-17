from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Literal

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


@dataclass
class GroupIdListItem(DataClassORJSONMixin):
    groupId: str
    groupType: Literal["ISOLATION", "ILOP_APP"]


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
    group_id_list: Annotated[list[GroupIdListItem], Alias("groupIdList")]
    net_type: Annotated[Literal["NET_WIFI", "NET_MNET"], Alias("netType")]
    active_time: Annotated[int, Alias("activeTime")]
    ip: str
    aliyun_commodity_code: Annotated[Literal["iothub_senior"], Alias("aliyunCommodityCode")]
    category_key: Annotated[Literal["LawnMower", "Tracker"], Alias("categoryKey")]
    node_type: Annotated[Literal["DEVICE"], Alias("nodeType")]
    product_key: Annotated[str, Alias("productKey")]
    status_last: Annotated[int, Alias("statusLast")]
    device_name: Annotated[str, Alias("deviceName")]
    iot_id: Annotated[str, Alias("iotId")]
    namespace: str
    tenant_id: Annotated[str, Alias("tenantId")]
    thing_type: Annotated[Literal["DEVICE"], Alias("thingType")]
    tenant_instance_id: Annotated[str, Alias("tenantInstanceId")]
    category_id: Annotated[int, Alias("categoryId")]
    status: Annotated[Status, Alias("status")]

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class ThingStatusMessage(DataClassORJSONMixin):
    method: Literal["thing.status"]
    id: str
    params: Params
    version: Literal["1.0"]
