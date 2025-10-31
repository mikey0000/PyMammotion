from dataclasses import dataclass

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class Device(DataClassORJSONMixin):
    """Unified device model supporting both Device and ShareNotification data"""

    # Core device fields (from Device model)
    gmt_modified: int
    node_type: str
    device_name: str
    product_name: str
    status: int
    identity_id: str

    # Required fields from original Device model
    net_type: str
    category_key: str
    product_key: str
    is_edge_gateway: bool
    category_name: str
    identity_alias: str
    iot_id: str
    bind_time: int
    owned: int
    thing_type: str

    # Optional fields (common to both or nullable)
    nick_name: str | None = None
    description: str | None = None
    product_image: str | None = None
    category_image: str | None = None
    product_model: str | None = None

    # Optional fields from ShareNotification only
    target_id: str | None = None
    receiver_identity_id: str | None = None
    target_type: str | None = None
    gmt_create: int | None = None
    batch_id: str | None = None
    record_id: str | None = None
    initiator_identity_id: str | None = None
    is_receiver: int | None = None
    initiator_alias: str | None = None
    receiver_alias: str | None = None

    class Config(BaseConfig):
        omit_default = True
        serialize_by_alias = True
        aliases = {
            # Original Device model aliases
            "gmt_modified": "gmtModified",
            "net_type": "netType",
            "category_key": "categoryKey",
            "product_key": "productKey",
            "node_type": "nodeType",
            "is_edge_gateway": "isEdgeGateway",
            "device_name": "deviceName",
            "category_name": "categoryName",
            "identity_alias": "identityAlias",
            "product_name": "productName",
            "iot_id": "iotId",
            "bind_time": "bindTime",
            "identity_id": "identityId",
            "thing_type": "thingType",
            "nick_name": "nickName",
            "product_image": "productImage",
            "category_image": "categoryImage",
            "product_model": "productModel",
            # ShareNotification specific aliases
            "target_id": "targetId",
            "receiver_identity_id": "receiverIdentityId",
            "target_type": "targetType",
            "gmt_create": "gmtCreate",
            "batch_id": "batchId",
            "record_id": "recordId",
            "initiator_identity_id": "initiatorIdentityId",
            "is_receiver": "isReceiver",
            "initiator_alias": "initiatorAlias",
            "receiver_alias": "receiverAlias",
        }


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
