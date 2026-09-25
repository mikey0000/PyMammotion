"""``MammotionClient.check_and_get_dynamics_line`` — the APK's getDynamicsLine() gates."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowerDevice
from pymammotion.utility.constant.device_enums import WorkMode
from tests._helpers import make_mock_handle


async def _client(
    device_name: str,
    *,
    sys_status: WorkMode = WorkMode.MODE_WORKING,
    fetch_enabled: bool = True,
    firmware: str = "",
) -> MammotionClient:
    device = MowerDevice(name=device_name)
    device.report_data.dev.sys_status = sys_status.value
    device.device_firmwares.device_version = firmware
    handle = make_mock_handle("dev1", device_name, device=device)
    handle.set_mow_path_fetch_enabled(value=fetch_enabled)
    client = MammotionClient()
    await client._device_registry.register(handle)  # noqa: SLF001
    client.get_dynamics_line = AsyncMock()  # type: ignore[method-assign]
    return client


@pytest.mark.parametrize("sys_status", [WorkMode.MODE_WORKING, WorkMode.MODE_PAUSE, WorkMode.MODE_RETURNING])
async def test_fetches_on_a_dynamics_line_mower_during_a_job(sys_status: WorkMode) -> None:
    client = await _client("Luba-LA123", sys_status=sys_status)

    assert await client.check_and_get_dynamics_line("Luba-LA123")
    client.get_dynamics_line.assert_awaited_once_with("Luba-LA123")


@pytest.mark.parametrize(
    ("device_name", "sys_status", "fetch_enabled"),
    [
        pytest.param("Luba-VS563L6H", WorkMode.MODE_WORKING, True, id="cover-path-only model"),
        pytest.param("Luba-VA123", WorkMode.MODE_WORKING, True, id="LUBA_VA without firmware"),
        pytest.param("Luba-LA123", WorkMode.MODE_CHARGING, True, id="no job"),
        pytest.param("Luba-LA123", WorkMode.MODE_WORKING, False, id="cloud fetch disabled"),
    ],
)
async def test_skips_without_a_dynamics_line_to_fetch(
    device_name: str, sys_status: WorkMode, fetch_enabled: bool
) -> None:
    client = await _client(device_name, sys_status=sys_status, fetch_enabled=fetch_enabled)

    assert not await client.check_and_get_dynamics_line(device_name)
    client.get_dynamics_line.assert_not_awaited()


async def test_luba_va_qualifies_from_its_firmware() -> None:
    client = await _client("Luba-VA123", firmware="1.15.3.4422")

    assert await client.check_and_get_dynamics_line("Luba-VA123")


async def test_luba_va_ignores_the_main_controller_version() -> None:
    """The APK gates on the whole-device version, not a module's."""
    client = await _client("Luba-VA123")
    device = client.get_device_by_name("Luba-VA123")
    assert device is not None
    device.device_firmwares.main_controller = "1.15.3.4422"

    assert not await client.check_and_get_dynamics_line("Luba-VA123")


async def test_an_unknown_device_is_not_fetched() -> None:
    assert not await MammotionClient().check_and_get_dynamics_line("Luba-LA999")
