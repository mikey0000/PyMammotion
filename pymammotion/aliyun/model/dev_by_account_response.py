from dataclasses import dataclass

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class Device(DataClassORJSONMixin):
    gmtModified: int
    netType: str
    categoryKey: str
    productKey: str
    nodeType: str
    isEdgeGateway: bool
    deviceName: str
    categoryName: str
    identityAlias: str
    productName: str
    iotId: str
    bindTime: int
    owned: int
    identityId: str
    thingType: str
    status: int
    nickName: str | None = None
    description: str | None = None
    productImage: str | None = None
    categoryImage: str | None = None
    productModel: str | None = None

    class Config(BaseConfig):
        omit_default = True


@dataclass
class Data(DataClassORJSONMixin):
    total: int
    data: list[Device]
    pageNo: int
    pageSize: int


@dataclass
class ListingDevByAccountResponse(DataClassORJSONMixin):
    code: int
    data: Data | None
    id: str | None = None
