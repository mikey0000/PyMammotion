"""Cleaning modes are per pool-cleaner model, not one list for all of them.

Mammotion-HA #891's sibling report: an E1 was offered Waterline and Custom,
which that hardware does not have. The app carries two mode enums —
``SwimmingWorkModule`` for the touch models and ``SwimmingSPWorkModule`` for the
PC210 SP — and narrows further still for Waterline.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.pool_state import SpinoWorkMode

_E1 = ("Spino-E1C36JT4", "a15Cq8FbCh1")
_SP = ("Spino-S1ABCDEF", "FCtXbVnmd2C")
_PLAIN = ("Spino-ABCDEFG", "a1UvLZ3mWcW")


def test_an_e1_has_four_modes() -> None:
    """No Waterline (it is PC200-only) and no Custom (SP-only)."""
    assert SpinoWorkMode.for_device(*_E1) == [
        SpinoWorkMode.AUTO,
        SpinoWorkMode.FLOOR,
        SpinoWorkMode.WALL,
        SpinoWorkMode.ECO,
    ]


def test_a_plain_spino_matches_the_e1() -> None:
    """``isPC100`` is true for anything that is not a SWIMMINGPOOL_S1."""
    assert SpinoWorkMode.for_device(*_PLAIN) == SpinoWorkMode.for_device(*_E1)


def test_the_sp_adds_waterline_and_custom() -> None:
    """``SwimmingSPWorkModule`` is the only enum carrying CUSTOM."""
    assert SpinoWorkMode.for_device(*_SP) == [
        SpinoWorkMode.AUTO,
        SpinoWorkMode.FLOOR,
        SpinoWorkMode.WALL,
        SpinoWorkMode.ECO,
        SpinoWorkMode.LINE,
        SpinoWorkMode.CUSTOM,
    ]


def test_the_pc200_branch_is_currently_unreachable() -> None:
    """SWIMMINGPOOL_S1 is the only variant that gets Waterline without Custom.

    Nothing resolves to it today: the SP entry claims the ``Spino-S1`` prefix
    and is matched first, and S1 has no product-key matcher of its own — so a
    real PC200 lands on the four-mode list and is missing Waterline.  The
    branch in ``for_device`` stays for when a key is known; this test fails the
    moment one is added, as a prompt to revisit.
    """
    from pymammotion.utility.device_type import DeviceType

    assert DeviceType.value_of_str("Spino-S1ABCDEF") is DeviceType.SWIMMINGPOOL_SP
    reachable = {DeviceType.value_of_str(name, key) for name, key in (_E1, _SP, _PLAIN, ("Spino-S1ABCDEF", ""))}
    assert DeviceType.SWIMMINGPOOL_S1 not in reachable


@pytest.mark.parametrize("device", [_E1, _SP, _PLAIN])
def test_no_list_offers_a_non_mode(device: tuple[str, str]) -> None:
    """OFF and UNKNOWN are reported states, never something to start."""
    modes = SpinoWorkMode.for_device(*device)
    assert SpinoWorkMode.OFF not in modes
    assert SpinoWorkMode.UNKNOWN not in modes


@pytest.mark.parametrize("device", [_E1, _SP, _PLAIN])
def test_the_common_four_are_always_present(device: tuple[str, str]) -> None:
    """Every cleaner does floor, wall, the combined pass and eco."""
    modes = SpinoWorkMode.for_device(*device)
    assert modes[:4] == [
        SpinoWorkMode.AUTO,
        SpinoWorkMode.FLOOR,
        SpinoWorkMode.WALL,
        SpinoWorkMode.ECO,
    ]


def test_an_unknown_device_falls_back_to_the_narrow_list() -> None:
    """Offering a mode the hardware lacks is worse than offering too few."""
    assert SpinoWorkMode.for_device("", "") == SpinoWorkMode.for_device(*_E1)
