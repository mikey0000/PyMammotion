from dataclasses import dataclass
from typing import Optional

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
    nickName: Optional[str] = None
    description: Optional[str] = None
    productImage: Optional[str] = None
    categoryImage: Optional[str] = None
    productModel: Optional[str] = None

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
    data: Optional[Data]
    id: Optional[str] = None
