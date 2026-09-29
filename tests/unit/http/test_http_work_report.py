"""``MammotionHTTP.get_work_report_page`` — the app's job history, newest first.

The app reads ``records[0]`` of this page to offer "continue last job"
(``HomeViewModel.getWorkReportData``); it goes through the shared
``device-server/v1`` helper, so a dead token must raise, never come back as a
``Response(code=401)`` that reads as "no jobs".
"""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

from aiohttp import ClientConnectionError
import pytest

from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import UnauthorizedExceptionError
from tests.unit._helpers import make_http_posting
from tests.unit.http._helpers import make_work_report_page_body, make_work_report_wire

DEVICE = "Luba-VSLKJX"


async def test_the_request_is_the_one_the_app_sends() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, make_work_report_page_body())

    await http.get_work_report_page(DEVICE, page_number=2, page_size=5)

    assert session.post.await_args.args[0].endswith("/device-server/v1/device/work-report/page")
    assert session.post.await_args.kwargs["json"] == {"deviceName": DEVICE, "pageNumber": 2, "pageSize": 5}
    assert session.post.await_args.kwargs["headers"]["Authorization"] == "Bearer tok"


async def test_the_default_page_is_the_first_ten_like_the_app_report_list() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, make_work_report_page_body())

    await http.get_work_report_page(DEVICE)

    assert session.post.await_args.kwargs["json"] == {"deviceName": DEVICE, "pageNumber": 1, "pageSize": 10}


async def test_a_page_parses_into_records() -> None:
    body = make_work_report_page_body(make_work_report_wire(), make_work_report_wire(workId=""))
    http, _ = make_http_posting(HTTPStatus.OK.value, body)

    response = await http.get_work_report_page(DEVICE)

    assert response.code == 0
    assert response.data is not None
    assert [r.work_id for r in response.data.records] == ["1727600000123", ""]


async def test_an_empty_page_has_no_records() -> None:
    http, _ = make_http_posting(HTTPStatus.OK.value, make_work_report_page_body())

    response = await http.get_work_report_page(DEVICE)

    assert response.data is not None and response.data.records == []


async def test_a_null_data_parses_as_no_page() -> None:
    """The server's refusal shape: the reason in ``code``/``msg``, ``data: null``."""
    http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 500, "msg": "internal", "data": None})

    response = await http.get_work_report_page(DEVICE)

    assert (response.code, response.data) == (500, None)


async def test_a_401_status_raises() -> None:
    http, _ = make_http_posting(HTTPStatus.UNAUTHORIZED.value, {"code": 401, "msg": "unauthorized"})

    with pytest.raises(UnauthorizedExceptionError):
        await http.get_work_report_page(DEVICE)
    assert http.reauth_required is None, "a 401 is a refresh signal; only a rejected refresh is terminal"


async def test_a_401_in_the_body_raises_even_under_a_200() -> None:
    http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 401, "msg": "token expired", "data": None})

    with pytest.raises(UnauthorizedExceptionError):
        await http.get_work_report_page(DEVICE)
    assert http.reauth_required is None, "a 401 is a refresh signal; only a rejected refresh is terminal"


async def test_a_network_error_propagates_and_leaves_the_login_usable() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, make_work_report_page_body())
    session.post.side_effect = ClientConnectionError("down")

    with pytest.raises(ClientConnectionError):
        await http.get_work_report_page(DEVICE)
    assert http.reauth_required is None


async def test_the_token_is_checked_before_the_request_like_its_siblings() -> None:
    """Same ``refresh_token_decorator`` gate as the other device-server calls."""
    http, _ = make_http_posting(HTTPStatus.OK.value, make_work_report_page_body())

    with patch.object(MammotionHTTP, "ensure_token_valid", autospec=True) as ensure:
        await http.get_work_report_page(DEVICE)

    ensure.assert_awaited_once()
