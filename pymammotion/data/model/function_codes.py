"""The function set stored per device, keyed like the app's ``functions_config`` table.

The app caches ``product-version-function/list`` by ``(productKey, productVersion)``
with no expiry and treats any other firmware as a cache miss, so the pair the list
was fetched for is stored with it.
"""

from dataclasses import dataclass, field

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class FunctionCodes(DataClassORJSONMixin):
    """Function codes the cloud listed for one product key at one firmware version."""

    class Config(BaseConfig):
        """Tolerate keys a newer library version wrote."""

        forbid_extra_keys = False

    product_key: str = ""
    product_version: str = ""
    codes: list[str] = field(default_factory=list)

    def is_current_for(self, product_key: str, product_version: str) -> bool:
        """Return True when this set was fetched for exactly this product key and firmware."""
        return bool(product_key and product_version) and (self.product_key, self.product_version) == (
            product_key,
            product_version,
        )

    def supports(self, code: str, product_version: str) -> bool:
        """Return True when *code* is listed and the set was fetched for *product_version*."""
        return bool(product_version) and self.product_version == product_version and code in self.codes
