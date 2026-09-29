"""Display-string helpers in ``utility/constant/display``, which the HA sensors render verbatim."""

from __future__ import annotations

import pytest

from pymammotion.utility.constant.display import camera_brightness


@pytest.mark.regression
@pytest.mark.parametrize(
    ("raw", "state"),
    [(0, "dark"), (1, "good"), (2, "intense"), (17, "unknown"), (240, "unknown"), (242, "unknown")],
)
def test_camera_brightness_renders_the_app_s_three_states(raw: int, state: str) -> None:
    """It showed 1 as "Light", 2 as "Dark" and anything above 45 (the Luba 3's garbage 240) as "Light".

    The app's mapping is 0 Dark, 1 Good, 2 Intense, anything else "--".
    """
    assert camera_brightness(raw) == state
