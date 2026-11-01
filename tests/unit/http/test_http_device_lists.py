"""The account's device lists replace what was held, including when the account is emptied.

``get_user_device_page`` and ``get_user_device_list`` used to keep the previous list
whenever a response carried no data (``response.data or self.<list>``).  An account
whose last device was removed answers with no data, so the removed device stayed in
``device_records``, was written back to the host's cache, and was registered again
on every restore — a mower the user could never remove.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest

from pymammotion.http.model.http import DeviceInfo
from tests.unit._helpers import (
    EMPTY_PAGE_BODIES,
    FAILED_FETCHES,
    device_record_json,
    device_records,
    make_http_posting,
)

STALE = "Luba-VAME9R5S"

EMPTY_LIST_BODIES = [
    pytest.param({"code": 0, "msg": "success"}, id="no-data"),
    pytest.param({"code": 0, "msg": "success", "data": None}, id="null-data"),
    pytest.param({"code": 0, "msg": "success", "data": []}, id="empty-list"),
]


@pytest.mark.regression
@pytest.mark.parametrize("body", EMPTY_PAGE_BODIES)
async def test_an_emptied_account_clears_the_held_device_records(body: dict) -> None:
    """``response.data or self.device_records`` kept the removed device when the page had no data."""
    http, _ = make_http_posting(HTTPStatus.OK.value, body)
    http.device_records = device_records(STALE)

    response = await http.get_user_device_page()

    assert response.data is not None
    assert response.data.records == []
    assert http.device_records is not None
    assert http.device_records.records == []


async def test_a_listed_device_replaces_the_held_device_records() -> None:
    http, _ = make_http_posting(
        HTTPStatus.OK.value,
        {
            "code": 0,
            "msg": "success",
            "data": {
                "records": [device_record_json("Luba-NEW", "iot-new")],
                "total": 1,
                "size": 100,
                "current": 1,
                "pages": 1,
            },
        },
    )
    http.device_records = device_records(STALE)

    await http.get_user_device_page()

    assert http.device_records is not None
    assert [r.device_name for r in http.device_records.records] == ["Luba-NEW"]


@pytest.mark.parametrize(("status", "body"), FAILED_FETCHES)
async def test_a_failed_device_page_keeps_the_held_device_records(status: int, body: dict) -> None:
    """A failed fetch is not proof the account is empty, so it must not clear the records."""
    http, _ = make_http_posting(status, body)
    http.device_records = device_records(STALE)

    response = await http.get_user_device_page()

    assert response.data is None
    assert http.device_records is not None
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
