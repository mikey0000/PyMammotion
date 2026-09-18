"""Forgetting a device's Aliyun binding when the cloud says it is unbound (29004).

The client half of the fix: the gateway owns the listing, but ``_on_device_unbound``
is what has to reach for it, and the host has to be told to rewrite the cache —
otherwise the trim lives in memory and dies at shutdown.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from tests._helpers import make_bare_client, make_mock_handle
from tests.unit.aliyun._helpers import make_gateway, make_listing_device, seed_listing

ACCOUNT = "user@test.com"


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
        await client._on_device_unbound(handle)  # noqa: SLF001

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
        await client._on_device_unbound(handle)  # noqa: SLF001

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
        await client._on_device_unbound(handle)  # noqa: SLF001

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
