"""``MammotionClient`` child-safety flow: read the switch, write it, re-read.

An X5 carries the setting as batch config, whose ack is a result code; an X3
carries it on the nav read/write channel.  The handle, broker and reducer are
real: a hand-written ``_FakeMower`` answers the frames the mocked cloud
transport is handed.
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
from pymammotion.proto import (
    AppBatchQueryResp,
    AppBatchSetResp,
    BatchConfigType,
    Batchcfg,
    BatchSetRes,
    ChildProtection,
    LubaMsg,
    MctlNav,
    MctlSys,
    NavSysParamMsg,
    ResResult,
)
from pymammotion.transport.base import CommandRejectedError, CommandTimeoutError, TransportType
from tests._helpers import let_others_run, make_account_session, make_bare_client, make_mock_transport

ACCOUNT = "acct@example.com"
X5 = "Luba-VAME9R5S"
X3 = "Luba-VS123456"
TIMEOUT = 5


class _FakeMower:
    """The device side: keeps the switch, acks writes and answers reads a few loop turns later."""

    def __init__(self, handle: DeviceHandle) -> None:
        self.handle = handle
        self.child_safety = False
        self.answer_reads = True
        self.answer_writes = True
        self.write_result = ResResult.RES_SUCCESS
        self.sent: list[str] = []
        self.user_initiated: list[bool] = []
        self._replies: set[asyncio.Task[None]] = set()

    async def send(self, payload: bytes, *, user_initiated: bool, **_: object) -> None:
        msg = LubaMsg().parse(payload)
        if (reply := self._answer(msg)) is None:
            return
        self.user_initiated.append(user_initiated)
        task = asyncio.create_task(self._deliver(reply))
        self._replies.add(task)
        task.add_done_callback(self._replies.discard)

    def _answer(self, msg: LubaMsg) -> LubaMsg | None:
        if msg.nav is not None and (param := msg.nav.nav_sys_param_cmd) is not None and param.id == 17:
            self.sent.append("write" if param.rw else "read")
            if param.rw:
                self.child_safety = bool(param.context)
            elif not self.answer_reads:
                return None
            reply = NavSysParamMsg(rw=param.rw, id=17, context=int(self.child_safety))
            return LubaMsg(nav=MctlNav(nav_sys_param_cmd=reply))
        if msg.sys is None:
            return None
        name, request = betterproto2.which_one_of(msg.sys, "SubSysMsg")
        if name == "batch_set_req":
            self.sent.append("write")
            if not self.answer_writes:
                return None
            if self.write_result == ResResult.RES_SUCCESS:
                self.child_safety = bool(request.cfgs[0].child_pro.child_protection_mode)
            result = BatchSetRes(type=BatchConfigType.CFG_TYPE_CHILD_PRO_CFG, res_result=self.write_result)
            return LubaMsg(sys=MctlSys(batch_set_resp=AppBatchSetResp(res_data=[result])))
        if name == "batch_query_req":
            self.sent.append("read")
            if not self.answer_reads:
                return None
            cfg = Batchcfg(
                cfgtype=BatchConfigType.CFG_TYPE_CHILD_PRO_CFG,
                child_pro=ChildProtection(child_protection_mode=int(self.child_safety)),
            )
            return LubaMsg(sys=MctlSys(batch_query_resp=AppBatchQueryResp(cfgs=[cfg])))
        return None

    async def _deliver(self, reply: LubaMsg) -> None:
        await let_others_run()
        await self.handle.on_raw_message(bytes(reply))


async def _client(device_name: str) -> tuple[MammotionClient, _FakeMower]:
    """A client holding *device_name* behind one mocked cloud transport."""
    client = make_bare_client(make_account_session(ACCOUNT))
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    handle = DeviceHandle("dev-1", device_name, MowingDevice(name=device_name), mqtt_transport=mqtt)
    mower = _FakeMower(handle)
    mqtt.send = AsyncMock(side_effect=partial(mower.send, user_initiated=False))
    mqtt.send_user = AsyncMock(side_effect=partial(mower.send, user_initiated=True))
    await client._device_registry.register(handle, account_id=ACCOUNT)
    return client, mower


def _child_safety(client: MammotionClient, device_name: str) -> bool | None:
    device = client.get_device_by_name(device_name)
    assert device is not None
    return device.mower_state.child_safety


@pytest.mark.parametrize("device_name", [X5, X3])
async def test_a_read_fills_the_switch(device_name: str) -> None:
    client, mower = await _client(device_name)
    mower.child_safety = True

    await asyncio.wait_for(client.read_child_safety(device_name), TIMEOUT)

    assert _child_safety(client, device_name) is True
    assert mower.user_initiated == [False], "a background read must stay behind the offline gate and the quota"


@pytest.mark.parametrize("device_name", [X5, X3])
async def test_a_write_reaches_the_mower_and_is_reread(device_name: str) -> None:
    client, mower = await _client(device_name)

    await asyncio.wait_for(client.set_child_safety(device_name, True), TIMEOUT)

    assert mower.child_safety is True
    assert _child_safety(client, device_name) is True
    assert mower.sent == ["write", "read"]
    assert mower.user_initiated == [True, True]


async def test_an_x5_refusal_raises_and_changes_nothing() -> None:
    client, mower = await _client(X5)
    mower.write_result = ResResult.RES_FAILURE

    with pytest.raises(CommandRejectedError):
        await asyncio.wait_for(client.set_child_safety(X5, True), TIMEOUT)

    assert _child_safety(client, X5) is None
    assert mower.sent == ["write"]


async def test_an_unacknowledged_write_raises_and_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The broker has no injectable clock: its real per-attempt timeout is the stimulus, shrunk to 10 ms."""
    monkeypatch.setattr(client_mod, "_BATCH_CONFIG_TIMEOUT", 0.01)
    client, mower = await _client(X5)
    mower.answer_writes = False

    with pytest.raises(CommandTimeoutError):
        await asyncio.wait_for(client.set_child_safety(X5, True), TIMEOUT)

    assert _child_safety(client, X5) is None
    assert "read" not in mower.sent


async def test_an_unanswered_reread_keeps_the_value_the_x5_acknowledged(monkeypatch: pytest.MonkeyPatch) -> None:
    """The broker has no injectable clock: its real per-attempt timeout is the stimulus, shrunk to 10 ms."""
    monkeypatch.setattr(client_mod, "_BATCH_CONFIG_TIMEOUT", 0.01)
    client, mower = await _client(X5)
    mower.answer_reads = False

    await asyncio.wait_for(client.set_child_safety(X5, True), TIMEOUT)

    assert _child_safety(client, X5) is True


async def test_an_unanswered_read_raises_and_leaves_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The broker has no injectable clock: its real per-attempt timeout is the stimulus, shrunk to 10 ms."""
    monkeypatch.setattr(client_mod, "_BATCH_CONFIG_TIMEOUT", 0.01)
    client, mower = await _client(X5)
    mower.answer_reads = False

    with pytest.raises(CommandTimeoutError):
        await asyncio.wait_for(client.read_child_safety(X5), TIMEOUT)

    assert _child_safety(client, X5) is None


async def test_a_write_and_a_read_started_together_take_turns() -> None:
    """The write's re-read and the read share a reply field; overlapping, one would be refused as concurrent."""
    client, _ = await _client(X5)

    await asyncio.wait_for(asyncio.gather(client.set_child_safety(X5, True), client.read_child_safety(X5)), TIMEOUT)

    assert _child_safety(client, X5) is True


async def test_a_mower_without_the_setting_is_sent_nothing() -> None:
    client, mower = await _client("Luba-ABCDEF")

    with pytest.raises(ValueError, match="only supported on X3 and X5"):
        await asyncio.wait_for(client.set_child_safety("Luba-ABCDEF", True), TIMEOUT)

    assert mower.sent == []


async def test_an_unknown_device_raises_key_error() -> None:
    client, _ = await _client(X5)

    with pytest.raises(KeyError):
        await client.set_child_safety("Luba-UNKNOWN", True)
