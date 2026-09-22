"""Nested-object tolerance in the Mammotion ``thing.event.property.post`` model.

``deviceOtherInfo`` is a firmware diagnostics dump whose key set differs per
model, and nothing in the library reads it.  A shape this module has not seen
must never cost the battery and state carried in the same post.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pymammotion.data.mqtt.mammotion_properties import DeviceOtherInfo
from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

# tests/unit/data/mqtt/ → repo tests/ is parents[3].
DATA = Path(__file__).parents[3] / "data"
LIDAR_OTHER_INFO = (DATA / "luba_mini_awd_lidar_other_info.json").read_text()


def _property_post(device_other_info: str) -> str:
    """Build a post carrying core status plus the diagnostics blob as the device sends it: a JSON string."""
    return json.dumps(
        {
            "id": "1",
            "version": "1.0",
            "sys": {"ack": 1},
            "params": {"batteryPercentage": 31, "deviceState": 13, "deviceOtherInfo": device_other_info},
        }
    )


@pytest.mark.regression
def test_luba_mini_awd_lidar_other_info_parses() -> None:
    """The Luba mini AWD LiDAR omits ``ins_fusion`` and ``vslam_vio``; both were required (#189)."""
    info = DeviceOtherInfo.from_json(LIDAR_OTHER_INFO)
    assert info.ins_fusion == ""
    assert info.vslam_vio == ""
    assert info.soc_up_time == 297340


@pytest.mark.regression
def test_unparseable_diagnostics_blob_does_not_drop_the_post() -> None:
    """A diagnostics key this model lacks used to fail the whole message, not just the blob."""
    blob = json.loads(LIDAR_OTHER_INFO)
    del blob["socUpTime"]
    msg = MammotionPropertiesMessage.from_json(_property_post(json.dumps(blob)))
    assert msg.params.battery_percentage == 31
    assert msg.params.device_state == 13
    assert msg.params.device_other_info is None


def test_parseable_diagnostics_blob_is_kept() -> None:
    """Tolerance must not turn every blob into None."""
    msg = MammotionPropertiesMessage.from_json(_property_post(LIDAR_OTHER_INFO))
    assert msg.params.device_other_info is not None
    assert msg.params.device_other_info.tilt_degree == "43.10"


def test_unparseable_diagnostics_object_does_not_drop_the_post() -> None:
    """The same tolerance covers the blob sent as a JSON object rather than a string."""
    blob = json.loads(LIDAR_OTHER_INFO)
    del blob["socUpTime"]
    post = json.loads(_property_post(""))
    post["params"]["deviceOtherInfo"] = blob
    msg = MammotionPropertiesMessage.from_json(json.dumps(post))
    assert msg.params.battery_percentage == 31
    assert msg.params.device_other_info is None
