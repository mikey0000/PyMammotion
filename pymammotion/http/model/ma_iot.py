"""Data models for Mammotion's MA-IoT proxy API (`api-iot-business-*.mammotion.com`).

The Mammotion Android app (2.2.4.x) no longer talks to the Aliyun IoT gateway
directly for device listing, property get/set, or service invocation.  It goes
through Mammotion's own HTTPS proxy at a per-region host (e.g.
``api-iot-business-eu-dcdn.mammotion.com``).  That proxy has its own rate
limits (much more lenient than raw Aliyun quotas) and exposes a small set of
REST endpoints for command/control, plus a ``/v1/mqtt/auth/jwt`` endpoint that
issues credentials for a separate MQTT broker used for push notifications.

These dataclasses cover the request/response bodies used by that proxy, mirror
``com.agilexrobotics.maiot_module.bean.*`` in the decompiled app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


@dataclass
class MaRegionRequest(DataClassORJSONMixin):
    """Body of ``POST /v1/ma-user/region`` to resolve the per-region base URL."""

    access_token: Annotated[str, Alias("accessToken")]

    class Config(BaseConfig):
        serialize_by_alias = True


@dataclass
class MaRegionData(DataClassORJSONMixin):
    """Per-region base URL returned by the ma-user/region endpoint."""

    region_endpoint: Annotated[str, Alias("regionEndpoint")] = ""

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class MaIotDeviceListRequest(DataClassORJSONMixin):
    """Body of ``POST /v1/user/device/page`` to paginate the user's devices.

    The app's ``GetDeviceListReq`` only ever sets ``pageNumber`` + ``pageSize``
    (see ``MaIoTApp.getDeviceList`` in the decompiled sources).  ``owned`` and
    ``iotId`` are optional filters we expose for flexibility but intentionally
    omit from the payload when unset so we match the app's wire format.
    """

    page_number: Annotated[int, Alias("pageNumber")] = 1
    page_size: Annotated[int, Alias("pageSize")] = 100
    owned: int | None = None
    iot_id: Annotated[str | None, Alias("iotId")] = None

    class Config(BaseConfig):
        serialize_by_alias = True
        omit_none = True


@dataclass
class MaIotDeviceRecord(DataClassORJSONMixin):
    """Single device record returned by the MA-IoT device list endpoint.

    Note: this intentionally mirrors the app's ``DeviceRecord`` shape which
    differs slightly from the legacy ``DeviceRecords`` entry under ``http``.
    """

    identity_id: Annotated[str, Alias("identityId")] = ""
    iot_id: Annotated[str, Alias("iotId")] = ""
    product_key: Annotated[str, Alias("productKey")] = ""
    device_name: Annotated[str, Alias("deviceName")] = ""
    nick_name: Annotated[str, Alias("nickName")] = ""
    owned: int = 0
    status: int = 0
    bind_time: Annotated[int, Alias("bindTime")] = 0

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class MaIotDeviceList(DataClassORJSONMixin):
    """Paginated container of ``MaIotDeviceRecord`` entries."""

    records: list[MaIotDeviceRecord] = field(default_factory=list)
    total: int = 0
    size: int = 0
    current: int = 0
    pages: int = 0


@dataclass
class MaIotJwtRequest(DataClassORJSONMixin):
    """Body of ``POST /v1/mqtt/auth/jwt`` to issue MQTT credentials."""

    client_id: Annotated[str, Alias("clientId")]
    username: str

    class Config(BaseConfig):
        serialize_by_alias = True


@dataclass
class MaIotJwtResponse(DataClassORJSONMixin):
    """MQTT broker host + JWT credentials returned by ``/v1/mqtt/auth/jwt``."""

    host: str = ""
    jwt: str = ""
    client_id: Annotated[str, Alias("clientId")] = ""
    username: str = ""

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class MaIotGetPropertiesRequest(DataClassORJSONMixin):
    """Body of ``POST /v1/mqtt/rpc/thing/properties/get`` (read device state)."""

    iot_id: Annotated[str, Alias("iotId")]
    product_key: Annotated[str, Alias("productKey")]
    device_name: Annotated[str, Alias("deviceName")]

    class Config(BaseConfig):
        serialize_by_alias = True


@dataclass
class MaIotSetPropertiesRequest(DataClassORJSONMixin):
    """Body of ``POST /v1/mqtt/rpc/thing/properties/set`` (write device state)."""

    iot_id: Annotated[str, Alias("iotId")]
    product_key: Annotated[str, Alias("productKey")]
    device_name: Annotated[str, Alias("deviceName")]
    items: dict[str, Any] = field(default_factory=dict)

    class Config(BaseConfig):
        serialize_by_alias = True


@dataclass
class MaIotServiceInvokeRequest(DataClassORJSONMixin):
    """Body of ``POST /v1/mqtt/rpc/thing/service/invoke`` (run a device action).

    ``args.content`` is an opaque payload string — for Mammotion devices it's
    the base64-encoded protobuf the coordinator currently sends through the
    Aliyun ``send_cloud_command`` code path.
    """

    iot_id: Annotated[str, Alias("iotId")]
    product_key: Annotated[str, Alias("productKey")]
    device_name: Annotated[str, Alias("deviceName")]
    identifier: str
    args: dict[str, Any] = field(default_factory=dict)

    class Config(BaseConfig):
        serialize_by_alias = True


@dataclass
class MaIotServiceInvokeResponse(DataClassORJSONMixin):
    """Response body of ``/v1/mqtt/rpc/thing/service/invoke``."""

    result: str = ""
    message_id: Annotated[str, Alias("messageId")] = ""

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class MaIotProperty(DataClassORJSONMixin):
    """Single property value entry returned by the properties/get endpoint."""

    identifier: str = ""
    value: Any = None
    time: int = 0
