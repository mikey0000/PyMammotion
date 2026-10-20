"""A device removed from the account (Mammotion 50101) is dropped from the client and the cache."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.aliyun.exceptions import DeviceRemovedFromAccountError
from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import TransportAvailability, TransportType
from tests._helpers import make_device_record, make_mock_handle, make_mock_http, make_mock_transport, wait_until

ACCOUNT = "user@test.com"
#: Far below the 30 s the Aliyun 29004 path sleeps before its second attempt.
WAIT_TIMEOUT = 1.0


@pytest.fixture
async def handles() -> AsyncIterator[list[DeviceHandle]]:
    """Collects the handles a test builds and stops them however the test ends."""
    created: list[DeviceHandle] = []
    yield created
    for handle in created:
        await handle.stop()


async def _mammotion_handle(handles: list[DeviceHandle], device_name: str) -> DeviceHandle:
    handle = make_mock_handle(device_name, device_name)
    handle.iot_id = f"iot-{device_name}"
    await handle.add_transport(
        make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    )
    handles.append(handle)
    return handle


async def _client_with_mammotion_device(
    handles: list[DeviceHandle], device_name: str, *, listed: list[str]
) -> tuple[MammotionClient, DeviceHandle, AccountSession, MagicMock]:
    """A client whose account holds *device_name* on Mammotion MQTT; the device page lists *listed*."""
    client = MammotionClient()
    handle = await _mammotion_handle(handles, device_name)
    await client._device_registry.register(handle, ACCOUNT)  # noqa: SLF001

    http = make_mock_http(device_records=[make_device_record(name, f"iot-{name}") for name in listed])
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.mammotion_http = http
    session.device_ids.add(device_name)
    await client._account_registry.register(session)  # noqa: SLF001
    return client, handle, session, http


async def test_a_device_removed_from_the_account_is_dropped_and_the_cache_rewritten(
    handles: list[DeviceHandle],
) -> None:
    """One device-list check settles a 50101: no multi-minute migration retries."""
    client, handle, session, _ = await _client_with_mammotion_device(handles, "Luba-GONE", listed=["Luba-KEEP"])
    removed = AsyncMock()
    persist = AsyncMock()
    client.on_device_removed = removed
    client.on_credentials_updated = persist

    await asyncio.wait_for(
        client._on_device_unbound(handle, DeviceRemovedFromAccountError(50101, "iot-Luba-GONE")),  # noqa: SLF001
        timeout=WAIT_TIMEOUT,
    )

    assert client._device_registry.get_by_name("Luba-GONE") is None  # noqa: SLF001
    assert "Luba-GONE" not in session.device_ids
    removed.assert_awaited_once_with("Luba-GONE", "iot-Luba-GONE")
    persist.assert_awaited()  # the refreshed device page only survives a restart once written


async def test_a_send_rejected_with_50101_removes_the_device(handles: list[DeviceHandle]) -> None:
    """End to end from the send: the handle hands the subclass to the client, which removes the device."""
    client, handle, _, _ = await _client_with_mammotion_device(handles, "Luba-GONE", listed=[])
    handle.on_device_unbound = client._on_device_unbound  # noqa: SLF001
    removed = AsyncMock()
    client.on_device_removed = removed
    handle._send_marked = AsyncMock(side_effect=DeviceRemovedFromAccountError(50101, "iot-Luba-GONE"))  # type: ignore[method-assign]  # noqa: SLF001

    with pytest.raises(DeviceRemovedFromAccountError):
        await handle.send_raw(b"\x01", user_initiated=True)
    await wait_until(lambda: removed.await_count, timeout=WAIT_TIMEOUT)

    removed.assert_awaited_once_with("Luba-GONE", "iot-Luba-GONE")


async def test_a_50101_for_a_device_still_listed_keeps_it(handles: list[DeviceHandle]) -> None:
    """The listing is the authority: a device it still shows is re-attached, never removed."""
    client, handle, _, _ = await _client_with_mammotion_device(handles, "Luba-KEEP", listed=["Luba-KEEP"])
    removed = AsyncMock()
    client.on_device_removed = removed
    reattach = AsyncMock()
    mammotion = make_mock_transport(TransportType.CLOUD_MAMMOTION, subscribe_device=AsyncMock())
    client._ensure_mammotion_transport = AsyncMock(return_value=mammotion)  # type: ignore[method-assign]  # noqa: SLF001
    client._ensure_device_handle = reattach  # type: ignore[method-assign]  # noqa: SLF001

    await client._on_device_unbound(handle, DeviceRemovedFromAccountError(50101, "iot-Luba-KEEP"))  # noqa: SLF001

    removed.assert_not_awaited()
    reattach.assert_awaited_once()


@pytest.mark.regression
async def test_an_unavailable_device_list_does_not_remove_the_device(handles: list[DeviceHandle]) -> None:
    """A failed device-page fetch is not proof the device left the account.

    The fetch returns a response with no data on a non-200; that was read as an empty
    listing, so a final migration attempt removed the device from the host.
    """
    client, handle, session, http = await _client_with_mammotion_device(handles, "Luba-KEEP", listed=[])
    http.get_user_device_page = AsyncMock(return_value=MagicMock(code=500, data=None))
    removed = AsyncMock()
    client.on_device_removed = removed

    settled = await client._try_migrate_unbound(handle, session, final_attempt=True)  # noqa: SLF001

    assert settled is False
    assert client._device_registry.get_by_name("Luba-KEEP") is handle  # noqa: SLF001
    removed.assert_not_awaited()


async def test_a_reload_drops_mammotion_devices_the_account_no_longer_lists(handles: list[DeviceHandle]) -> None:
    """A restore registers from the cached page; the fresh page must prune what has gone."""
    client, gone, session, http = await _client_with_mammotion_device(handles, "Luba-GONE", listed=["Luba-KEEP"])
    kept = await _mammotion_handle(handles, "Luba-KEEP")
    await client._device_registry.register(kept, ACCOUNT)  # noqa: SLF001
    session.device_ids.add("Luba-KEEP")
    session.mammotion_transport = make_mock_transport(TransportType.CLOUD_MAMMOTION)
    removed = AsyncMock()
    client.on_device_removed = removed

    await client._bootstrap_mammotion_mqtt(ACCOUNT, http, session, {}, skip_ids=set(session.device_ids))  # noqa: SLF001

    assert client._device_registry.get_by_name("Luba-GONE") is None  # noqa: SLF001
    assert client._device_registry.get_by_name("Luba-KEEP") is kept  # noqa: SLF001
    removed.assert_awaited_once_with("Luba-GONE", gone.iot_id)


async def test_a_reload_with_an_unavailable_device_list_drops_nothing(handles: list[DeviceHandle]) -> None:
    """A failed fetch must not read as an empty account and prune every device."""
    client, handle, _, http = await _client_with_mammotion_device(handles, "Luba-KEEP", listed=[])
    http.get_user_device_page = AsyncMock(return_value=MagicMock(code=500, data=None))
    session = client._account_registry.get(ACCOUNT)  # noqa: SLF001

    await client._bootstrap_mammotion_mqtt(ACCOUNT, http, session, {}, skip_ids=set(session.device_ids))  # noqa: SLF001

    assert client._device_registry.get_by_name("Luba-KEEP") is handle  # noqa: SLF001


async def test_a_reload_leaves_aliyun_devices_to_the_aliyun_listing(handles: list[DeviceHandle]) -> None:
    """The Mammotion page does not list Aliyun-bound devices, so its absence there proves nothing."""
    client, handle, session, http = await _client_with_mammotion_device(handles, "Luba-ALI", listed=[])
    await handle.add_transport(
        make_mock_transport(TransportType.CLOUD_ALIYUN, availability=TransportAvailability.UNKNOWN)
    )

    await client._bootstrap_mammotion_mqtt(ACCOUNT, http, session, {}, skip_ids=set(session.device_ids))  # noqa: SLF001

    assert client._device_registry.get_by_name("Luba-ALI") is handle  # noqa: SLF001


async def test_a_reload_keeps_an_unlisted_device_that_still_has_bluetooth(handles: list[DeviceHandle]) -> None:
    """Bluetooth needs no account, so a removed mower the user paired over BLE keeps working."""
    client, handle, session, http = await _client_with_mammotion_device(handles, "Luba-BLE", listed=[])
    await handle.add_transport(make_mock_transport(TransportType.BLE, connected=False))
    removed = AsyncMock()
    client.on_device_removed = removed

    await client._bootstrap_mammotion_mqtt(ACCOUNT, http, session, {}, skip_ids=set(session.device_ids))  # noqa: SLF001

    assert client._device_registry.get_by_name("Luba-BLE") is handle  # noqa: SLF001
    assert handle.get_transport(TransportType.CLOUD_MAMMOTION) is None
    assert "Luba-BLE" not in session.device_ids
    removed.assert_not_awaited()
