"""Regression tests for partial ``thing.event.property.post`` payloads.

Mammotion devices routinely send property posts containing only a small subset
of fields (sometimes a single field). Before this fix, ``DeviceProperties``
marked nearly every field as required, so any partial post raised
``MissingField`` and was silently dropped at
``pymammotion/transport/mqtt.py:_dispatch_mammotion_properties``.

Payloads here are real, PII-redacted captures from a Spino E1
(see https://github.com/mikey0000/Mammotion-HA/issues/763).
"""

import json

from pymammotion.data.mqtt.mammotion_properties import DeviceProperties
from pymammotion.data.mqtt.properties import MammotionPropertiesMessage


SPINO_MODEL_ONLY = json.dumps(
    {
        "id": "14846",
        "version": "1.0",
        "sys": {"ack": 1},
        "params": {"intMod": "SPINO E1", "extMod": "SPINO E1"},
        "method": "thing.event.property.post",
    }
)

SPINO_FW_ONLY = json.dumps(
    {
        "id": "14848",
        "version": "1.0",
        "sys": {"ack": 1},
        "params": {
            "deviceVersion": "1.15.2.1039",
            "deviceVersionInfo": json.dumps(
                {
                    "devVer": "1.15.2.1039",
                    "whole": 1,
                    "fwInfo": [
                        {"t": "63", "c": "63-PAWG4", "v": "1.2.0.275"},
                        {"t": "65", "c": "65-PACG4", "v": "1.2.0.279"},
                    ],
                }
            ),
        },
        "method": "thing.event.property.post",
    }
)


def test_partial_property_post_model_fields_only() -> None:
    """A property/post carrying only ``intMod`` / ``extMod`` decodes successfully."""
    msg = MammotionPropertiesMessage.from_json(SPINO_MODEL_ONLY)
    p = msg.params

    assert p.int_mod == "SPINO E1"
    assert p.ext_mod == "SPINO E1"

    # Absent fields default rather than raising; absent nested objects are None.
    assert p.device_state == 0
    assert p.battery_percentage == 0
    assert p.device_version == ""
    assert p.network_info is None
    assert p.coordinate is None
    assert p.device_other_info is None
    assert p.device_version_info is None
    assert p.check_data is None


def test_partial_property_post_firmware_only() -> None:
    """A property/post carrying only ``deviceVersion`` / ``deviceVersionInfo`` decodes successfully."""
    msg = MammotionPropertiesMessage.from_json(SPINO_FW_ONLY)
    p = msg.params

    assert p.device_version == "1.15.2.1039"
    assert p.device_version_info is not None
    assert p.device_version_info.dev_ver == "1.15.2.1039"
    assert [fw.c for fw in p.device_version_info.fw_info] == ["63-PAWG4", "65-PACG4"]

    # Everything else defaults / is None.
    assert p.battery_percentage == 0
    assert p.network_info is None
    assert p.coordinate is None


def test_device_properties_accepts_empty_params() -> None:
    """A property/post with no params at all still decodes (every field optional)."""
    p = DeviceProperties.from_dict({})
    assert p.device_state == 0
    assert p.network_info is None
