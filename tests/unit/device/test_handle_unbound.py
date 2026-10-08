"""DeviceHandle on Aliyun 29004 (device unbound): detach without disconnecting, migrate, re-route the send."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pymammotion.aliyun.exceptions import DeviceUnboundException
from pymammotion.state.device_state import TransportAvailability
from pymammotion.transport.base import TransportType
from tests._helpers import make_mock_handle, make_mock_transport


async def test_detach_transport_pops_without_disconnect() -> None:
    """detach_transport removes the transport from the handle WITHOUT disconnecting it.

    The Aliyun transport is account-shared; disconnecting it would kill cloud for
    every other device on the account.  Idempotent: a second call returns None.
    """
    handle = make_mock_handle("dev1", "Mower One")
    aliyun = make_mock_transport(TransportType.CLOUD_ALIYUN, connected=True)
    await handle.add_transport(aliyun)

    removed = handle.detach_transport(TransportType.CLOUD_ALIYUN)

    assert removed is aliyun
    assert handle.get_transport(TransportType.CLOUD_ALIYUN) is None
    aliyun.disconnect.assert_not_awaited()
    # Idempotent — already gone.
    assert handle.detach_transport(TransportType.CLOUD_ALIYUN) is None


async def test_device_unbound_detaches_aliyun_and_schedules_hook() -> None:
    """A 29004 detaches the Aliyun transport (not disconnect) and fires the unbound hook once.

    No BLE present → send_raw re-raises the DeviceUnboundException; the
    permanent detach must NOT set mqtt_reported_offline.
    """
    handle = make_mock_handle("dev1", "Mower One")
    aliyun = make_mock_transport(TransportType.CLOUD_ALIYUN, connected=True)
    await handle.add_transport(aliyun)
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)
    hook = AsyncMock()
    handle.on_device_unbound = hook

    handle._send_marked = AsyncMock(  # type: ignore[method-assign]
        side_effect=DeviceUnboundException(29004, "iot-id")
    )

    with pytest.raises(DeviceUnboundException):
        await handle.send_raw(b"\x01")
    await asyncio.sleep(0)  # let the fire-and-forget hook task run

    assert handle.get_transport(TransportType.CLOUD_ALIYUN) is None
    aliyun.disconnect.assert_not_awaited()
    hook.assert_awaited_once_with(handle)
    assert handle.availability.mqtt_reported_offline is False
    await handle.stop()


async def test_device_unbound_retries_over_ble() -> None:
    """A 29004 (always from Aliyun) detaches Aliyun and the command retries over BLE.

    BLE starts disconnected so Aliyun is chosen first; it comes online for the retry
    (mirrors the device-offline fallback test).
    """
    handle = make_mock_handle("dev1", "Mower One")
    aliyun = make_mock_transport(TransportType.CLOUD_ALIYUN, connected=True)
    ble = make_mock_transport(TransportType.BLE, connected=False)  # not connected → Aliyun chosen
    await handle.add_transport(aliyun)
    await handle.add_transport(ble)
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)
    handle.on_device_unbound = AsyncMock()

    call_count = 0

    async def _side_effect(
        transport: object, payload: bytes, *, user_initiated: bool = False
    ) -> None:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            ble.is_connected = True  # BLE comes online between Aliyun failure and retry
            raise DeviceUnboundException(29004, "iot-id")
        # second call (BLE) succeeds

    handle._send_marked = AsyncMock(side_effect=_side_effect)  # type: ignore[method-assign]

    await handle.send_raw(b"\x01")

    assert handle._send_marked.call_count == 2
    assert handle._send_marked.await_args_list[1].args[0] is ble
    assert handle.get_transport(TransportType.CLOUD_ALIYUN) is None
    await handle.stop()


@pytest.mark.regression
async def test_device_unbound_retries_over_the_remaining_cloud_transport() -> None:
    """A 29004 on Aliyun retries on the Mammotion MQTT transport the handle still has.

    The fallback only ever considered BLE, so a migrated device holding both cloud
    transports failed the user's command even though Mammotion MQTT was connected.
    """
    handle = make_mock_handle("dev1", "Mower One")
    aliyun = make_mock_transport(TransportType.CLOUD_ALIYUN, connected=True)
    mammotion = make_mock_transport(TransportType.CLOUD_MAMMOTION, connected=True)
    await handle.add_transport(aliyun)
    await handle.add_transport(mammotion)
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)
    handle.update_availability(TransportType.CLOUD_MAMMOTION, TransportAvailability.CONNECTED)
    handle.on_device_unbound = AsyncMock()

    async def _side_effect(transport: object, payload: bytes, *, user_initiated: bool = False) -> None:  # noqa: ARG001
        if transport is aliyun:
            raise DeviceUnboundException(29004, "iot-id")

    handle._send_marked = AsyncMock(side_effect=_side_effect)  # type: ignore[method-assign]

    await handle.send_raw(b"\x01", user_initiated=True)

    assert [c.args[0] for c in handle._send_marked.await_args_list] == [aliyun, mammotion]
    assert handle._send_marked.await_args_list[1].kwargs["user_initiated"] is True
    assert handle.get_transport(TransportType.CLOUD_ALIYUN) is None
    await handle.stop()


async def test_device_unbound_hook_fires_only_once() -> None:
    """A second _on_device_unbound (transport already detached) must not re-fire the hook."""
    handle = make_mock_handle("dev1", "Mower One")
    aliyun = make_mock_transport(TransportType.CLOUD_ALIYUN, connected=True)
    await handle.add_transport(aliyun)
    handle.update_availability(TransportType.CLOUD_ALIYUN, TransportAvailability.CONNECTED)
    hook = AsyncMock()
    handle.on_device_unbound = hook

    await handle._on_device_unbound(aliyun)  # noqa: SLF001
    await handle._on_device_unbound(aliyun)  # noqa: SLF001 — already detached
    await asyncio.sleep(0)

    hook.assert_awaited_once_with(handle)
