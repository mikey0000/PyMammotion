"""Forgetting a device's Aliyun binding when the cloud says it is unbound (29004).

The client half of the fix: the gateway owns the listing, but ``_on_device_unbound``
is what has to reach for it, and the host has to be told to rewrite the cache —
otherwise the trim lives in memory and dies at shutdown.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import DeviceUnboundException
from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import TransportAvailability, TransportType
from tests._helpers import (
    make_bare_client,
    make_device_record,
    make_mock_handle,
    make_mock_http,
    make_mock_transport,
)
from tests.unit.aliyun._helpers import make_gateway, make_listing_device, seed_listing

ACCOUNT = "user@test.com"
UNBIND = DeviceUnboundException(29004, "iot-gone")


def make_client_with_listing(
    *device_names_and_ids: tuple[str, str],
) -> tuple[MammotionClient, DeviceHandle, AsyncMock]:
    """A client whose single account lists the given devices, plus a persist spy."""
    gateway = make_gateway()
    seed_listing(gateway, *(make_listing_device(name, iot_id) for name, iot_id in device_names_and_ids))
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.cloud_client = gateway
    client = make_bare_client(session)

    persist = AsyncMock()
    client.on_credentials_updated = persist

    handle = make_mock_handle("dev-gone", "Luba-GONE")
    handle.account_id = ACCOUNT
    handle.iot_id = "iot-gone"
    return client, handle, persist


def listing_of(client: MammotionClient, handle: DeviceHandle) -> list[str]:
    """Device names currently in the handle's account listing."""
    gateway: CloudIOTGateway = client._get_session_for_handle(handle).cloud_client  # noqa: SLF001
    return [d.device_name for d in gateway.devices_by_account_response.data.data]


@pytest.mark.regression
async def test_an_unbind_removes_the_device_from_the_listing_and_persists_it() -> None:
    """Without this the restore re-registers the device and it 29004s again, every boot.

    Driven through ``_on_device_unbound`` — the real 29004 entry point — so that
    deleting the call, not just the removal itself, fails this.
    """
    client, handle, persist = make_client_with_listing(("Luba-GONE", "iot-gone"), ("Luba-KEEP", "iot-keep"))

    # Settle migration at once; the real loop sleeps 30/60/120/180s between attempts.
    with patch.object(MammotionClient, "_try_migrate_unbound", autospec=True) as migrate:
        migrate.return_value = True
        await client._on_device_unbound(handle, UNBIND)  # noqa: SLF001

    assert listing_of(client, handle) == ["Luba-KEEP"]
    persist.assert_awaited_once()  # the trim only survives once the host rewrites the cache


@pytest.mark.regression
async def test_the_device_is_forgotten_before_migration_is_attempted() -> None:
    """Ordering matters: migration retries run for minutes and can be interrupted.

    If the trim happened after they settled, a restart during those minutes would
    still restore the stale binding — the very loop this fix exists to break.
    """
    client, handle, _ = make_client_with_listing(("Luba-GONE", "iot-gone"), ("Luba-KEEP", "iot-keep"))
    listing_when_migration_ran: list[list[str]] = []

    def _record(_self: MammotionClient, _handle: DeviceHandle, _session: object, *, final_attempt: bool) -> bool:
        listing_when_migration_ran.append(listing_of(client, handle))
        return True

    with patch.object(MammotionClient, "_try_migrate_unbound", autospec=True, side_effect=_record):
        await client._on_device_unbound(handle, UNBIND)  # noqa: SLF001

    assert listing_when_migration_ran == [["Luba-KEEP"]], "migration ran before the listing was trimmed"


@pytest.mark.regression
async def test_the_device_is_forgotten_even_when_it_migrates_to_mammotion_mqtt() -> None:
    """Migrating off Aliyun still means it is unbound *from Aliyun*.

    Leaving it listed would have the restore rebuild an Aliyun binding alongside the
    Mammotion one it now legitimately has.
    """
    client, handle, _ = make_client_with_listing(("Luba-GONE", "iot-gone"))

    with patch.object(MammotionClient, "_try_migrate_unbound", autospec=True) as migrate:
        migrate.return_value = True
        await client._on_device_unbound(handle, UNBIND)  # noqa: SLF001

    assert listing_of(client, handle) == []


async def test_an_unbind_for_an_unlisted_device_does_not_rewrite_the_cache() -> None:
    """A repeat 29004 must not spam the host with credential writes."""
    client, handle, persist = make_client_with_listing(("Luba-KEEP", "iot-keep"))

    await client._forget_aliyun_binding(handle, client._get_session_for_handle(handle))  # noqa: SLF001

    persist.assert_not_awaited()


async def test_an_unbind_without_a_persist_callback_still_trims_the_listing() -> None:
    """A 29004 can land before the host has registered one; the trim must still happen."""
    client, handle, _ = make_client_with_listing(("Luba-GONE", "iot-gone"), ("Luba-KEEP", "iot-keep"))
    client.on_credentials_updated = None

    await client._forget_aliyun_binding(handle, client._get_session_for_handle(handle))  # noqa: SLF001

    assert listing_of(client, handle) == ["Luba-KEEP"]


async def test_a_failing_persist_callback_does_not_break_the_unbind() -> None:
    """The host's storage failing is not a reason to abandon the migration that follows."""
    client, handle, _ = make_client_with_listing(("Luba-GONE", "iot-gone"), ("Luba-KEEP", "iot-keep"))
    client.on_credentials_updated = AsyncMock(side_effect=OSError("disk full"))

    await client._forget_aliyun_binding(handle, client._get_session_for_handle(handle))  # noqa: SLF001

    assert listing_of(client, handle) == ["Luba-KEEP"]


async def test_an_unbind_on_a_device_with_no_cloud_session_is_a_no_op() -> None:
    """A BLE-only handle has no account, and a Mammotion-only account has no gateway.

    Neither has an Aliyun listing to trim, and a 29004 reaching here must not raise
    into the migration that follows it.
    """
    client, handle, persist = make_client_with_listing(("Luba-GONE", "iot-gone"))

    await client._forget_aliyun_binding(handle, None)  # noqa: SLF001 — BLE-only: no session

    session = client._get_session_for_handle(handle)  # noqa: SLF001
    session.cloud_client = None  # Mammotion-only account: session, but no Aliyun gateway
    await client._forget_aliyun_binding(handle, session)  # noqa: SLF001

    persist.assert_not_awaited()


@pytest.mark.regression
async def test_a_successful_migration_persists_the_cache() -> None:
    """The device page fetched during migration is what stops the next restore re-binding to Aliyun.

    Without a write here it lived only in memory, so every restart bound the device to
    Aliyun again and its first send 29004'd.
    """
    client, handle, persist = make_client_with_listing(("Luba-KEEP", "iot-keep"))
    session = client._get_session_for_handle(handle)  # noqa: SLF001
    session.mammotion_http = make_mock_http(device_records=[make_device_record("Luba-GONE", "iot-gone")])

    with (
        patch.object(MammotionClient, "_ensure_mammotion_transport", autospec=True, return_value=AsyncMock()),
        patch.object(MammotionClient, "_ensure_device_handle", autospec=True),
    ):
        settled = await client._try_migrate_unbound(handle, session, final_attempt=False)  # noqa: SLF001

    assert settled is True
    persist.assert_awaited_once()


async def test_device_unbound_migrates_to_mammotion() -> None:
    """When an unbound device now appears on Mammotion MQTT, attach that transport to the
    SAME handle (no new handle), remap the iot_id, and never disconnect the shared Aliyun.
    """
    client = MammotionClient()
    handle = make_mock_handle("Luba-MIG", "Luba-MIG")
    handle.iot_id = "iot-old"
    await client._device_registry.register(handle, "user@test.com")
    client._inbound.bind("user@test.com", "iot-old", ("user@test.com", "Luba-MIG"))

    record = make_device_record(device_name="Luba-MIG", iot_id="iot-new", product_key="pkNEW")
    http = make_mock_http(device_records=[record])
    http.get_user_device_list = AsyncMock(
        return_value=MagicMock(data=[MagicMock(device_name="Luba-MIG", iot_id="iot-new")])
    )
    session = AccountSession(account_id="user@test.com", email="user@test.com", password="pw")
    session.mammotion_http = http
    session.aliyun_transport = make_mock_transport(
        TransportType.CLOUD_ALIYUN, availability=TransportAvailability.UNKNOWN
    )
    session.device_ids.add("Luba-MIG")
    await client._account_registry.register(session)

    mammotion_transport = make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    mammotion_transport.add_topic = AsyncMock()
    # The transport owns the topic layout now (MQTTTransport.subscribe_device); the
    # client only decides *when* a device gets subscribed.
    mammotion_transport.subscribe_device = AsyncMock()

    with patch.object(client, "_ensure_mammotion_transport", AsyncMock(return_value=mammotion_transport)):
        await client._on_device_unbound(handle, DeviceUnboundException(29004, handle.iot_id))

    # Same handle reused; Mammotion attached; iot_id remapped; shared Aliyun untouched.
    assert client._device_registry.get_by_name("Luba-MIG") is handle
    assert handle.get_transport(TransportType.CLOUD_MAMMOTION) is mammotion_transport
    assert handle.iot_id == "iot-new"
    # Asserted through the router: what matters is that a frame for the new iot_id
    # reaches this handle, and one for the old id no longer reaches anything.
    assert client._inbound.handle_for("user@test.com", "iot-new", "test") is handle
    assert client._inbound.handle_for("user@test.com", "iot-old", "test") is None
    mammotion_transport.subscribe_device.assert_awaited_once_with("pkNEW", "Luba-MIG", "iot-new")
    session.aliyun_transport.disconnect.assert_not_awaited()
    await handle.stop()


async def test_device_unbound_removed_when_on_no_cloud() -> None:
    """When the unbound device is on neither cloud, remove it entirely and fire on_device_removed.

    The account-shared Aliyun transport must NOT be disconnected (other devices use it).
    """
    client = MammotionClient()
    handle = make_mock_handle("Luba-GONE", "Luba-GONE")
    handle.iot_id = "iot-gone"
    await client._device_registry.register(handle, "user@test.com")
    client._inbound.bind("user@test.com", "iot-gone", ("user@test.com", "Luba-GONE"))

    http = make_mock_http(device_records=[])  # not present on Mammotion either
    session = AccountSession(account_id="user@test.com", email="user@test.com", password="pw")
    session.mammotion_http = http
    session.aliyun_transport = make_mock_transport(
        TransportType.CLOUD_ALIYUN, availability=TransportAvailability.UNKNOWN
    )
    session.device_ids.add("Luba-GONE")
    await client._account_registry.register(session)

    removed = AsyncMock()
    client.on_device_removed = removed

    # Collapse the multi-minute migration retry backoff so the test runs instantly.
    with patch("pymammotion.client._UNBOUND_MIGRATION_DELAYS", (0.0, 0.0)):
        await client._on_device_unbound(handle, DeviceUnboundException(29004, handle.iot_id))

    assert client._device_registry.get_by_name("Luba-GONE") is None
    assert client._inbound.handle_for("user@test.com", "iot-gone", "test") is None
    assert "Luba-GONE" not in session.device_ids
    removed.assert_awaited_once_with("Luba-GONE", "iot-gone")
    session.aliyun_transport.disconnect.assert_not_awaited()
