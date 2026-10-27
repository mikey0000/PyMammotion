"""The account's device lists replace what was held, including when the account is emptied.

``get_user_device_page`` and ``get_user_device_list`` used to keep the previous list
whenever a response carried no data (``response.data or self.<list>``).  An account
whose last device was removed answers with no data, so the removed device stayed in
``device_records``, was written back to the host's cache, and was registered again
on every restore — a mower the user could never remove.
"""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import DeviceInfo, DeviceRecord, DeviceRecords, MQTTConnection
from pymammotion.transport.base import TransportAvailability, TransportType
from tests._helpers import make_mock_handle, make_mock_transport
from tests.unit._helpers import make_http_posting

ACCOUNT = "user@test.com"
STALE = "Luba-VAME9R5S"

#: The shapes an account with no devices can answer in: no ``data`` at all (what
#: the fake server's ``_ok()`` sends for an empty payload), ``data: null``, and an
#: empty page.
EMPTY_PAGE_BODIES = [
    pytest.param({"code": 0, "msg": "success"}, id="no-data"),
    pytest.param({"code": 0, "msg": "success", "data": None}, id="null-data"),
    pytest.param(
        {"code": 0, "msg": "success", "data": {"records": [], "total": 0, "size": 100, "current": 1, "pages": 0}},
        id="empty-records",
    ),
]

EMPTY_LIST_BODIES = [
    pytest.param({"code": 0, "msg": "success"}, id="no-data"),
    pytest.param({"code": 0, "msg": "success", "data": None}, id="null-data"),
    pytest.param({"code": 0, "msg": "success", "data": []}, id="empty-list"),
]


def _record_json(device_name: str, iot_id: str) -> dict:
    """Build a device-page record in the shape the server sends (see ``DeviceRecord``)."""
    return {
        "identityId": "819056836211638272",
        "iotId": iot_id,
        "productKey": "ATyVu9QkAdX",
        "deviceName": device_name,
        "owned": 1,
        "bindTime": 1780498106000,
        "createTime": "2026-06-03T14:48:26",
    }


def _stale_records() -> DeviceRecords:
    return DeviceRecords(
        records=[DeviceRecord.from_dict(_record_json(STALE, "iot-stale"))],
        total=1,
        size=100,
        current=1,
        pages=1,
    )


@pytest.mark.regression
@pytest.mark.parametrize("body", EMPTY_PAGE_BODIES)
async def test_an_emptied_account_clears_the_held_device_records(body: dict) -> None:
    """``response.data or self.device_records`` kept the removed device when the page had no data."""
    http, _ = make_http_posting(HTTPStatus.OK.value, body)
    http.device_records = _stale_records()

    response = await http.get_user_device_page()

    assert response.data is not None
    assert response.data.records == []
    assert http.device_records.records == []


async def test_a_listed_device_replaces_the_held_device_records() -> None:
    http, _ = make_http_posting(
        HTTPStatus.OK.value,
        {
            "code": 0,
            "msg": "success",
            "data": {
                "records": [_record_json("Luba-NEW", "iot-new")],
                "total": 1,
                "size": 100,
                "current": 1,
                "pages": 1,
            },
        },
    )
    http.device_records = _stale_records()

    await http.get_user_device_page()

    assert [r.device_name for r in http.device_records.records] == ["Luba-NEW"]


@pytest.mark.parametrize(
    ("status", "body"),
    [
        pytest.param(HTTPStatus.INTERNAL_SERVER_ERROR.value, {"code": 500, "msg": "boom"}, id="http-error"),
        pytest.param(HTTPStatus.OK.value, {"code": 500, "msg": "boom"}, id="in-body-error"),
    ],
)
async def test_a_failed_device_page_keeps_the_held_device_records(status: int, body: dict) -> None:
    """A failed fetch is not proof the account is empty, so it must not clear the records."""
    http, _ = make_http_posting(status, body)
    http.device_records = _stale_records()

    response = await http.get_user_device_page()

    assert response.data is None
    assert [r.device_name for r in http.device_records.records] == [STALE]


@pytest.mark.regression
@pytest.mark.parametrize("body", EMPTY_LIST_BODIES)
async def test_an_emptied_account_clears_the_held_owned_devices(body: dict) -> None:
    """``response.data or self.device_info`` kept the removed device for an empty or missing list."""
    http, _ = make_http_posting(HTTPStatus.OK.value, body)
    http.device_info = [DeviceInfo(device_name=STALE, iot_id="iot-stale")]

    response = await http.get_user_device_list()

    assert response.data == []
    assert http.device_info == []


async def test_a_failed_owned_device_list_keeps_the_held_owned_devices() -> None:
    http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 500, "msg": "boom"})
    held = [DeviceInfo(device_name=STALE, iot_id="iot-stale")]
    http.device_info = held

    await http.get_user_device_list()

    assert http.device_info == held


@pytest.mark.regression
async def test_an_emptied_device_page_is_written_to_the_cache() -> None:
    """The host merges the cache into what it stored, so a missing key keeps the old records."""
    client = MammotionClient()
    http = MammotionHTTP()
    http.mqtt_credentials = MQTTConnection(host="h", jwt="j", client_id="c", username="u")
    http.device_records = DeviceRecords()
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.mammotion_http = http
    await client._account_registry.register(session)  # noqa: SLF001

    cache = client.to_cache()

    assert cache["mammotion_device_records"].records == []


@pytest.mark.regression
@pytest.mark.parametrize("body", EMPTY_PAGE_BODIES)
async def test_a_reload_of_an_emptied_account_removes_the_device_restored_from_cache(body: dict) -> None:
    """The restore registers the cached record; the empty page must remove it and say so."""
    client = MammotionClient()
    handle = make_mock_handle(STALE, STALE)
    handle.iot_id = "iot-stale"
    await handle.add_transport(
        make_mock_transport(TransportType.CLOUD_MAMMOTION, availability=TransportAvailability.UNKNOWN)
    )
    try:
        await client._device_registry.register(handle, ACCOUNT)  # noqa: SLF001
        http, _ = make_http_posting(HTTPStatus.OK.value, body)
        http.device_records = _stale_records()
        http.mqtt_credentials = MQTTConnection(host="h", jwt="j", client_id="c", username="u")
        http.get_user_shared_device_page = AsyncMock(return_value=MagicMock(data=None))  # type: ignore[method-assign]
        session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
        session.mammotion_http = http
        session.mammotion_transport = make_mock_transport(TransportType.CLOUD_MAMMOTION)
        session.device_ids.add(STALE)
        await client._account_registry.register(session)  # noqa: SLF001
        removed = AsyncMock()
        client.on_device_removed = removed

        await client._bootstrap_mammotion_mqtt(ACCOUNT, http, session, {}, skip_ids=set(session.device_ids))  # noqa: SLF001

        assert client._device_registry.get_by_name(STALE) is None  # noqa: SLF001
        removed.assert_awaited_once_with(STALE, "iot-stale")
        assert client.to_cache()["mammotion_device_records"].records == []
    finally:
        await handle.stop()


def _owned_list(*names: str) -> dict:
    return {"code": 0, "msg": "success", "data": [{"deviceName": n, "iotId": f"iot-{n}"} for n in names]}


async def _restore(
    body: dict, status: int = HTTPStatus.OK.value
) -> tuple[MammotionClient, MammotionHTTP, AsyncMock, AsyncMock]:
    """Run the Mammotion MQTT restore over a cached owned ``STALE`` and a shared ``Luba-SHARED``."""
    client = MammotionClient()
    http, _ = make_http_posting(status, body)
    http.mqtt_credentials = MQTTConnection(host="h", jwt="j", client_id="c", username="u")
    shared = _record_json("Luba-SHARED", "iot-shared") | {"owned": 0}
    http.device_records = DeviceRecords(
        records=[DeviceRecord.from_dict(_record_json(STALE, "iot-stale")), DeviceRecord.from_dict(shared)],
        total=2,
        size=100,
        current=1,
        pages=1,
    )
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.mammotion_http = http
    removed = AsyncMock()
    client.on_device_removed = removed
    transport = make_mock_transport(TransportType.CLOUD_MAMMOTION)
    with (
        patch.object(client, "_ensure_token_manager", AsyncMock()),
        patch.object(client, "_setup_mammotion_transport", return_value=transport),
        patch.object(client, "_register_mammotion_device", AsyncMock()) as register,
    ):
        await client._restore_mammotion_mqtt(ACCOUNT, session)  # noqa: SLF001
    return client, http, register, removed


@pytest.mark.regression
async def test_a_restore_drops_a_cached_owned_device_the_account_no_longer_owns() -> None:
    """The restore registered every cached record, so an unbound mower came back until the device page ran."""
    _, http, register, removed = await _restore(_owned_list())

    assert [c.args[0].device_name for c in register.await_args_list] == ["Luba-SHARED"]
    assert [r.device_name for r in http.device_records.records] == ["Luba-SHARED"]
    removed.assert_awaited_once_with(STALE, "iot-stale")


async def test_a_restore_keeps_a_cached_device_the_account_still_owns() -> None:
    _, http, register, removed = await _restore(_owned_list(STALE))

    assert [c.args[0].device_name for c in register.await_args_list] == [STALE, "Luba-SHARED"]
    assert len(http.device_records.records) == 2
    removed.assert_not_awaited()


@pytest.mark.parametrize(
    ("status", "body"),
    [
        pytest.param(HTTPStatus.INTERNAL_SERVER_ERROR.value, {"code": 500, "msg": "boom"}, id="http-error"),
        pytest.param(HTTPStatus.OK.value, {"code": 500, "msg": "boom"}, id="in-body-error"),
    ],
)
async def test_a_restore_with_a_failed_owned_list_keeps_the_cached_devices(status: int, body: dict) -> None:
    """A failed owned-list fetch answers with ``data=[]``; that is not proof the account is empty."""
    _, http, register, removed = await _restore(body, status)

    assert [c.args[0].device_name for c in register.await_args_list] == [STALE, "Luba-SHARED"]
    assert len(http.device_records.records) == 2
    removed.assert_not_awaited()
