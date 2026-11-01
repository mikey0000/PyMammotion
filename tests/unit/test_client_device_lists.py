"""How ``MammotionClient`` acts on the account's device lists: listing, caching, restore and bootstrap.

A device list the server failed to return is not proof the account is empty, so a
failed fetch must never drop a device or be written to the host's cache as an
emptied account.  A list the server *did* return replaces what was held.
"""

from __future__ import annotations

from contextlib import ExitStack
from http import HTTPStatus
import inspect
import logging
from unittest.mock import AsyncMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import DeviceInfo, DeviceRecord, DeviceRecords, MQTTConnection, Response
from pymammotion.transport.base import TransportAvailability, TransportType
from tests._helpers import make_bare_client, make_mock_handle, make_mock_transport
from tests.unit._helpers import (
    EMPTY_PAGE_BODIES,
    FAILED_FETCHES,
    device_record_json,
    device_records,
    make_http_posting,
)

ACCOUNT = "user@test.com"
STALE = "Luba-VAME9R5S"
SHARED = "Luba-SHARED"
MQTT = MQTTConnection(host="h", jwt="j", client_id="c", username="u")


def _session(http: MammotionHTTP) -> AccountSession:
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.mammotion_http = http
    return session


def _owned_list(*names: str) -> dict:
    return {"code": 0, "msg": "success", "data": [{"deviceName": n, "iotId": f"iot-{n}"} for n in names]}


async def _mammotion_handle(client: MammotionClient, name: str) -> DeviceHandle:
    """Register a Mammotion-MQTT-only handle for *name*, as a restore from cache would."""
    handle = make_mock_handle(name, name)
    handle.iot_id = f"iot-{name}"
    await handle.add_transport(
        make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    )
    await client._device_registry.register(handle, ACCOUNT)  # noqa: SLF001
    return handle


@pytest.mark.parametrize(
    ("records", "listed"),
    [
        pytest.param(None, [], id="unknown"),
        pytest.param(
            DeviceRecords(records=[DeviceRecord.from_dict(device_record_json("Yuka-LISTED", "iot-listed"))]),
            ["Yuka-LISTED"],
            id="known",
        ),
    ],
)
def test_the_mammotion_device_list_reflects_the_held_records(records: DeviceRecords | None, listed: list[str]) -> None:
    http = MammotionHTTP()
    http.device_records = records
    client = make_bare_client(_session(http))

    assert [d.device_name for d in client.mammotion_device_list] == listed


async def _cache_after_page(status: int, body: dict) -> dict:
    """Fetch the device page on a fresh session, then serialise the client."""
    client = MammotionClient()
    http, _ = make_http_posting(status, body)
    http.mqtt_credentials = MQTT
    await client._account_registry.register(_session(http))  # noqa: SLF001
    await http.get_user_device_page()
    return client.to_cache()


@pytest.mark.regression
@pytest.mark.parametrize("body", EMPTY_PAGE_BODIES)
async def test_an_emptied_device_page_is_written_to_the_cache(body: dict) -> None:
    """``to_cache`` left the records key out for an empty page, and the host's merge kept the removed device."""
    cache = await _cache_after_page(HTTPStatus.OK.value, body)

    assert cache["mammotion_device_records"].records == []


@pytest.mark.regression
@pytest.mark.parametrize(("status", "body"), FAILED_FETCHES)
async def test_a_failed_device_page_leaves_the_cached_records_to_the_host(status: int, body: dict) -> None:
    """A session whose page fetch failed was serialised with ``records=[]``, which the host merged as emptied."""
    cache = await _cache_after_page(status, body)

    assert "mammotion_mqtt" in cache  # the session serialised, so the absent records key means something
    assert "mammotion_device_records" not in cache


@pytest.mark.regression
@pytest.mark.parametrize("body", EMPTY_PAGE_BODIES)
async def test_a_reload_of_an_emptied_account_removes_the_device_restored_from_cache(body: dict) -> None:
    """The restore registers the cached record; the empty page must remove it and say so."""
    client = MammotionClient()
    handle = await _mammotion_handle(client, STALE)
    try:
        http, _ = make_http_posting(HTTPStatus.OK.value, body)
        http.device_records = device_records(STALE)
        http.mqtt_credentials = MQTT
        session = _session(http)
        session.mammotion_transport = make_mock_transport(TransportType.CLOUD_MAMMOTION)
        session.device_ids.add(STALE)
        await client._account_registry.register(session)  # noqa: SLF001
        removed = AsyncMock()
        client.on_device_removed = removed

        await client._bootstrap_mammotion_mqtt(  # noqa: SLF001
            ACCOUNT, http, session, {}, skip_ids=set(session.device_ids)
        )

        assert client._device_registry.get_by_name(STALE) is None  # noqa: SLF001
        removed.assert_awaited_once_with(STALE, f"iot-{STALE}")
        assert client.to_cache()["mammotion_device_records"].records == []
    finally:
        await handle.stop()


async def test_a_failed_shared_device_page_does_not_stop_the_device_page() -> None:
    """Share invitations are best effort; the device page is still fetched and acted on."""
    client = MammotionClient()
    handle = await _mammotion_handle(client, STALE)
    try:
        http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 0, "msg": "success"})
        session = _session(http)
        await client._account_registry.register(session)  # noqa: SLF001
        removed = AsyncMock()
        client.on_device_removed = removed

        with patch.object(http, "get_user_shared_device_page", autospec=True, side_effect=TimeoutError):
            await client._bootstrap_mammotion_mqtt(ACCOUNT, http, session, {})  # noqa: SLF001

        # The empty page was acted on: the device it no longer lists is gone.
        assert client._device_registry.get_by_name(STALE) is None  # noqa: SLF001
        removed.assert_awaited_once_with(STALE, f"iot-{STALE}")
    finally:
        await handle.stop()


async def test_a_device_page_that_raises_keeps_the_restored_devices() -> None:
    """A network error on the device page is not proof the account is empty."""
    client = MammotionClient()
    handle = await _mammotion_handle(client, STALE)
    try:
        http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 0, "msg": "success"})
        session = _session(http)
        await client._account_registry.register(session)  # noqa: SLF001
        removed = AsyncMock()
        client.on_device_removed = removed

        with patch.object(http, "get_user_device_page", autospec=True, side_effect=TimeoutError):
            await client._bootstrap_mammotion_mqtt(ACCOUNT, http, session, {})  # noqa: SLF001

        assert client._device_registry.get_by_name(STALE) is handle  # noqa: SLF001
        removed.assert_not_awaited()
    finally:
        await handle.stop()


async def _restore(
    body: dict,
    status: int = HTTPStatus.OK.value,
    *,
    removed: AsyncMock | None = None,
    persisted: list[list[str]] | None = None,
) -> tuple[MammotionClient, MammotionHTTP, AsyncMock, AsyncMock]:
    """Run the Mammotion MQTT restore over a cached owned ``STALE`` and a shared ``SHARED``.

    *body* is the owned-list response.  *persisted*, if given, collects the held device
    names at each moment the host is asked to rewrite its cache.
    """
    client = MammotionClient()
    http, _ = make_http_posting(status, body)
    http.mqtt_credentials = MQTT
    records = device_records(STALE, SHARED)
    records.records[1].owned = 0
    http.device_records = records
    session = _session(http)
    removed = removed or AsyncMock()
    client.on_device_removed = removed

    async def _persist() -> None:
        if persisted is not None and (held := http.device_records) is not None:
            persisted.append([r.device_name for r in held.records])

    client.on_credentials_updated = _persist
    transport = make_mock_transport(TransportType.CLOUD_MAMMOTION)
    with (
        patch.object(client, "_ensure_token_manager", autospec=True),
        patch.object(client, "_setup_mammotion_transport", autospec=True, return_value=transport),
        patch.object(client, "_register_mammotion_device", autospec=True) as register,
    ):
        await client._restore_mammotion_mqtt(ACCOUNT, session)  # noqa: SLF001
    assert session.mammotion_transport is transport
    return client, http, register, removed


_REGISTER_SIGNATURE = inspect.signature(MammotionClient._register_mammotion_device)  # noqa: SLF001


def _registered(register: AsyncMock) -> list[str]:
    return [c.args[0].device_name for c in register.await_args_list]


async def test_a_restore_with_unknown_records_connects_without_registering_or_dropping() -> None:
    """Nothing is known to register or drop, and the unknown records must stay out of the cache."""
    client = MammotionClient()
    http, _ = make_http_posting(HTTPStatus.OK.value, _owned_list())
    http.mqtt_credentials = MQTT
    assert http.device_records is None
    session = _session(http)
    removed = AsyncMock()
    client.on_device_removed = removed
    transport = make_mock_transport(TransportType.CLOUD_MAMMOTION)
    with (
        patch.object(client, "_ensure_token_manager", autospec=True),
        patch.object(client, "_setup_mammotion_transport", autospec=True, return_value=transport),
        patch.object(client, "_register_mammotion_device", autospec=True) as register,
    ):
        await client._restore_mammotion_mqtt(ACCOUNT, session)  # noqa: SLF001

    assert session.mammotion_transport is transport
    register.assert_not_awaited()
    removed.assert_not_awaited()
    await client._account_registry.register(session)  # noqa: SLF001
    cache = client.to_cache()
    assert "mammotion_mqtt" in cache  # the session serialised, so the absent records key means something
    assert "mammotion_device_records" not in cache


@pytest.mark.regression
async def test_a_restore_drops_a_cached_owned_device_the_account_no_longer_owns() -> None:
    """The restore registered every cached record, so an unbound mower came back until the device page ran."""
    _, http, register, removed = await _restore(_owned_list())

    assert _registered(register) == [SHARED]
    assert http.device_records is not None
    assert [r.device_name for r in http.device_records.records] == [SHARED]
    removed.assert_awaited_once_with(STALE, f"iot-{STALE}")


@pytest.mark.regression
async def test_a_dropped_cached_device_is_written_to_the_cache() -> None:
    """The drop was held only in memory, so it repeated, and notified the host again, on every restore."""
    persisted: list[list[str]] = []

    await _restore(_owned_list(), persisted=persisted)

    assert persisted == [[SHARED]]  # once, after the drop, so the host serialises the pruned list


async def test_a_host_failing_to_remove_a_dropped_device_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """The host's failure used to be suppressed silently, leaving no trace of a device it still shows."""
    with caplog.at_level(logging.WARNING, logger="pymammotion.client"):
        await _restore(_owned_list(), removed=AsyncMock(side_effect=RuntimeError("store")))

    failures = [r for r in caplog.records if r.getMessage() == f"Host failed to remove device '{STALE}'"]
    assert [(r.name, r.levelno) for r in failures] == [("pymammotion.client", logging.WARNING)]
    assert failures[0].exc_info is not None


async def test_a_failed_owned_list_does_not_correct_the_cached_iot_ids() -> None:
    """An error response's devices are not the account's; their iot_ids must not override the cache."""
    body = {"code": 500, "msg": "boom", "data": [{"deviceName": STALE, "iotId": "iot-wrong"}]}
    _, _, register, _ = await _restore(body)

    overrides = [
        _REGISTER_SIGNATURE.bind(None, *c.args, **c.kwargs).arguments["iot_id_override"]
        for c in register.await_args_list
    ]
    assert overrides == ["", ""]


async def test_a_restore_keeps_a_cached_device_the_account_still_owns() -> None:
    _, http, register, removed = await _restore(_owned_list(STALE))

    assert _registered(register) == [STALE, SHARED]
    assert http.device_records is not None
    assert len(http.device_records.records) == 2
    removed.assert_not_awaited()


@pytest.mark.parametrize(("status", "body"), FAILED_FETCHES)
async def test_a_restore_with_a_failed_owned_list_keeps_the_cached_devices(status: int, body: dict) -> None:
    """A failed owned-list fetch answers with ``data=[]``; that is not proof the account is empty."""
    _, http, register, removed = await _restore(body, status)

    assert _registered(register) == [STALE, SHARED]
    assert http.device_records is not None
    assert len(http.device_records.records) == 2
    removed.assert_not_awaited()


_BOOTSTRAP_SIGNATURE = inspect.signature(MammotionClient._bootstrap_mammotion_mqtt)  # noqa: SLF001


@pytest.mark.parametrize(
    ("from_restore", "fetches", "iot_ids"),
    [
        pytest.param([DeviceInfo(device_name=STALE, iot_id="iot-owned")], 0, {STALE: "iot-owned"}, id="handed-over"),
        pytest.param([], 0, {}, id="handed-over-empty"),
        pytest.param(None, 1, {STALE: f"iot-{STALE}"}, id="restore-could-not-fetch"),
    ],
)
async def test_the_bootstrap_gets_the_owned_list_fetched_once(
    from_restore: list[DeviceInfo] | None, fetches: int, iot_ids: dict[str, str]
) -> None:
    """The restore and the new-device check fetched the owned list one after the other.

    When the restore has the list it hands it over; when it could not fetch one, the
    bootstrap still gets a list fetched exactly once.
    """
    client = MammotionClient()
    http, _ = make_http_posting(HTTPStatus.OK.value, _owned_list(STALE))
    cached = {"mammotion_mqtt": {}, "mammotion_device_records": {}}
    try:
        with (
            patch.object(MammotionHTTP, "from_cache", return_value=http),
            patch.object(http, "validate_login", autospec=True, return_value=True),
            patch.object(http, "get_user_device_list", wraps=http.get_user_device_list) as owned_list,
            patch.object(client, "_restore_mammotion_mqtt", autospec=True, return_value=from_restore),
            patch.object(client, "_bootstrap_mammotion_mqtt", autospec=True) as bootstrap,
        ):
            await client.restore_credentials(ACCOUNT, "pw", cached, check_for_new_devices=True)

        assert owned_list.await_count == fetches
        call = bootstrap.await_args
        bound = _BOOTSTRAP_SIGNATURE.bind(client, *call.args, **call.kwargs)
        assert bound.arguments["owned_iot_id_map"] == iot_ids
    finally:
        await client.stop()


@pytest.mark.parametrize("failing", ["get_user_device_list", "get_user_shared_device_page", "get_user_device_page"])
async def test_a_login_survives_a_device_list_fetch_that_raises(failing: str) -> None:
    """These fetches used to propagate, so a blip on any one of them failed the whole login."""
    client = MammotionClient()
    answers = {
        "get_user_device_list": Response(code=0, msg="ok", data=[]),
        "get_user_shared_device_page": Response(code=0, msg="ok"),
        "get_user_device_page": Response(code=0, msg="ok", data=DeviceRecords()),
    }
    try:
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(MammotionHTTP, "login_v2", autospec=True, return_value=Response(code=0, msg="ok"))
            )
            for name, answer in answers.items():
                outcome = {"side_effect": TimeoutError} if name == failing else {"return_value": answer}
                stack.enter_context(patch.object(MammotionHTTP, name, autospec=True, **outcome))
            await client.login_and_initiate_cloud(ACCOUNT, "pw")

        session = client._account_registry.get(ACCOUNT)  # noqa: SLF001
        assert session is not None
        assert session.mammotion_http is not None
    finally:
        await client.stop()
