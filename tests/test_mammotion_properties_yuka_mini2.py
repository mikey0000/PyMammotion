"""Regression test for the Yuka Mini 2 ``thing.event.property.post`` parse failure.

A Yuka Mini 2 (single-drive-motor, no RTK) reports a property payload that omits
several version/diagnostic fields the model previously marked as *required*
(``leftMotorVersion``, ``rightMotorVersion``, ``rtkVersion``, ``bmsVersion``,
``leftMotorBootVersion``, ``rightMotorBootVersion``, ``DeviceOtherInfo.tilt_degree``,
``NetworkInfo.ip``, ``NetworkInfo.apn_num``). A single missing required field made
``mashumaro`` raise ``MissingField`` and the *entire* property update (battery, state,
knife height, …) was dropped, leaving Home Assistant with permanently stale status.

The fixture is a real, PII-redacted payload captured from a Yuka Mini 2 (``Yuka-ML744XZH``).
"""

import json
from pathlib import Path

from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

FIXTURE = Path(__file__).parent / "fixtures" / "yuka_mini2_property_post.json"


def test_yuka_mini2_property_post_parses() -> None:
    """The full property message decodes instead of being dropped on a missing field."""
    raw = FIXTURE.read_bytes()
    msg = MammotionPropertiesMessage.from_json(raw)
    p = msg.params

    # Core status that HA depends on — the data that was being thrown away.
    assert p.battery_percentage == 31
    assert p.device_state == 13
    assert p.knife_height == 60
    assert "YUKA mini 2" in p.ext_mod
    assert p.device_version == "2.3.23.19"

    # Fields this device class does not report must default, not raise.
    assert p.left_motor_version == ""
    assert p.right_motor_version == ""
    assert p.rtk_version == ""
    assert p.bms_version == ""
    assert p.network_info.ip == ""
    assert p.network_info.apn_num == 0
    assert p.device_other_info.tilt_degree == ""

    # Fields the device *does* report still populate (incl. the previously typo'd alias).
    assert p.network_info.wifi_rssi == -65
    assert p.device_other_info.iot_con_fail_min == "0"
    assert [fw.c for fw in p.device_version_info.fw_info][:2] == [
        "202-MNWheelfG4BT",
        "201-MNWheelfG4",
    ]


def test_missing_optional_fields_does_not_raise() -> None:
    """Stripping every now-optional key must still yield a usable message."""
    obj = json.loads(FIXTURE.read_bytes())
    for key in ("leftMotorVersion", "rightMotorVersion", "rtkVersion", "bmsVersion"):
        obj["params"].pop(key, None)  # already absent for this device, asserted explicit
    msg = MammotionPropertiesMessage.from_json(json.dumps(obj))
    assert msg.params.battery_percentage == 31
