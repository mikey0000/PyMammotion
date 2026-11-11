"""The device-list fetch helpers in ``client_auth``: a failed fetch is ``None``, a rejected login is not.

A network or server failure must not read as an empty account, so each helper turns
it into ``None`` (or, for share invitations, does nothing).  An auth rejection is a
signal the host must see, so it always propagates.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any
from unittest.mock import patch

import pytest

from pymammotion.client_auth import (
    _accept_pending_mammotion_shares,
    _fetch_mammotion_device_page,
    _fetch_owned_devices,
)
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import UnauthorizedExceptionError
from tests.unit._helpers import device_record_json, device_records, make_http_posting

HELD = "Luba-HELD"

#: Each helper with the MammotionHTTP call it wraps.
HELPERS = [
    pytest.param(_fetch_owned_devices, "get_user_device_list", id="owned-list"),
    pytest.param(_fetch_mammotion_device_page, "get_user_device_page", id="device-page"),
    pytest.param(_accept_pending_mammotion_shares, "get_user_shared_device_page", id="shares"),
]


@pytest.mark.parametrize(("helper", "wrapped"), HELPERS)
async def test_a_raising_fetch_is_not_an_answer(
    helper: Callable[[MammotionHTTP], Awaitable[Any]], wrapped: str
) -> None:
    http, _ = make_http_posting(HTTPStatus.OK.value, {})

    with patch.object(http, wrapped, autospec=True, side_effect=TimeoutError):
        assert await helper(http) is None


@pytest.mark.parametrize(("helper", "wrapped"), HELPERS)
async def test_a_rejected_login_propagates(helper: Callable[[MammotionHTTP], Awaitable[Any]], wrapped: str) -> None:
    """Swallowing it would let a restore report success on a session the server has invalidated."""
    http, _ = make_http_posting(HTTPStatus.OK.value, {})

    with (
        patch.object(http, wrapped, autospec=True, side_effect=UnauthorizedExceptionError("401")),
        pytest.raises(UnauthorizedExceptionError),
    ):
        await helper(http)


async def test_an_error_page_that_still_carries_records_is_not_an_answer() -> None:
    """The server can attach a page to an error code; those records are not the account's."""
    body = {
        "code": 500,
        "msg": "boom",
        "data": {"records": [device_record_json("Luba-WRONG", "iot-wrong")], "total": 1, "size": 100, "current": 1},
    }
    http, _ = make_http_posting(HTTPStatus.OK.value, body)
    http.device_records = device_records(HELD)

    assert await _fetch_mammotion_device_page(http) is None
    assert http.device_records is not None
    assert [r.device_name for r in http.device_records.records] == [HELD]
