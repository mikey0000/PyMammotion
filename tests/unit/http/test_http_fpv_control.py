"""``MammotionHTTP.request_fpv_control_token`` / ``refresh_fpv_control_token`` — the remote-drive control token.

Mirrors ``FpvDriveApiService`` in app 2.3.20.30: two ``device-server/v1/fpv/control`` POSTs whose
body is ``FpvControlReq`` with Gson's null-dropping (``deviceId`` alone to request, plus ``token``
to refresh).  Both go through the shared device-server helper, so a dead login raises rather
than coming back as a ``Response(code=401)`` that would read as "control unavailable".
"""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus

import pytest

from pymammotion.http.model.http import UnauthorizedExceptionError
from tests.unit._helpers import make_http_posting

IOT_ID = "iot-123"

_GRANT_BODY = {
    "code": 0,
    "msg": "success",
    "data": {"deviceResult": 0, "token": "ctl-tok", "expireIn": 600, "timeoutExit": 10, "latencyThreshold": 1500},
}


async def test_a_token_request_posts_the_device_id_alone() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _GRANT_BODY)

    await http.request_fpv_control_token(IOT_ID)

    assert session.post.await_args.args[0].endswith("/device-server/v1/fpv/control/token")
    assert session.post.await_args.kwargs["json"] == {"deviceId": IOT_ID}
    assert session.post.await_args.kwargs["headers"]["Authorization"] == "Bearer tok"


async def test_a_refresh_posts_the_device_id_and_the_current_control_token() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _GRANT_BODY)

    await http.refresh_fpv_control_token(IOT_ID, "old-ctl")

    assert session.post.await_args.args[0].endswith("/device-server/v1/fpv/control/refresh-token")
    assert session.post.await_args.kwargs["json"] == {"deviceId": IOT_ID, "token": "old-ctl"}


async def test_a_grant_parses_into_the_control_model() -> None:
    http, _ = make_http_posting(HTTPStatus.OK.value, _GRANT_BODY)

    response = await http.request_fpv_control_token(IOT_ID)

    assert response.code == 0
    assert response.data is not None
    assert (response.data.token, response.data.expire_in, response.data.latency_threshold) == ("ctl-tok", 600, 1500)


_CALLS = {
    "request": lambda http: http.request_fpv_control_token(IOT_ID),
    "refresh": lambda http: http.refresh_fpv_control_token(IOT_ID, "old-ctl"),
}


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (HTTPStatus.UNAUTHORIZED.value, {"code": 401, "msg": "unauthorized"}),
        (HTTPStatus.OK.value, {"code": 401, "msg": "unauthorized"}),
    ],
    ids=["status-401", "in-body-401"],
)
@pytest.mark.parametrize("call", _CALLS.values(), ids=_CALLS.keys())
async def test_a_401_is_raised_rather_than_returned(status: int, body: dict, call: Callable) -> None:
    http, _ = make_http_posting(status, body)

    with pytest.raises(UnauthorizedExceptionError):
        await call(http)


@pytest.mark.parametrize("call", _CALLS.values(), ids=_CALLS.keys())
async def test_a_non_json_body_comes_back_as_a_failed_response(call: Callable) -> None:
    http, _ = make_http_posting(HTTPStatus.BAD_GATEWAY.value, {}, content_type="text/html")

    response = await call(http)

    assert (response.code, response.data) == (HTTPStatus.BAD_GATEWAY.value, None)


@pytest.mark.parametrize("call", _CALLS.values(), ids=_CALLS.keys())
async def test_a_server_error_comes_back_as_a_failed_response(call: Callable) -> None:
    http, _ = make_http_posting(HTTPStatus.INTERNAL_SERVER_ERROR.value, {"code": 500, "msg": "boom"})

    response = await call(http)

    assert response.code == HTTPStatus.INTERNAL_SERVER_ERROR.value
    assert response.data is None
