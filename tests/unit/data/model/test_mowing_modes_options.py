"""Obstacle-detection options and the labels the app puts on them.

The app's off position is value **1** on the new Off/Standard/Sensitive list
(``WorkingSettingManage.aytomatiTypecRange = {"1", "10", "11"}``) and value 0 on
the older touch lists, and ``SettingOptionsView.initBypassingStrategy`` labels a
value differently depending on which list the device has. Mammotion-HA #887 was
filed because value 0 reads "Off" while the public API docs describe 0/1 as
"slowtouch".
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.mowing_modes import DetectionStrategy


def test_luba1_keeps_the_three_option_touch_list() -> None:
    """Luba 1 never had the no-touch option."""
    assert DetectionStrategy.for_device("Luba-123456") == [
        DetectionStrategy.direct_touch,
        DetectionStrategy.slow_touch,
        DetectionStrategy.less_touch,
    ]


def test_old_firmware_keeps_the_four_option_touch_list() -> None:
    """Luba 2 / Yuka below 1.12.0 still show the old touch UI."""
    assert DetectionStrategy.for_device("Luba-VS12345", "1.11.9") == [
        DetectionStrategy.direct_touch,
        DetectionStrategy.slow_touch,
        DetectionStrategy.less_touch,
        DetectionStrategy.no_touch,
    ]


@pytest.mark.parametrize("device", ["Luba-VS12345", "Yuka-123456", "Yuka-MN1234"])
def test_new_style_devices_use_one_not_zero_for_off(device: str) -> None:
    """The app sends 1 for off here; 0 is not in its range at all."""
    options = DetectionStrategy.for_device(device, "1.12.0")
    assert options == [
        DetectionStrategy.slow_touch,
        DetectionStrategy.no_touch,
        DetectionStrategy.sensitive,
    ]
    assert DetectionStrategy.direct_touch not in options


def test_one_reads_as_off_on_the_new_list() -> None:
    """Value 1 is the off position there, not "slow touch"."""
    options = DetectionStrategy.for_device("Yuka-MN1234")
    assert [s.option_key(options) for s in options] == ["off", "standard", "sensitive"]


def test_one_reads_as_slow_touch_where_zero_is_also_offered() -> None:
    """On the touch lists 0 is off, so 1 keeps its own label."""
    options = DetectionStrategy.for_device("Luba-VS12345", "1.11.9")
    assert [s.option_key(options) for s in options] == [
        "off",
        "slow_touch",
        "less_touch",
        "standard",
    ]


def test_luba1_options_stay_distinct() -> None:
    """The app would label two of these three "Off"; keying off 0 avoids that."""
    options = DetectionStrategy.for_device("Luba-123456")
    keys = [s.option_key(options) for s in options]
    assert keys == ["off", "slow_touch", "less_touch"]
    assert len(set(keys)) == len(keys)


@pytest.mark.parametrize("device", ["Luba-123456", "Luba-VS12345", "Yuka-MN1234"])
def test_option_keys_round_trip(device: str) -> None:
    """Every key a device presents resolves back to the strategy it came from."""
    options = DetectionStrategy.for_device(device)
    for strategy in options:
        assert (
            DetectionStrategy.from_option_key(strategy.option_key(options), options) is strategy
        )


def test_an_unknown_key_is_rejected() -> None:
    """A stale restored option must not silently pick the wrong value."""
    options = DetectionStrategy.for_device("Yuka-MN1234")
    with pytest.raises(ValueError, match="direct_touch"):
        DetectionStrategy.from_option_key("direct_touch", options)
