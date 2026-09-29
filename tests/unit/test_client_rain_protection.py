"""``MammotionClient.read_rain_protection`` / ``set_rain_protection`` — the app's rain-protection flow.

The app (``RainProtectionModule.setRainProtectionMode``, APK 2.3.20.30) writes the
device over the batch-config channel, applies the values it sent once the ack says
success (the ack carries none), then POSTs them to the weather server; this flow
also re-reads the device.  The handle, broker and reducer are real: a hand-written
``_FakeMower`` answers the frames the mocked cloud transport is handed.  The weather
server is a real ``MammotionHTTP`` over a canned aiohttp session.
"""

from __future__ import annotations

import asyncio
from functools import partial
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, create_autospec

from aiohttp import ClientConnectionError, ClientResponse
import betterproto2
import pytest

from pymammotion import client as client_mod
from pymammotion.auth.token_manager import TokenManager
from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.device_info import RainProtectionSettings
from pymammotion.data.model.mowing_modes import RainProtectionMode
from pymammotion.device.handle import DeviceHandle
from pymammotion.http.model.http import UnauthorizedExceptionError
from pymammotion.http.model.rain_protection import WeatherServerSync
from pymammotion.proto import (
    AppBatchQueryResp,
    AppBatchSetResp,
    Batchcfg,
    BatchConfigType,
    BatchSetRes,
    LubaMsg,
    MctlSys,
    RainProtection,
    ResResult,
)
from pymammotion.transport.base import CommandRejectedError, CommandTimeoutError, TransportType
from tests._helpers import let_others_run, make_account_session, make_bare_client, make_mock_transport
from tests.unit._helpers import make_http_posting

ACCOUNT = "acct@example.com"
DEVICE = "Luba-VAME9R5S"
TOKEN = "tok"
SAVED = (HTTPStatus.OK.value, {"code": 0, "msg": "success", "data": None})
UNAUTHORIZED = (HTTPStatus.OK.value, {"code": 401, "msg": "token expired", "data": None})
TIMEOUT = 5


class _FakeMower:
    """The device side of the batch-config channel: stores what it is set to and answers queries.

    *answer_sets* is the ``res_result`` it acks writes with (``None`` acks with no RAINPRO
    entry at all); *answer_queries* False leaves queries unanswered.  Replies are delivered
    a few loop turns after the send, so concurrent callers genuinely overlap.
    """

    def __init__(self, handle: DeviceHandle) -> None:
        self.handle = handle
        self.mode = 0
        self.delay = 0
        self.answer_sets: ResResult | None = ResResult.RES_SUCCESS
        self.answer_queries = True
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
        if name == "batch_set_req":
            reply = self._ack(request.cfgs[0].rain_pro)
        elif name == "batch_query_req" and self.answer_queries:
            rain_pro = RainProtection(result=1, rain_protection_mode=self.mode, custom_delay_hours=self.delay)
            cfg = Batchcfg(cfgtype=BatchConfigType.CFG_TYPE_RAINPRO_CFG, rain_pro=rain_pro)
            reply = LubaMsg(sys=MctlSys(batch_query_resp=AppBatchQueryResp(req_id=1, cfgs=[cfg])))
        else:
            return
        task = asyncio.create_task(self._deliver(reply))
        self._replies.add(task)
        task.add_done_callback(self._replies.discard)

    def _ack(self, rain_pro: RainProtection) -> LubaMsg:
        results = []
        if self.answer_sets is not None:
            if self.answer_sets is ResResult.RES_SUCCESS:
                self.mode, self.delay = rain_pro.rain_protection_mode, rain_pro.custom_delay_hours
            results = [BatchSetRes(type=BatchConfigType.CFG_TYPE_RAINPRO_CFG, res_result=self.answer_sets)]
        return LubaMsg(sys=MctlSys(batch_set_resp=AppBatchSetResp(req_id=1, res_data=results)))

    async def _deliver(self, reply: LubaMsg) -> None:
        await let_others_run()
        await self.handle.on_raw_message(bytes(reply))

    def sets(self) -> int:
        return self.sent.count("batch_set_req")

    def queries(self) -> int:
        return self.sent.count("batch_query_req")


def _reply(status: int, body: dict) -> MagicMock:
    reply = MagicMock(spec=ClientResponse, status=status, headers={"Content-Type": "application/json"})
    reply.json = AsyncMock(return_value=body)
    return reply


async def _client(
    *posts: tuple[int, dict], cloud: bool = True, settings: RainProtectionSettings | None = None
) -> tuple[MammotionClient, _FakeMower, MagicMock, MagicMock]:
    """A client holding *DEVICE* behind one mocked cloud transport; POSTs answer with *posts*."""
    http, http_session = make_http_posting(HTTPStatus.OK.value, {})
    http_session.post = AsyncMock(side_effect=[_reply(status, body) for status, body in posts])
    token_manager = create_autospec(TokenManager, instance=True)
    client = make_bare_client(make_account_session(ACCOUNT, http=http, token_manager=token_manager))
    device = MowingDevice(name=DEVICE)
    if settings is not None:
        device.mower_state.rain_protection = settings
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    handle = DeviceHandle("dev-1", DEVICE, device, mqtt_transport=mqtt)
    mower = _FakeMower(handle)
    mqtt.send = AsyncMock(side_effect=partial(mower.send, user_initiated=False))
    mqtt.send_user = AsyncMock(side_effect=partial(mower.send, user_initiated=True))
    await client._device_registry.register(handle, account_id=ACCOUNT if cloud else None)
    return client, mower, http_session, token_manager


def _rain(client: MammotionClient) -> RainProtectionSettings:
    device = client.get_device_by_name(DEVICE)
    assert device is not None
    return device.mower_state.rain_protection


def _posted(http_session: MagicMock) -> list[dict]:
    return [call.kwargs["json"] for call in http_session.post.await_args_list]


async def test_a_read_returns_what_the_device_reported() -> None:
    client, mower, _, _ = await _client()
    mower.mode, mower.delay = 2, 6

    settings = await asyncio.wait_for(client.read_rain_protection(DEVICE), TIMEOUT)

    assert settings == RainProtectionSettings(supported=True, mode=RainProtectionMode.sensor, delay_hours=6)
    assert _rain(client) == settings


async def test_concurrent_reads_take_turns_instead_of_colliding() -> None:
    """Both wait on ``batch_query_resp``; the broker allows one pending request per field."""
    client, mower, _, _ = await _client()

    await asyncio.wait_for(
        asyncio.gather(client.read_rain_protection(DEVICE), client.read_rain_protection(DEVICE)), TIMEOUT
    )

    assert mower.queries() == 2


async def test_a_set_and_a_read_started_together_take_turns() -> None:
    """The set's re-read and the read both wait on ``batch_query_resp``; neither may collide.

    The set itself waits on ``batch_set_resp``, so this pins the read's lock; the set's lock is
    pinned by two concurrent sets.
    """
    client, mower, _, _ = await _client(SAVED)

    sync, settings = await asyncio.wait_for(
        asyncio.gather(
            client.set_rain_protection(DEVICE, RainProtectionMode.smart), client.read_rain_protection(DEVICE)
        ),
        TIMEOUT,
    )

    assert sync is WeatherServerSync.SAVED
    assert settings.supported is True
    assert (mower.sets(), mower.queries()) == (1, 2)


async def test_two_sets_started_together_take_turns() -> None:
    """Both wait on ``batch_set_resp`` (a mode pick then a delay pick in quick succession)."""
    client, mower, _, _ = await _client(SAVED, SAVED)

    await asyncio.wait_for(
        asyncio.gather(
            client.set_rain_protection(DEVICE, RainProtectionMode.smart),
            client.set_rain_protection(DEVICE, RainProtectionMode.sensor, 6),
        ),
        TIMEOUT,
    )

    assert mower.sets() == 2
    assert (mower.mode, mower.delay) == (2, 6)


async def test_a_set_writes_the_device_saves_the_server_copy_and_rereads() -> None:
    client, mower, http_session, _ = await _client(SAVED)

    sync = await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.sensor, 6), TIMEOUT)

    assert sync is WeatherServerSync.SAVED
    assert mower.sent == ["batch_set_req", "batch_query_req"]
    assert (mower.mode, mower.delay) == (2, 6)
    assert _posted(http_session) == [
        {"deviceName": DEVICE, "rainProtectionMode": 2, "customDelayHours": 6, "pushToDevice": False}
    ]
    assert _rain(client) == RainProtectionSettings(supported=True, mode=RainProtectionMode.sensor, delay_hours=6)


async def test_a_set_is_a_user_command_that_waives_the_offline_flag() -> None:
    client, mower, _, _ = await _client(SAVED)
    handle = client.mower(DEVICE)
    assert handle is not None
    handle.update_availability(TransportType.CLOUD_ALIYUN, handle.availability.mqtt, mqtt_reported_offline=True)

    await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.off), TIMEOUT)

    assert mower.sets() == 1
    assert all(mower.user_initiated), f"expected every send user-initiated, got {mower.user_initiated}"


@pytest.mark.parametrize("mode", [RainProtectionMode.off, RainProtectionMode.smart])
async def test_leaving_sensor_mode_keeps_the_delay_for_later_and_saves_zero(mode: RainProtectionMode) -> None:
    remembered = RainProtectionSettings(supported=True, mode=RainProtectionMode.sensor, delay_hours=48)
    client, mower, http_session, _ = await _client(SAVED, settings=remembered)

    await asyncio.wait_for(client.set_rain_protection(DEVICE, mode), TIMEOUT)

    assert (mower.mode, mower.delay) == (mode.value, 0)
    assert _posted(http_session)[0]["customDelayHours"] == 0
    assert (_rain(client).mode, _rain(client).delay_hours) == (mode.value, 48)


async def test_returning_to_sensor_mode_resends_the_remembered_delay() -> None:
    """The app keeps the last Sensor delay itself; picking Sensor again must not reset it."""
    remembered = RainProtectionSettings(supported=True, mode=RainProtectionMode.off, delay_hours=48)
    client, mower, http_session, _ = await _client(SAVED, settings=remembered)

    await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.sensor), TIMEOUT)

    assert (mower.mode, mower.delay) == (2, 48)
    assert _posted(http_session)[0]["customDelayHours"] == 48


async def test_sensor_mode_on_a_never_read_device_uses_the_apps_default_delay() -> None:
    client, mower, _, _ = await _client(SAVED)

    await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.sensor), TIMEOUT)

    assert mower.delay == 24


@pytest.mark.parametrize("ack", [ResResult.RES_FAILURE, None], ids=["failure", "no-rainpro-entry"])
async def test_a_refused_write_raises_and_changes_nothing(ack: ResResult | None) -> None:
    before = RainProtectionSettings(supported=True, mode=RainProtectionMode.off, delay_hours=24)
    client, mower, http_session, _ = await _client(SAVED, settings=before)
    mower.answer_sets = ack

    with pytest.raises(CommandRejectedError):
        await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.smart), TIMEOUT)

    assert _rain(client) == before
    http_session.post.assert_not_awaited()
    assert mower.queries() == 0


async def test_a_ble_only_mower_is_set_without_the_weather_server() -> None:
    client, mower, http_session, _ = await _client(cloud=False)

    sync = await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.smart), TIMEOUT)

    assert sync is WeatherServerSync.SKIPPED
    http_session.post.assert_not_awaited()
    assert _rain(client).mode == RainProtectionMode.smart
    assert mower.queries() == 1


@pytest.mark.parametrize(
    "failure",
    [
        _reply(HTTPStatus.OK.value, {"code": 500, "msg": "internal", "data": None}),
        _reply(HTTPStatus.BAD_GATEWAY.value, {"code": 502, "msg": "bad gateway"}),
        ClientConnectionError("down"),
    ],
    ids=["error-code", "http-502", "network"],
)
async def test_a_failed_save_keeps_the_device_setting(failure: object) -> None:
    """The device already changed; the app does not roll it back, and neither may we."""
    client, mower, http_session, _ = await _client()
    http_session.post = AsyncMock(side_effect=[failure])

    sync = await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.smart), TIMEOUT)

    assert sync is WeatherServerSync.FAILED
    assert mower.sets() == 1
    assert _rain(client).mode == RainProtectionMode.smart
    assert mower.queries() == 1, "the re-read still runs"


async def test_a_401_on_the_save_refreshes_the_token_once_and_retries() -> None:
    client, _, http_session, token_manager = await _client(UNAUTHORIZED, SAVED)

    sync = await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.smart), TIMEOUT)

    assert sync is WeatherServerSync.SAVED
    token_manager.refresh_invoke_token.assert_awaited_once_with(stale_token=TOKEN)
    assert http_session.post.await_count == 2


async def test_a_second_401_propagates_after_the_device_was_set() -> None:
    """A dead login is the host's to handle; the device write it followed is not undone."""
    client, mower, _, _ = await _client(UNAUTHORIZED, UNAUTHORIZED)

    with pytest.raises(UnauthorizedExceptionError):
        await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.smart), TIMEOUT)

    assert _rain(client).mode == RainProtectionMode.smart
    assert mower.sets() == 1


async def test_an_unanswered_reread_leaves_the_applied_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """The broker has no injectable clock: its real per-attempt timeout is the stimulus, shrunk to 10 ms."""
    monkeypatch.setattr(client_mod, "_BATCH_CONFIG_TIMEOUT", 0.01)
    client, mower, _, _ = await _client(SAVED)
    mower.answer_queries = False

    sync = await asyncio.wait_for(client.set_rain_protection(DEVICE, RainProtectionMode.smart), TIMEOUT)

    assert sync is WeatherServerSync.SAVED
    assert _rain(client).mode == RainProtectionMode.smart


async def test_an_unanswered_read_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """The broker has no injectable clock: its real per-attempt timeout is the stimulus, shrunk to 10 ms."""
    monkeypatch.setattr(client_mod, "_BATCH_CONFIG_TIMEOUT", 0.01)
    client, mower, _, _ = await _client()
    mower.answer_queries = False

    with pytest.raises(CommandTimeoutError):
        await asyncio.wait_for(client.read_rain_protection(DEVICE), TIMEOUT)

    assert _rain(client).supported is None


async def test_an_invalid_delay_is_refused_before_anything_is_sent() -> None:
    client, mower, _, _ = await _client(SAVED)

    with pytest.raises(ValueError, match="delay"):
        await client.set_rain_protection(DEVICE, RainProtectionMode.sensor, 13)

    assert mower.sent == []


async def test_an_unknown_device_raises_key_error() -> None:
    client, _, _, _ = await _client()

    with pytest.raises(KeyError):
        await client.set_rain_protection("Luba-UNKNOWN", RainProtectionMode.off)
