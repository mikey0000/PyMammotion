"""The MammotionCommand builder DeviceHandle hands out.

Split from ``test_handle.py``: what the builder is configured with is its own
concern, and NAV routing (``get_msg_device``) reads the product key off it.
"""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.handle import DeviceHandle
from tests._helpers import make_mock_handle


def test_commands_carry_the_product_key_from_the_device_list() -> None:
    """get_msg_device routes NAV by device type, which needs the product key.

    Without it every device falls back to name-only detection, so a model we know
    by product key but not by name prefix is routed as UNKNOWN.
    """
    handle = make_mock_handle(device_id="dev-pk", device_name="Luba-Test")
    handle.product_key = "a1ZU6bdGjaM"

    assert handle.commands.get_device_product_key() == "a1ZU6bdGjaM"


def test_commands_fall_back_to_the_key_the_device_reported() -> None:
    """A BLE-only device has no device list to seed from, so it reports its own.

    The reducer stores it from net.toapp_wifi_iot_status; this is the path that
    carries it through to the command builder.
    """
    device = MowerDevice(name="Luba-Test")
    device.mower_state.product_key = "a1ZU6bdGjaM"
    handle = DeviceHandle(device_id="dev-ble", device_name="Luba-Test", initial_device=device)

    assert handle.product_key == ""  # nothing seeded it
    assert handle.commands.get_device_product_key() == "a1ZU6bdGjaM"
