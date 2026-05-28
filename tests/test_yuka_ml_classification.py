"""Regression tests for Yuka Mini 2 (YUKA_ML / Yuka-ML / MN232) classification.

The generic ``LUBA_YUKA`` rule (name prefix ``"Yuka-"``) used to be ordered before the
specific ``YUKA_ML`` (``"Yuka-ML"``) and ``YUKA_MINIV`` (``"Yuka-MV"``) rules in
``value_of_str``. Because ``"Yuka-"`` is a substring of those prefixes, a real Yuka Mini 2
device name like ``"Yuka-ML744XZH"`` resolved to ``LUBA_YUKA`` (the original full-size Yuka)
instead of ``YUKA_ML``. That misclassification meant the HA integration's capability gates
(``is_yuka_mini`` / ``is_mini_or_x_series``) returned the wrong answers: the mower wrongly
got full-Yuka grass-collection entities and was denied its blade-speed (cutter) and light
controls.
"""

import pytest

from pymammotion.utility.device_type import DeviceType

YUKA_MINI2_NAME = "Yuka-ML744XZH"  # real device name


def test_yuka_ml_name_resolves_to_yuka_ml() -> None:
    assert DeviceType.value_of_str(YUKA_MINI2_NAME) is DeviceType.YUKA_ML


def test_yuka_miniv_no_longer_shadowed() -> None:
    """Yuka-MV (YUKA_MINIV) was shadowed by the same ordering bug."""
    assert DeviceType.value_of_str("Yuka-MV000001") is DeviceType.YUKA_MINIV


def test_original_yuka_still_generic() -> None:
    """A bare Yuka- name (no specific suffix) still resolves to the original Yuka."""
    assert DeviceType.value_of_str("Yuka-000001") is DeviceType.LUBA_YUKA


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        ("is_yuka", True),
        ("is_yuka_mini", True),          # mulch-only Mini 2 -> grass-collection excluded
        ("is_mini_or_x_series", True),   # -> cutter-speed + light controls exposed
        ("is_luba_pro", True),           # camera / voice entities preserved
        ("has_4g", True),                # Mini 2 has cellular
        ("is_rtk", False),               # vision-only, no RTK
        ("is_luba1", False),
    ],
)
def test_yuka_mini2_capabilities(predicate: str, expected: bool) -> None:
    assert getattr(DeviceType, predicate)(YUKA_MINI2_NAME) is expected
