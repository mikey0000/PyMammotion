"""DeviceConfig — the per-product-key capability tables.

The two tables are module-level constants rather than instance state, because the
Home Assistant integration constructs a ``DeviceConfig()`` on every number-entity
limit read (``custom_components/mammotion/number.py``) — rebuilding ~200 nested
dict literals each time.
"""

from __future__ import annotations

from pymammotion.data.model.device_capabilities import _DEFAULT_LIST, _INNER_LIST, DeviceConfig
from pymammotion.data.model.device_limits import DeviceLimits
from pymammotion.utility.device_type import AliyunProductKey, LubaProductKey


def test_instances_share_the_tables_rather_than_rebuilding_them() -> None:
    first, second = DeviceConfig(), DeviceConfig()
    assert first.default_list is second.default_list is _DEFAULT_LIST
    assert first.inner_list is second.inner_list is _INNER_LIST


def test_tables_are_populated() -> None:
    """A silent truncation during the hoist would leave lookups quietly returning None."""
    assert len(_DEFAULT_LIST) == 12
    assert len(_INNER_LIST) == 184


def test_lookup_by_internal_model_code() -> None:
    assert DeviceConfig().get_external_model("HM010060LBAWD10") == "LubaAWD1000"


def test_lookup_by_product_key() -> None:
    limits = DeviceConfig().get_working_parameters("a1ZU6bdGjaM")
    assert isinstance(limits, DeviceLimits)
    assert (limits.blade_height.min, limits.blade_height.max) == (30, 70)


def test_internal_model_wins_over_product_key() -> None:
    """get_device_config checks inner_list first; both tables can hold the same key."""
    config = DeviceConfig()
    overlapping = set(_INNER_LIST) & set(_DEFAULT_LIST)
    for key in overlapping:
        assert config.get_device_config(key) is _INNER_LIST[key]


def test_unknown_key_returns_none() -> None:
    assert DeviceConfig().get_device_config("not-a-real-key") is None


def test_lookups_do_not_mutate_the_shared_tables() -> None:
    """The tables are shared across every instance, so a mutating lookup would leak."""
    before = ({k: dict(v) for k, v in _DEFAULT_LIST.items()}, {k: dict(v) for k, v in _INNER_LIST.items()})
    config = DeviceConfig()
    config.get_device_config("HM010060LBAWD10")
    config.get_working_parameters("a1ZU6bdGjaM")
    config.get_external_model("HM010060LBAWD10")
    assert (_DEFAULT_LIST, _INNER_LIST) == before


def test_every_capability_product_key_is_a_known_luba_1() -> None:
    """``_DEFAULT_LIST`` is keyed by Luba 1 product key, and both tables must list the same set.

    A key here but not in ``LubaProductKey`` still resolves to UNKNOWN in
    ``DeviceType.value_of_str`` and, worse, misses ``AliyunProductKey`` — so an Aliyun
    Luba 1 gets pointed at the Mammotion broker.  ``a1FbaU4Bqk5`` was exactly that.
    """
    missing = set(_DEFAULT_LIST) - set(LubaProductKey)
    assert not missing, f"capability keys absent from LubaProductKey: {sorted(missing)}"
    assert set(_DEFAULT_LIST) <= set(AliyunProductKey)
