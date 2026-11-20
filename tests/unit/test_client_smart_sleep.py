"""``MammotionClient`` Smart Sleep flow: read both switches, write one, re-read.

The write's ack carries a result code rather than the switch positions, so the
client applies the value it sent and then re-reads.  The handle, broker and
reducer are real: a hand-written ``_FakeMower`` answers the frames the mocked
cloud transport is handed.
"""

from __future__ import annotations

import asyncio
from functools import partial
from unittest.mock import AsyncMock

import betterproto2
import pytest

from pymammotion import client as client_mod
from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowingDevice
from pymammotion.device.handle import DeviceHandle
from pymammotion.proto import DevLowPowerGet, DevLowPowerSetInfo, LubaMsg, MctlSys
from pymammotion.transport.base import CommandTimeoutError, TransportType
from tests._helpers import let_others_run, make_account_session, make_bare_client, make_mock_transport

ACCOUNT = "acct@example.com"
DEVICE = "Luba-VAME9R5S"
TIMEOUT = 5


class _FakeMower:
    """The device side: keeps the two switches, acks writes and answers reads a few loop turns later."""

    def __init__(self, handle: DeviceHandle) -> None:
        self.handle = handle
        self.eco = False
        self.live = False
        self.answer_reads = True
        self.answer_writes = True
        self.sent: list[str] = []
        self.user_initiated: list[bool] = []
        self._replies: set[asyncio.Task[None]] = set()

    async def send(self, payload: bytes, *, user_initiated: bool, **_: object) -> None:
        msg = LubaMsg().parse(payload)
        if msg.sys is None:
            return
        name, request = betterproto2.which_one_of(msg.sys, "SubSysMsg")
        self.sent.append(name)
        self.user_initiated.append(user_initiated)
        if name == "to_set_dev_low_power_cmd" and self.answer_writes:
            if request.set_charging_lowpower_sta:
                self.eco = bool(request.charging_low_power)
            if request.set_uncharging_lowpower_sta:
                self.live = bool(request.uncharging_low_power)
            reply = MctlSys(to_set_dev_low_power_cmd=DevLowPowerSetInfo())
        elif name == "to_get_dev_low_power_cmd" and self.answer_reads:
            reply = MctlSys(
                to_get_dev_low_power_cmd=DevLowPowerGet(
                    charging_low_power=int(self.eco), uncharging_low_power=int(self.live)
                )
            )
        else:
            return
        task = asyncio.create_task(self._deliver(LubaMsg(sys=reply)))
        self._replies.add(task)
        task.add_done_callback(self._replies.discard)

    async def _deliver(self, reply: LubaMsg) -> None:
        await let_others_run()
        await self.handle.on_raw_message(bytes(reply))


async def _client() -> tuple[MammotionClient, _FakeMower]:
    """A client holding *DEVICE* behind one mocked cloud transport."""
    client = make_bare_client(make_account_session(ACCOUNT))
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    handle = DeviceHandle("dev-1", DEVICE, MowingDevice(name=DEVICE), mqtt_transport=mqtt)
    mower = _FakeMower(handle)
    mqtt.send = AsyncMock(side_effect=partial(mower.send, user_initiated=False))
    mqtt.send_user = AsyncMock(side_effect=partial(mower.send, user_initiated=True))
    await client._device_registry.register(handle, account_id=ACCOUNT)
    return client, mower


def _switches(client: MammotionClient) -> tuple[bool | None, bool | None]:
    device = client.get_device_by_name(DEVICE)
    assert device is not None
    return device.mower_state.eco_sleep, device.mower_state.live_sleep


async def test_a_read_fills_both_switches() -> None:
    client, mower = await _client()
    mower.eco = True

    await asyncio.wait_for(client.read_smart_sleep(DEVICE), TIMEOUT)

    assert _switches(client) == (True, False)
    assert mower.user_initiated == [False], "a background read must stay behind the offline gate and the quota"


async def test_an_unanswered_read_raises_and_leaves_the_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    """The broker has no injectable clock: its real per-attempt timeout is the stimulus, shrunk to 10 ms."""
    monkeypatch.setattr(client_mod, "_SMART_SLEEP_TIMEOUT", 0.01)
    client, mower = await _client()
    mower.answer_reads = False

    with pytest.raises(CommandTimeoutError):
        await asyncio.wait_for(client.read_smart_sleep(DEVICE), TIMEOUT)

    assert _switches(client) == (None, None)


async def test_a_write_changes_its_own_switch_and_rereads() -> None:
    client, mower = await _client()

    await asyncio.wait_for(client.set_live_sleep(DEVICE, True), TIMEOUT)

    assert (mower.eco, mower.live) == (False, True)
    assert _switches(client) == (False, True)
    assert mower.sent == ["to_set_dev_low_power_cmd", "to_get_dev_low_power_cmd"]


async def test_a_write_is_a_user_command() -> None:
    """Sent at once, past the queue and the cloud's advisory offline flag."""
    client, mower = await _client()

    await asyncio.wait_for(client.set_eco_sleep(DEVICE, True), TIMEOUT)

    assert mower.user_initiated == [True, True]


async def test_an_unanswered_reread_keeps_the_value_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The broker has no injectable clock: its real per-attempt timeout is the stimulus, shrunk to 10 ms."""
    monkeypatch.setattr(client_mod, "_SMART_SLEEP_TIMEOUT", 0.01)
    client, mower = await _client()
    mower.answer_reads = False

    await asyncio.wait_for(client.set_eco_sleep(DEVICE, True), TIMEOUT)

    assert _switches(client) == (True, None), "the acked value must show even though nothing confirmed the pair"


async def test_an_unacknowledged_write_raises_and_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The broker has no injectable clock: its real per-attempt timeout is the stimulus, shrunk to 10 ms."""
    monkeypatch.setattr(client_mod, "_SMART_SLEEP_TIMEOUT", 0.01)
    client, mower = await _client()
    mower.answer_writes = False

    with pytest.raises(CommandTimeoutError):
        await asyncio.wait_for(client.set_eco_sleep(DEVICE, True), TIMEOUT)

    assert _switches(client) == (None, None)
    assert "to_get_dev_low_power_cmd" not in mower.sent


async def test_both_switches_written_together_take_turns() -> None:
    """Both wait on the same reply fields; overlapping, the second would be refused as a concurrent request."""
    client, mower = await _client()

    await asyncio.wait_for(
        asyncio.gather(client.set_eco_sleep(DEVICE, True), client.set_live_sleep(DEVICE, True)), TIMEOUT
    )

    assert _switches(client) == (True, True)
    assert mower.sent == ["to_set_dev_low_power_cmd", "to_get_dev_low_power_cmd"] * 2


async def test_a_write_and_a_read_started_together_take_turns() -> None:
    client, mower = await _client()

    await asyncio.wait_for(asyncio.gather(client.set_eco_sleep(DEVICE, True), client.read_smart_sleep(DEVICE)), TIMEOUT)

    assert _switches(client) == (True, False)


async def test_an_unknown_device_raises_key_error() -> None:
    client, _ = await _client()

    with pytest.raises(KeyError):
        await client.set_eco_sleep("Luba-UNKNOWN", True)
