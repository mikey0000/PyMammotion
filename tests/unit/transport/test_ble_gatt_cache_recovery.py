"""connect() recovering from a cached GATT table the device has moved on from.

Split out of ``test_ble.py``: this is one concern with two distinct failure shapes
— a characteristic bleak cannot find at all, and one the cached table still lists
at a handle the device dropped (issue #193) — and it owns the only tests that care
how far a cache purge actually travels.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from bleak import BLEDevice
import pytest

from pymammotion.transport.base import TransportAvailability
from pymammotion.transport.ble import BLETransport, BLETransportConfig
from tests.unit.transport._fakes import make_ble_device, make_fake_ble_client
from tests.unit.transport._fakes import make_fake_ble_message


@pytest.fixture
def config() -> BLETransportConfig:
    return BLETransportConfig(device_id="test-device-001", ble_address="AA:BB:CC:DD:EE:FF")


# connect() recovers from a stale GATT service cache instead of looping on cooldown


def _not_found() -> Exception:
    from bleak.exc import BleakCharacteristicNotFoundError

    return BleakCharacteristicNotFoundError("0000ff02-0000-1000-8000-00805f9b34fb")


async def test_connect_clears_stale_service_cache_and_reconnects_once(config: BLETransportConfig) -> None:
    """The reported Yuka loop: link up, ff02 missing, cooldown, repeat until restart.

    The first miss must clear bleak's service cache and reconnect immediately; the
    reconnect (with a fresh GATT table) succeeds and no cooldown is armed.
    """
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    stale_client = make_fake_ble_client()
    stale_client.start_notify = AsyncMock(side_effect=_not_found())
    fresh_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()
    establish = AsyncMock(side_effect=[stale_client, fresh_client])

    with (
        patch("pymammotion.transport.ble.establish_connection", new=establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()

    stale_client.clear_cache.assert_awaited_once()
    stale_client.disconnect.assert_awaited_once()
    assert establish.await_count == 2
    fresh_client.start_notify.assert_awaited_once()
    assert transport.is_connected is True
    assert transport.availability is TransportAvailability.CONNECTED
    assert transport.is_usable  # no cooldown was armed by the cache miss


async def test_connect_counts_a_second_missing_characteristic_as_a_real_failure(
    config: BLETransportConfig,
) -> None:
    from pymammotion.transport.base import BLEUnavailableError

    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    first, second = make_fake_ble_client(), make_fake_ble_client()
    first.start_notify = AsyncMock(side_effect=_not_found())
    second.start_notify = AsyncMock(side_effect=_not_found())
    establish = AsyncMock(side_effect=[first, second])

    with (
        patch("pymammotion.transport.ble.establish_connection", new=establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
        pytest.raises(BLEUnavailableError),
    ):
        await transport.connect()

    first.clear_cache.assert_awaited_once()
    second.clear_cache.assert_not_awaited()  # one cache retry, then it is a failure
    assert establish.await_count == 2
    assert transport.is_connected is False
    assert transport.is_usable  # one failure is below the threshold — BLE gets another go

    # The failure still counts: reaching the threshold arms the cooldown.
    third = make_fake_ble_client()
    third.start_notify = AsyncMock(side_effect=_not_found())
    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=third)),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
        pytest.raises(BLEUnavailableError),
    ):
        await transport.connect()

    assert not transport.is_usable


async def test_connect_does_not_clear_cache_for_unrelated_setup_errors(config: BLETransportConfig) -> None:
    from bleak.exc import BleakError

    from pymammotion.transport.base import BLEUnavailableError

    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))
    client = make_fake_ble_client()
    client.start_notify = AsyncMock(side_effect=BleakError("GATT Error: Unlikely error"))
    establish = AsyncMock(return_value=client)

    with (
        patch("pymammotion.transport.ble.establish_connection", new=establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
        pytest.raises(BLEUnavailableError),
    ):
        await transport.connect()

    client.clear_cache.assert_not_awaited()
    assert establish.await_count == 1


# connect() recovers from a GATT table the device moved under the proxy (issue #193)


def _esphome_gatt_error(handle: int, code: int) -> Exception:
    """Return the exception bleak_esphome actually raises for a GATT status.

    ``api_error_as_bleak_error`` flattens every ``BluetoothGATTAPIError`` into a
    plain ``BleakError(str(exc)) from exc`` (bleak_esphome/backend/client.py), so
    the numeric status only survives on ``__cause__``.  The real aioesphomeapi
    class is used rather than a stand-in precisely because the production
    predicate duck-types that shape and must track it.
    """
    from aioesphomeapi.core import BluetoothGATTAPIError
    from aioesphomeapi.model import BluetoothGATTError
    from bleak.exc import BleakError

    api_error = BluetoothGATTAPIError(BluetoothGATTError(address=0xCC641A112233, handle=handle, error=code))
    try:
        raise BleakError(str(api_error)) from api_error
    except BleakError as exc:
        return exc


def _dead_link_clear_cache() -> AsyncMock:
    """clear_cache() on a link the proxy already dropped.

    ``BleakClientESPHome.clear_cache`` clears HA's in-memory copy, then calls
    ``_raise_if_not_connected()`` *before* it reaches the proxy's flash-backed
    copy — so on a dead link the proxy keeps the stale table.
    """
    from bleak.exc import BleakError

    return AsyncMock(side_effect=BleakError("ESPHome proxy is not connected"))


@pytest.mark.regression
async def test_connect_recovers_when_the_device_moved_its_gatt_handles(config: BLETransportConfig) -> None:
    """Issue #193: the Yuka re-registers its service at a new handle block.

    The cached table still lists ff02, so nothing is "not found" — the CCCD write
    lands on a handle the mower dropped and the proxy answers ``error=1 Invalid
    handle``, then drops the link.  The code treated that as an ordinary setup
    failure: no cache clear, no retry, straight to cooldown, and every later
    attempt repeated it because the proxy's flash-backed table never changed.

    Recovery has to purge the proxy's copy, and that call only reaches the proxy
    over a live link — so it must run on the *next* connection, not on the corpse
    of the one that just failed.
    """
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    # What stands in for the link the proxy dropped is clear_cache() refusing — that
    # refusal, not is_connected, is what production has to route around.
    moved = make_fake_ble_client()
    moved.start_notify = AsyncMock(side_effect=_esphome_gatt_error(handle=31, code=1))
    moved.clear_cache = _dead_link_clear_cache()

    purge = make_fake_ble_client()
    healthy = make_fake_ble_client()
    establish = AsyncMock(side_effect=[moved, purge, healthy])

    with (
        patch("pymammotion.transport.ble.establish_connection", new=establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
    ):
        await transport.connect()

    # The purge ran against a live link — this is what the dead-link attempt could not do.
    purge.clear_cache.assert_awaited_once()
    purge.disconnect.assert_awaited_once()
    purge.start_notify.assert_not_awaited()  # nothing is set up on the purge pass
    assert establish.await_count == 3
    healthy.start_notify.assert_awaited_once()
    assert transport.is_connected is True
    assert transport.availability is TransportAvailability.CONNECTED
    assert transport.is_usable  # the recovery must not arm a cooldown


@pytest.mark.regression
async def test_connect_skips_the_extra_pass_when_the_link_survived_the_gatt_error(
    config: BLETransportConfig,
) -> None:
    """A link still up when the error surfaced can purge the proxy in place.

    Only the dead-link case needs a throwaway connection, so the surviving-link
    path must still recover in two attempts.
    """
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))

    stale = make_fake_ble_client()
    stale.start_notify = AsyncMock(side_effect=_esphome_gatt_error(handle=18, code=135))
    healthy = make_fake_ble_client()
    establish = AsyncMock(side_effect=[stale, healthy])

    with (
        patch("pymammotion.transport.ble.establish_connection", new=establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
    ):
        await transport.connect()

    stale.clear_cache.assert_awaited_once()
    assert establish.await_count == 2
    assert transport.is_connected is True


async def test_connect_does_not_clear_cache_for_an_unrelated_gatt_status(config: BLETransportConfig) -> None:
    """Only the codes that mean "the table we hold is wrong" trigger a purge.

    ``5 Insufficient authentication`` is a pairing problem: the handles are right
    and rediscovering them changes nothing, so it stays an ordinary failure.
    """
    from pymammotion.transport.base import BLEUnavailableError

    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))
    client = make_fake_ble_client()
    client.start_notify = AsyncMock(side_effect=_esphome_gatt_error(handle=31, code=5))
    establish = AsyncMock(return_value=client)

    with (
        patch("pymammotion.transport.ble.establish_connection", new=establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
        pytest.raises(BLEUnavailableError),
    ):
        await transport.connect()

    client.clear_cache.assert_not_awaited()
    assert establish.await_count == 1


async def test_each_pass_re_reads_the_ble_device_pointer(config: BLETransportConfig) -> None:
    """A proxy handover partway through the recovery must be picked up.

    ``establish_connection`` builds its client once from the device it is handed, and
    its ``ble_device_callback`` has been accepted-and-ignored since bleak-retry-connector
    2.13.0 — so re-reading the pointer at the top of each pass is the only thing that
    follows the mower to whichever proxy can currently hear it.
    """
    transport = BLETransport(config)
    first = make_ble_device("AA:BB:CC:DD:EE:FF")
    second = make_ble_device("11:22:33:44:55:66")
    transport.set_ble_device(first)

    stale = make_fake_ble_client()
    stale.start_notify = AsyncMock(side_effect=_esphome_gatt_error(handle=31, code=1))
    clients = [stale, make_fake_ble_client()]
    seen: list[Any] = []

    async def fake_establish(_cls: Any, device: Any, _name: Any, _callback: Any, **_kwargs: Any) -> MagicMock:
        seen.append(device)
        # Between passes HA hears the mower through a different proxy and pushes it.
        transport.set_ble_device(second)
        return clients.pop(0)

    with (
        patch("pymammotion.transport.ble.establish_connection", new=fake_establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
    ):
        await transport.connect()

    assert seen == [first, second], "the retry reused the stale BLEDevice pointer"


async def test_connect_retries_the_purge_on_a_live_link_when_the_adapter_declines(
    config: BLETransportConfig,
) -> None:
    """clear_cache() answers False rather than raising when the adapter declines it.

    Distinct from the dead-link case, which raises — both mean the table is still
    stale, so both have to buy the extra live-link pass.
    """
    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))

    declined = make_fake_ble_client()
    declined.start_notify = AsyncMock(side_effect=_esphome_gatt_error(handle=31, code=1))
    declined.clear_cache = AsyncMock(return_value=False)

    purge = make_fake_ble_client()
    healthy = make_fake_ble_client()
    establish = AsyncMock(side_effect=[declined, purge, healthy])

    with (
        patch("pymammotion.transport.ble.establish_connection", new=establish),
        patch("pymammotion.transport.ble.BleMessage", return_value=make_fake_ble_message()),
    ):
        await transport.connect()

    declined.clear_cache.assert_awaited_once()
    purge.clear_cache.assert_awaited_once()
    assert establish.await_count == 3
    assert transport.is_connected is True
