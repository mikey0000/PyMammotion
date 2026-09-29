"""``DeviceType.CM900``: name and product-key resolution.

Its row of capability helpers lives in ``test_device_type_helper_matrix.py``.
"""

import pytest

from pymammotion.utility.device_type import DeviceType


@pytest.mark.regression
def test_a_kumar_mk_name_resolves_to_cm900() -> None:
    """The CM900 prefix is eight characters, and it was matched against the first seven.

    ``"Kumar-MK" in name[:7]`` can never hold, so every CM900 resolved to UNKNOWN and fell
    out of every gate that lists it — including ``is_luba_pro``, which routes NAV commands
    to the navigation board.  The APK compares ``str.substring(0, 8)`` for CM900 alone
    (``DeviceType.valueOfStrByDeviceName``).
    """
    assert DeviceType.value_of_str("Kumar-MK6ABCDE") is DeviceType.CM900


@pytest.mark.parametrize("device_name", ["Kumar-10ABCDE", "Kumar-M", "XKumar-MK6ABCD"])
def test_only_a_leading_kumar_mk_is_a_cm900(device_name: str) -> None:
    """Kumar-10 is another product, and the APK looks only at the first eight characters."""
    assert DeviceType.value_of_str(device_name) is not DeviceType.CM900


@pytest.mark.regression
@pytest.mark.parametrize("product_key", ["zkRuTK9KsXG", "6DbgVh2Qs5m", "a1tyIkI4q0G", "1SCa3mAX6G"])
def test_a_cm900_product_key_resolves_to_cm900(product_key: str) -> None:
    """The APK's ``valueOfStr(name, productKey)`` returns CM900 for ``DeviceProductKey.Cm900ProductKey``.

    No rule consulted that list, and ``1SCa3mAX6G`` was missing from it, so a CM900 known
    only by its product key resolved to UNKNOWN.
    """
    assert DeviceType.value_of_str("", product_key) is DeviceType.CM900
