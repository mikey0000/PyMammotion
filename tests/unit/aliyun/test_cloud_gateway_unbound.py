"""Removing a device from the cached Aliyun listing when it unbinds (29004).

``to_cache`` persists that listing and a restore re-registers an Aliyun binding for
every device in it, so a device left behind is re-bound on every restart and gets
29004 again — forever.
"""

from __future__ import annotations

import pytest

from tests.unit.aliyun._helpers import make_gateway, make_listing_device, seed_listing


@pytest.mark.regression
def test_forget_device_drops_the_unbound_device_by_iot_id() -> None:
    """29004 carries the iot_id, so that is what the removal has to match on."""
    gateway = make_gateway()
    seed_listing(gateway, make_listing_device("Luba-GONE", "iot-gone"), make_listing_device("Luba-KEEP", "iot-keep"))

    assert gateway.forget_device(iot_id="iot-gone") is True

    remaining = gateway.devices_by_account_response.data
    assert [d.device_name for d in remaining.data] == ["Luba-KEEP"]
    assert remaining.total == 1


@pytest.mark.regression
def test_forget_device_drops_the_unbound_device_by_name() -> None:
    """A handle whose iot_id was never populated must still be removable."""
    gateway = make_gateway()
    seed_listing(gateway, make_listing_device("Luba-GONE", "iot-gone"), make_listing_device("Luba-KEEP", "iot-keep"))

    assert gateway.forget_device(device_name="Luba-GONE") is True

    assert [d.device_name for d in gateway.devices_by_account_response.data.data] == ["Luba-KEEP"]


def test_forget_device_reports_false_when_nothing_matched() -> None:
    """The caller persists the cache only on a real change, so this must not lie."""
    gateway = make_gateway()
    seed_listing(gateway, make_listing_device("Luba-KEEP", "iot-keep"))

    assert gateway.forget_device(iot_id="iot-unknown") is False
    assert gateway.forget_device(device_name="Luba-UNKNOWN") is False
    assert len(gateway.devices_by_account_response.data.data) == 1


def test_forget_device_is_safe_with_no_listing_cached() -> None:
    """A gateway restored without device_data must not blow up on a 29004."""
    gateway = make_gateway()
    assert gateway.devices_by_account_response is None
    assert gateway.forget_device(iot_id="iot-gone") is False


def test_forget_device_is_safe_when_the_listing_carries_no_data() -> None:
    """Aliyun answers with data=None on an empty account, and that is cacheable."""
    from pymammotion.aliyun.model.dev_by_account_response import ListingDevAccountResponse

    gateway = make_gateway()
    gateway._devices_by_account_response = ListingDevAccountResponse(code=200, data=None)  # noqa: SLF001

    assert gateway.forget_device(iot_id="iot-gone") is False


@pytest.mark.regression
def test_the_removal_reaches_the_persisted_cache() -> None:
    """to_cache is what a restart reads, so the trimmed listing has to reach it."""
    gateway = make_gateway()
    seed_listing(gateway, make_listing_device("Luba-GONE", "iot-gone"), make_listing_device("Luba-KEEP", "iot-keep"))

    gateway.forget_device(iot_id="iot-gone")

    cached = gateway.to_cache()["device_data"]
    assert [d.device_name for d in cached.data.data] == ["Luba-KEEP"]
