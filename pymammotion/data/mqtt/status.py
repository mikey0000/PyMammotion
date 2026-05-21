from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Literal

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


@dataclass
class GroupIdListItem(DataClassORJSONMixin):
    """A single group membership entry in the device status message."""

    groupId: str
    groupType: Literal["ISOLATION", "ILOP_APP"]


class StatusType(Enum):
    """Online/offline connection state values used in ``thing.status`` messages."""

    CONNECTED = 1
    DISCONNECTED = 3


@dataclass
class Status(DataClassORJSONMixin):
    """Timestamped connection status value from a ``thing.status`` message."""

    time: int
    value: StatusType


@dataclass
class Params(DataClassORJSONMixin):
    """Envelope parameters for an Aliyun IoT ``thing.status`` MQTT message.

    The fields ``iot_id`` and ``status`` are always required.  All Aliyun-specific
    fields default to ``None`` so that a synthetic ``Params`` can be constructed
    from the simpler Mammotion MQTT status format without carrying Aliyun metadata.
    """

    iot_id: Annotated[str, Alias("iotId")]
    status: Annotated[Status, Alias("status")]
    group_id_list: Annotated[list[GroupIdListItem], Alias("groupIdList")] = field(default_factory=list)
    net_type: Annotated[str | None, Alias("netType")] = None
    active_time: Annotated[int | None, Alias("activeTime")] = None
    ip: str | None = None
    aliyun_commodity_code: Annotated[str | None, Alias("aliyunCommodityCode")] = None
    category_key: Annotated[str | None, Alias("categoryKey")] = None
    node_type: Annotated[str | None, Alias("nodeType")] = None
    product_key: Annotated[str | None, Alias("productKey")] = None
    status_last: Annotated[int | None, Alias("statusLast")] = None
    device_name: Annotated[str | None, Alias("deviceName")] = None
    namespace: str | None = None
    tenant_id: Annotated[str | None, Alias("tenantId")] = None
    thing_type: Annotated[str | None, Alias("thingType")] = None
    tenant_instance_id: Annotated[str | None, Alias("tenantInstanceId")] = None
    category_id: Annotated[int | None, Alias("categoryId")] = None

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class ThingStatusMessage(DataClassORJSONMixin):
    """Top-level ``thing.status`` MQTT message reporting device online/offline state.

    ``method``, ``id``, and ``version`` are present in Aliyun-format messages but
    omitted by the Mammotion MQTT broker (post-2025 devices), so they default to
    ``None`` / empty string.
    """

    params: Params
    id: str = ""
    version: str = ""
    method: Literal["thing.status"] | None = None


@dataclass
class MammotionStatusMessage(DataClassORJSONMixin):
    """Mammotion MQTT (post-2025) device status message.

    Sent on ``/sys/{productKey}/{deviceName}/app/down/thing/status`` with a flat
    structure — no nested ``params`` or Aliyun metadata::

        {
            "action": "online",
            "productKey": "8xMGQS6DESC",
            "deviceName": "Yuka-MNTXVHBE",
            "iotId": "UTpbwGC7vxd4DpNvbFGL000000",
            "gmtCreate": 1779395099943
        }
    """

    action: str  # "online" | "offline"
    product_key: Annotated[str, Alias("productKey")]
    device_name: Annotated[str, Alias("deviceName")]
    iot_id: Annotated[str, Alias("iotId")]
    gmt_create: Annotated[int, Alias("gmtCreate")]

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True

    def to_thing_status(self) -> ThingStatusMessage:
        """Synthesise a :class:`ThingStatusMessage` for unified downstream handling."""
        status_value = StatusType.CONNECTED if self.action == "online" else StatusType.DISCONNECTED
        return ThingStatusMessage(
            params=Params(
                iot_id=self.iot_id,
                status=Status(time=self.gmt_create, value=status_value),
                product_key=self.product_key,
                device_name=self.device_name,
            ),
        )
