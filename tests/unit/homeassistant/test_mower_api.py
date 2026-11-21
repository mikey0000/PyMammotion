"""``HomeAssistantMowerApi``: the facade Home Assistant core's Mammotion integration consumes.

Every member that integration calls is pinned here (constructor, ``mammotion``, ``is_online``
and the per-device calls it maps to HA errors), so the contract cannot drift silently.
``update`` has its own module.  Where the call into the client *is* the contract (which
priority a command takes, which client method a call lands on) the client method is
patched with ``autospec``; otherwise the real client and a real handle are used.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import patch

import pytest

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowerDevice, MowingDevice
from pymammotion.data.model.device_capabilities import DeviceConfig
from pymammotion.data.model.device_config import OperationSettings
from pymammotion.device.handle import DeviceHandle, DeviceNotRegisteredError
from pymammotion.homeassistant.mower_api import HomeAssistantMowerApi
from pymammotion.messaging.command_queue import Priority
from pymammotion.state.device_state import DeviceSnapshot
from pymammotion.utility.constant.device_constant import WorkMode
from tests.unit.homeassistant._helpers import NAME, make_api

_MISSING = "Luba-MISSING"


def test_the_constructor_takes_the_keywords_the_integration_passes() -> None:
    api = HomeAssistantMowerApi(ha_version="2026.11.0", session=None)

    assert isinstance(api.mammotion, MammotionClient)


@pytest.mark.parametrize("online", [True, False])
async def test_is_online_reports_what_the_cloud_last_said(online: bool) -> None:
    device = MowerDevice(name=NAME)
    device.online = online
    api, _ = await make_api(device)

    assert api.is_online(NAME) is online


async def test_is_online_is_false_for_an_unknown_device() -> None:
    api, _ = await make_api()

    assert api.is_online(_MISSING) is False


async def test_device_limits_are_the_family_defaults_for_an_unknown_device() -> None:
    api, _ = await make_api()

    assert api.device_limits(_MISSING) == DeviceConfig().get_best_default("")


async def test_device_limits_come_from_the_devices_model() -> None:
    device = MowerDevice(name=NAME)
    device.mower_state.sub_model_id = "HM010060LBAWD10"
    api, _ = await make_api(device)

    limits = api.device_limits(NAME)

    assert limits == DeviceConfig().get_working_parameters("HM010060LBAWD10")
    assert limits != DeviceConfig().get_best_default(""), "the model's limits must differ from the fallback"


async def _noop(_: DeviceSnapshot) -> None:
    pass


_UNKNOWN_DEVICE_CALLS: list[tuple[str, Callable[[HomeAssistantMowerApi], Any]]] = [
    ("update", lambda api: api.update(_MISSING)),
    ("async_send_command", lambda api: api.async_send_command(_MISSING, "get_report_cfg")),
    ("async_send_user_command", lambda api: api.async_send_user_command(_MISSING, "start_job")),
    ("async_wait_for_mode", lambda api: api.async_wait_for_mode(_MISSING, WorkMode.MODE_PAUSE)),
    ("async_request_report", lambda api: api.async_request_report(_MISSING)),
    ("async_request_state_if_stale", lambda api: api.async_request_state_if_stale(_MISSING)),
    ("async_refresh_state_if_stale", lambda api: api.async_refresh_state_if_stale(_MISSING)),
    ("restore_device", lambda api: api.restore_device(_MISSING, MowingDevice())),
    ("subscribe_state_changed", lambda api: api.subscribe_state_changed(_MISSING, _noop)),
    ("set_scheduled_updates", lambda api: api.set_scheduled_updates(_MISSING, enabled=False)),
    ("update_firmware", lambda api: api.update_firmware(_MISSING, "1.0.0")),
    ("async_wake_up", lambda api: api.async_wake_up(_MISSING)),
    ("async_start_stop_blades", lambda api: api.async_start_stop_blades(_MISSING, start_stop=True)),
    ("async_leave_dock", lambda api: api.async_leave_dock(_MISSING)),
    ("async_move_forward", lambda api: api.async_move_forward(_MISSING, 0.4)),
    ("async_set_non_work_hours", lambda api: api.async_set_non_work_hours(_MISSING, "22:00", "06:00")),
    ("generate_route_information", lambda api: api.generate_route_information(_MISSING, OperationSettings())),
    ("async_plan_route", lambda api: api.async_plan_route(_MISSING, OperationSettings())),
    ("async_modify_plan_route", lambda api: api.async_modify_plan_route(_MISSING, OperationSettings())),
    ("clear_update_failures", lambda api: api.clear_update_failures(_MISSING)),
    ("async_check_firmware_version", lambda api: api.async_check_firmware_version(_MISSING)),
    ("async_setup_device", lambda api: api.async_setup_device(_MISSING)),
]


@pytest.mark.parametrize("call", [call for _, call in _UNKNOWN_DEVICE_CALLS], ids=[n for n, _ in _UNKNOWN_DEVICE_CALLS])
async def test_an_unknown_device_raises_device_not_registered(call: Callable[[HomeAssistantMowerApi], Any]) -> None:
    """One rule for every call that acts on a device; the error is a ``KeyError`` for older callers."""
    api, _ = await make_api()

    with pytest.raises(DeviceNotRegisteredError):
        result = call(api)
        if isinstance(result, Awaitable):
            await result


async def test_a_user_command_is_sent_at_user_priority() -> None:
    """``Priority.USER`` is what lets it pass a running saga and raise when it does not land."""
    api, _ = await make_api()

    with patch.object(MammotionClient, "send_command_with_args", autospec=True) as send:
        await api.async_send_user_command(NAME, "start_job")

    send.assert_awaited_once_with(api.mammotion, NAME, "start_job", priority=Priority.USER)


async def test_a_background_command_is_queued_at_normal_priority() -> None:
    api, _ = await make_api()

    with patch.object(MammotionClient, "send_command_with_args", autospec=True) as send:
        assert await api.async_send_command(NAME, "get_report_cfg") is True

    send.assert_awaited_once_with(api.mammotion, NAME, "get_report_cfg")


async def test_a_background_command_that_cannot_be_built_reports_false() -> None:
    api, _ = await make_api()

    assert await api.async_send_command(NAME, "no_such_command") is False
    assert api.update_failures == 1


@pytest.mark.regression
@pytest.mark.parametrize(
    ("method", "command"),
    [
        ("async_move_forward", "move_forward"),
        ("async_move_back", "move_back"),
        ("async_move_left", "move_left"),
        ("async_move_right", "move_right"),
    ],
)
async def test_manual_movement_is_a_user_command(method: str, command: str) -> None:
    """Movement was queued at NORMAL, so a nudge waited behind a map sync and arrived minutes late.

    D14: a command whose value decays takes ``Priority.USER``.
    """
    api, _ = await make_api()

    with patch.object(MammotionClient, "send_command_with_args", autospec=True) as send:
        await getattr(api, method)(NAME, 0.4)

    assert send.await_args.args[2] == command
    assert send.await_args.kwargs["priority"] is Priority.USER


async def test_wait_for_mode_returns_the_mode_the_mower_reported() -> None:
    api, _ = await make_api()
    paused = MowerDevice(name=NAME)
    paused.report_data.dev.sys_status = WorkMode.MODE_PAUSE

    with patch.object(MammotionClient, "wait_for", autospec=True, return_value=paused) as wait_for:
        mode = await api.async_wait_for_mode(NAME, WorkMode.MODE_PAUSE, WorkMode.MODE_READY, timeout=5)

    predicate = wait_for.await_args.args[2]
    working = MowerDevice(name=NAME)
    working.report_data.dev.sys_status = WorkMode.MODE_WORKING
    assert mode is WorkMode.MODE_PAUSE
    assert predicate(paused) is True
    assert predicate(working) is False, "the wait must not end on a mode it was not asked for"
    assert wait_for.await_args.kwargs["timeout"] == 5


async def test_request_report_asks_the_handle_for_a_background_snapshot() -> None:
    api, _ = await make_api()

    with patch.object(DeviceHandle, "request_report_snapshot", autospec=True) as request:
        await api.async_request_report(NAME)

    request.assert_awaited_once()


@pytest.mark.parametrize(("method", "wait"), [("async_request_state_if_stale", False), ("async_refresh_state_if_stale", True)])
async def test_the_two_fresh_state_calls_take_the_two_client_paths(method: str, wait: bool) -> None:
    """One returns at once (a queued background request), the other waits for the report (the user path)."""
    api, handle = await make_api()

    with patch.object(MammotionClient, "ensure_fresh_state", autospec=True) as ensure:
        await getattr(api, method)(NAME, max_age_s=30)

    ensure.assert_awaited_once_with(api.mammotion, NAME, max_age_s=30, account_id=handle.account_id, **({"wait": True} if wait else {}))


async def test_restore_device_seeds_the_handles_state() -> None:
    api, handle = await make_api()
    saved = MowerDevice(name=NAME)
    saved.mower_state.swversion = "1.2.3"

    api.restore_device(NAME, saved)

    assert handle.snapshot.raw.mower_state.swversion == "1.2.3"


async def test_a_state_subscription_receives_snapshots_until_cancelled() -> None:
    api, handle = await make_api()
    received: list[DeviceSnapshot] = []

    async def _record(snapshot: DeviceSnapshot) -> None:
        received.append(snapshot)

    subscription = api.subscribe_state_changed(NAME, _record)
    await handle.emit_state_changed(handle.snapshot)
    subscription.cancel()
    await handle.emit_state_changed(handle.snapshot)

    assert received == [handle.snapshot]


@pytest.mark.regression
async def test_plan_route_reports_a_saga_that_was_gated_off() -> None:
    """It answered True whatever happened, so a fetch refused over MQTT read as started."""
    api, _ = await make_api()

    with patch.object(MammotionClient, "start_mow_path_saga", autospec=True, return_value=False):
        assert await api.async_plan_route(NAME, OperationSettings(areas=[1])) is False


async def test_route_generation_reads_the_device_it_was_named_for() -> None:
    """The gates follow the named device: its firmware, not another mower's, decides auto-reverse.

    The gate rules themselves are pinned against ``build_route_information`` in
    ``tests/unit/data/model/test_device_config.py``; this pins that the wrapper feeds it the right device.
    """
    target = MowerDevice(name="Luba-VA6ABCDE")
    target.device_firmwares.device_version = "2.3.28.1"
    api, _ = await make_api(target, name="Luba-VA6ABCDE")
    other = MowerDevice(name="Luba-VA6OTHER")
    other.device_firmwares.device_version = "1.0.0.0"
    await api.mammotion.device_registry.register(_handle_for(other))

    route = api.generate_route_information("Luba-VA6ABCDE", OperationSettings(auto_change_direction=1))

    assert route.auto_change_direction == 1


def _handle_for(device: MowerDevice) -> DeviceHandle:
    return DeviceHandle(device_id=device.name, device_name=device.name, initial_device=device)


async def _modified_route(work_setup: Callable[[MowerDevice], None], settings: OperationSettings) -> Any:
    device = MowerDevice(name="Luba-VA6ABCDE")
    device.device_firmwares.device_version = "2.3.28.1"
    work_setup(device)
    api, _ = await make_api(device, name="Luba-VA6ABCDE")
    with patch.object(MammotionClient, "send_command_with_args", autospec=True) as send:
        await api.async_modify_plan_route("Luba-VA6ABCDE", settings)
    return send.await_args.kwargs["generate_route_information"]


async def test_modifying_a_running_job_keeps_its_ride_boundary_distance() -> None:
    """Modify re-sends the whole route, so the running job's value is seeded from ``work`` or it resets to 0."""

    def _work(device: MowerDevice) -> None:
        device.work.edge_mode = 1
        device.work.ride_boundary_distance = 0.5

    route = await _modified_route(_work, OperationSettings())

    assert route.ride_boundary_distance == 0.5


@pytest.mark.regression
async def test_modifying_a_running_job_keeps_its_auto_reverse_setting() -> None:
    """A route write always carries the auto-reverse buffer, so a modify must copy the running job's setting.

    Routes used to omit the field when off, leaving the running job untouched.  Now that they send explicit
    zeros, a modify built from a default OperationSettings would switch auto-reverse off mid-job.
    """

    def _work(device: MowerDevice) -> None:
        device.work.auto_change_direction = True

    route = await _modified_route(_work, OperationSettings())

    assert route.auto_change_direction == 1


async def test_modifying_a_job_that_reports_no_auto_reverse_keeps_the_callers_choice() -> None:
    """``None`` means the device did not report it, so the caller's setting is used unchanged."""

    def _work(device: MowerDevice) -> None:
        device.work.auto_change_direction = None

    route = await _modified_route(_work, OperationSettings(auto_change_direction=1))

    assert route.auto_change_direction == 1


async def test_async_wake_up_passes_the_clients_answer_through() -> None:
    """The wake lives on MammotionClient: it owns both the handle and the account's session."""
    api, _ = await make_api()

    with patch.object(MammotionClient, "wake_device", autospec=True, return_value=False) as wake:
        assert await api.async_wake_up(NAME) is False

    wake.assert_awaited_once_with(api.mammotion, NAME)
