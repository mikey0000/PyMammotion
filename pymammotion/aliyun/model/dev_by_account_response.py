from dataclasses import dataclass
from typing import Annotated, Optional

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


@dataclass
class Device(DataClassORJSONMixin):
    """Unified device model supporting both Device and ShareNotification data"""

    # Core device fields (from Device model)
    gmt_modified: Annotated[int, Alias("gmtModified")]
    node_type: Annotated[str, Alias("nodeType")]
    device_name: Annotated[str, Alias("deviceName")]
    product_name: Annotated[str, Alias("productName")]
    status: int
    identity_id: Annotated[str, Alias("identityId")]

    # Required fields from original Device model
    net_type: Annotated[str, Alias("netType")]
    category_key: Annotated[str, Alias("categoryKey")]
    product_key: Annotated[str, Alias("productKey")]
    is_edge_gateway: Annotated[bool, Alias("isEdgeGateway")]
    category_name: Annotated[str, Alias("categoryName")]
    identity_alias: Annotated[str, Alias("identityAlias")]
    iot_id: Annotated[str, Alias("iotId")]
    bind_time: Annotated[int, Alias("bindTime")]
    owned: int
    thing_type: Annotated[str, Alias("thingType")]

    # Optional fields (common to both or nullable)
    nick_name: Annotated[Optional[str], Alias("nickName")] = None
    description: Optional[str] = None
    product_image: Annotated[Optional[str], Alias("productImage")] = None
    category_image: Annotated[Optional[str], Alias("categoryImage")] = None
    product_model: Annotated[Optional[str], Alias("productModel")] = None

    # Optional fields from ShareNotification only
    target_id: Annotated[Optional[str], Alias("targetId")] = None
    receiver_identity_id: Annotated[Optional[str], Alias("receiverIdentityId")] = None
    target_type: Annotated[Optional[str], Alias("targetType")] = None
    gmt_create: Annotated[Optional[int], Alias("gmtCreate")] = None
    batch_id: Annotated[Optional[str], Alias("batchId")] = None
    record_id: Annotated[Optional[str], Alias("recordId")] = None
    initiator_identity_id: Annotated[Optional[str], Alias("initiatorIdentityId")] = None
    is_receiver: Annotated[Optional[int], Alias("isReceiver")] = None
    initiator_alias: Annotated[Optional[str], Alias("initiatorAlias")] = None
    receiver_alias: Annotated[Optional[str], Alias("receiverAlias")] = None

    class Config(BaseConfig):
        omit_default = True
        allow_deserialization_not_by_alias = True


# # Alternative: Keep them separate but with a common base class
# @dataclass
# class BaseDevice(DataClassORJSONMixin):
#     """Base device model with common fields"""
#
#     gmt_modified: int
#     node_type: str
#     device_name: str
#     product_name: str
#     status: int
#     product_image: Optional[str] = None
#     category_image: Optional[str] = None
#     description: Optional[str] = None
#
#     class Config(BaseConfig):
#         omit_default = True
#         serialize_by_alias = True
#         aliases = {
#             "gmt_modified": "gmtModified",
#             "node_type": "nodeType",
#             "device_name": "deviceName",
#             "product_name": "productName",
#             "product_image": "productImage",
#             "category_image": "categoryImage",
#         }
#
#
# @dataclass
# class Device(BaseDevice):
#     """Full device model"""
#
#     net_type: str
#     category_key: str
#     product_key: str
#     is_edge_gateway: bool
#     category_name: str
#     identity_alias: str
#     iot_id: str
#     bind_time: int
#     owned: int
#     identity_id: str
#     thing_type: str
#     nick_name: Optional[str] = None
#     product_model: Optional[str] = None
#
#     class Config(BaseConfig):
#         omit_default = True
#         serialize_by_alias = True
#         aliases = {
#             **BaseDevice.Config.aliases,
#             "net_type": "netType",
#             "category_key": "categoryKey",
#             "product_key": "productKey",
#             "is_edge_gateway": "isEdgeGateway",
#             "category_name": "categoryName",
#             "identity_alias": "identityAlias",
#             "iot_id": "iotId",
#             "bind_time": "bindTime",
#             "identity_id": "identityId",
#             "thing_type": "thingType",
#             "nick_name": "nickName",
#             "product_model": "productModel",
#         }
#
#
# @dataclass
# class ShareNotification(BaseDevice):
#     """Share notification model extending base device"""
#
#     target_id: str
#     receiver_identity_id: str
#     target_type: str
#     gmt_create: int
#     batch_id: str
#     record_id: str
#     initiator_identity_id: str
#     is_receiver: int
#     initiator_alias: str
#     receiver_alias: str
#
#     # Optional fields that Device has but ShareNotification might not
#     net_type: Optional[str] = None
#     category_key: Optional[str] = None
#     product_key: Optional[str] = None
#     is_edge_gateway: Optional[bool] = None
#     category_name: Optional[str] = None
#     identity_alias: Optional[str] = None
#     iot_id: Optional[str] = None
#     bind_time: Optional[int] = None
#     owned: Optional[int] = None
#     identity_id: Optional[str] = None
#     thing_type: Optional[str] = None
#     nick_name: Optional[str] = None
#     product_model: Optional[str] = None
#
#     class Config(BaseConfig):
#         omit_default = True
#         serialize_by_alias = True
#         aliases = {
#             **BaseDevice.Config.aliases,
#             "target_id": "targetId",
#             "receiver_identity_id": "receiverIdentityId",
#             "target_type": "targetType",
#             "gmt_create": "gmtCreate",
#             "batch_id": "batchId",
#             "record_id": "recordId",
#             "initiator_identity_id": "initiatorIdentityId",
#             "is_receiver": "isReceiver",
#             "initiator_alias": "initiatorAlias",
#             "receiver_alias": "receiverAlias",
#             # Device fields that might be present
#             "net_type": "netType",
#             "category_key": "categoryKey",
#             "product_key": "productKey",
#             "is_edge_gateway": "isEdgeGateway",
#             "category_name": "categoryName",
#             "identity_alias": "identityAlias",
#             "iot_id": "iotId",
#             "bind_time": "bindTime",
#             "identity_id": "identityId",
#             "thing_type": "thingType",
#             "nick_name": "nickName",
#             "product_model": "productModel",
#         }


@dataclass
class Data(DataClassORJSONMixin):
    total: int
    data: list[Device]
    pageNo: int
    pageSize: int


@dataclass
class ListingDevAccountResponse(DataClassORJSONMixin):
    code: int
    data: Data | None
    id: str | None = None
