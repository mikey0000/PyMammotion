"""Wire-value enums in ``utility/constant/device_enums``: values the app itself compares against."""

from __future__ import annotations

import pytest

from pymammotion.utility.constant.device_enums import VioBrightness, VioState


@pytest.mark.parametrize("raw", [160, 232], ids=["luba3_fw_2_3_27", "luba3_fw_2_3_30"])
def test_vio_state_reads_the_luba_3_s_uninitialised_values_as_unknown(raw: int) -> None:
    """Real Luba 3 frames; the app compares vio_state to 0-3 and decodes no bits of it."""
    assert VioState(raw) is VioState.SIGNAL_UNKNOWN


@pytest.mark.parametrize(
    ("raw", "member"),
    [(0, VioBrightness.DARK), (1, VioBrightness.GOOD), (2, VioBrightness.INTENSE), (240, VioBrightness.UNKNOWN)],
)
def test_vio_brightness_follows_the_app_s_mapping(raw: int, member: VioBrightness) -> None:
    """``SignalHelper.refreshVioBrightnessSignal``: 0 Dark, 1 Good, 2 Intense, anything else "--"."""
    assert VioBrightness(raw) is member
