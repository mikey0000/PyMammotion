"""The per-model work-setting parameter schema served by the Mammotion API.

The app asks ``product/param/version/search`` which of the job settings a given
model and firmware actually has, and how each one should be presented: whether
to show the row at all (``is_show``), what to default it to (``default_value``),
whether the user may change it (``is_force``), and the bounds of the control
(``min`` / ``max`` / ``step`` / ``range``).  ``WorkingSettingManage`` in the APK
switches on ``code`` — "15" is ride-boundary distance, "21" start progress, and
so on.

Nothing in the library calls this at runtime.  It is here so the schema can be
dumped with ``scripts/dump_product_params.py`` and folded into the hard-coded
capability helpers by hand, the way ``DeviceType.supports_auto_change_direction``
already approximates one of these rows.
"""

from dataclasses import dataclass, field
from typing import Any

from mashumaro import field_options
from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin


def _sort_key(param: "ProductParam") -> tuple[int, int, str]:
    """Order rows by the app's sort, then numerically by code.

    Codes are strings on the wire, so a plain sort puts "12" before "3".
    """
    try:
        return (param.sort, int(param.code), "")
    except (TypeError, ValueError):
        return (param.sort, 1 << 31, param.code)


@dataclass
class ProductParam(DataClassORJSONMixin):
    """One settable job parameter for a model, as the app would render it."""

    class Config(BaseConfig):
        """Tolerate new keys, and read back what ``to_dict`` wrote.

        Without ``allow_deserialization_not_by_alias`` a round trip through
        ``to_dict`` silently yields an empty list: it writes field names while
        the aliases are what the wire uses, and a host persisting the schema
        would read back nothing.
        """

        forbid_extra_keys = False
        allow_deserialization_not_by_alias = True

    code: str = ""
    name: str = ""
    default_value: str | None = field(default=None, metadata=field_options(alias="defaultValue"))
    min: str | None = None
    max: str | None = None
    step: str | None = None
    range: list[str] = field(default_factory=list)
    ui_type: str | None = field(default=None, metadata=field_options(alias="uiType"))
    data_type: int = field(default=0, metadata=field_options(alias="dataType"))
    #: 1 when the app shows the row for this model at all.
    is_show: int = field(default=0, metadata=field_options(alias="isShow"))
    #: 1 when the value is imposed rather than offered.
    is_force: int = field(default=0, metadata=field_options(alias="isForce"))
    sort: int = 0

    @property
    def shown(self) -> bool:
        """Whether the app would show this parameter for the queried model."""
        return self.is_show == 1


@dataclass
class ProductParamData(DataClassORJSONMixin):
    """The parameter set for one product key at one firmware version."""

    class Config(BaseConfig):
        """Tolerate new keys, and read back what ``to_dict`` wrote."""

        forbid_extra_keys = False
        allow_deserialization_not_by_alias = True

    detail_vos: list[ProductParam] = field(default_factory=list, metadata=field_options(alias="detailVos"))
    int_mod: str | None = field(default=None, metadata=field_options(alias="intMod"))
    min_product_version: str | None = field(default=None, metadata=field_options(alias="minProductVersion"))
    product_key: str | None = field(default=None, metadata=field_options(alias="productKey"))
    version: str | None = None

    def by_code(self) -> dict[str, ProductParam]:
        """Return the parameters keyed by the code ``WorkingSettingManage`` switches on."""
        return {param.code: param for param in self.detail_vos}

    def to_summary(self) -> dict[str, Any]:
        """Return a flat, diffable view for the dump script."""
        return {
            param.code: {
                "name": param.name,
                "shown": param.shown,
                "default": param.default_value,
                "min": param.min,
                "max": param.max,
                "step": param.step,
                "range": param.range,
                "ui_type": param.ui_type,
                "forced": param.is_force == 1,
            }
            for param in sorted(self.detail_vos, key=_sort_key)
        }
