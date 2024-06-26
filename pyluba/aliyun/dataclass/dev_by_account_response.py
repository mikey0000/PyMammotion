from dataclasses import dataclass
from typing import List, Optional

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class Device(DataClassORJSONMixin):
    productModel: str
    gmtModified: int
    netType: str
    nickName: str
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
    productImage: Optional[str] = None
    categoryImage: Optional[str] = None


@dataclass
class Data(DataClassORJSONMixin):
    total: int
    data: List[Device]
    pageNo: int
    pageSize: int


@dataclass
class ListingDevByAccountResponse(DataClassORJSONMixin):
    code: int
    data: Optional[Data]
    id: Optional[str] = None
