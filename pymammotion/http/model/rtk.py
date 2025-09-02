"""RTK device information."""
from dataclasses import dataclass, field

from mashumaro import field_options
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class RTK(DataClassORJSONMixin):
    """RTK device information."""

    device_id: str = field(metadata=field_options(alias="deviceId"))
    device_name: str = field(metadata=field_options(alias="deviceName"))
    product_key: str = field(metadata=field_options(alias="productKey"))
    status: int
    lora: str
