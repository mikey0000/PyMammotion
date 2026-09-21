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


@dataclass
class ProductParam(DataClassORJSONMixin):
    """One settable job parameter for a model, as the app would render it."""

    class Config(BaseConfig):
        """Unknown keys are tolerated: the schema gains fields between app releases."""

        forbid_extra_keys = False

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
        """Unknown keys are tolerated."""

        forbid_extra_keys = False

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
            for param in sorted(self.detail_vos, key=lambda p: (p.sort, p.code))
        }
