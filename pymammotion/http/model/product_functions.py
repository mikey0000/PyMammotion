"""The function set the Mammotion API publishes per product key and firmware version.

``device-server/v1/product-version-function/list`` answers which feature codes a
firmware has (``002.002`` remote drive, ``001.006.001`` video encryption,
``003.001`` child safety, ...).  The app asks ``FunctionsConfigFacade.hasFunctionCode``
before showing those features.
"""

from dataclasses import dataclass, field

from mashumaro import field_options
from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class ProductFunction(DataClassORJSONMixin):
    """One feature row; every field is nullable in the app's model."""

    class Config(BaseConfig):
        """Tolerate new keys, and read back what ``to_dict`` wrote."""

        forbid_extra_keys = False
        allow_deserialization_not_by_alias = True

    id: str | int | None = None
    parent_id: str | int | None = field(default=None, metadata=field_options(alias="parentId"))
    function_name: str | None = field(default=None, metadata=field_options(alias="functionName"))
    function_code: str | None = field(default=None, metadata=field_options(alias="functionCode"))
    remark: str | None = None


@dataclass
class ProductFunctionsData(DataClassORJSONMixin):
    """The function set for one ``(productKey, productVersion)``."""

    class Config(BaseConfig):
        """Tolerate new keys, and read back what ``to_dict`` wrote."""

        forbid_extra_keys = False
        allow_deserialization_not_by_alias = True

    product_key: str | None = field(default=None, metadata=field_options(alias="productKey"))
    product_version: str | None = field(default=None, metadata=field_options(alias="productVersion"))
    functions: list[ProductFunction] | None = None

    def codes(self) -> list[str]:
        """Return the function codes, skipping rows that carry none."""
        return [function.function_code for function in self.functions or [] if function.function_code]
