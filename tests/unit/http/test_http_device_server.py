"""The ``device-server/v1`` endpoints: the paged error-code table and the product list.

These sit under a different prefix from the rest of the client — the CSV export in
``get_all_error_codes`` is ``user-server`` — and they share one POST helper, so their
tests share a module.

The paged code endpoint is richer than the CSV export: each record nests every
language and carries the display hints and product keys.  It is not, however, a
richer *code* list — run against a live account it returns the same 469 codes.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.http.model.http import UnauthorizedExceptionError
from tests.unit._helpers import make_http_posting

PAGE_SIZE = 2


def _record(code: str) -> dict:
    return {
        "code": code,
        "description": f"desc {code}",
        "level": "3",
        "module": "navigation",
        "showType": "1",
        "showWork": "0",
        "showTime": "1",
        "productKeys": ["ATyVu9QkAdX"],
        "handleList": [{"language": "en", "implication": f"imp {code}", "solution": f"sol {code}"}],
    }


def _page(*codes: str) -> dict:
    return {"code": 0, "msg": "success", "data": {"records": [_record(c) for c in codes], "size": PAGE_SIZE}}


def _responses(http_session: MagicMock, pages: list[dict], statuses: list[int] | None = None) -> None:
    """Make consecutive POSTs return consecutive *pages*."""
    replies = []
    for index, page in enumerate(pages):
        status = (statuses or [])[index] if statuses and index < len(statuses) else HTTPStatus.OK.value
        reply = MagicMock(status=status, headers={"Content-Type": "application/json"})
        reply.json = AsyncMock(return_value=page)
        replies.append(reply)
    http_session.post = AsyncMock(side_effect=replies)


async def test_a_page_parses_into_records_with_their_translations() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _page("1005"))

    response = await http.get_error_codes_page(page_number=1, page_size=PAGE_SIZE)

    assert response.code == 0
    assert response.data is not None
    record = response.data.records[0]
    assert record.code == "1005"
    assert record.show_type == "1", "camelCase showType must map onto show_type"
    assert record.product_keys == ["ATyVu9QkAdX"]
    assert (handle := record.text("en")) is not None and handle.implication == "imp 1005"
    assert record.text("ja") is None, "a language the record lacks is absent, not blank"


async def test_a_page_request_sends_the_paging_body_the_app_sends() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _page("1005"))

    await http.get_error_codes_page(page_number=3, page_size=50)

    assert session.post.await_args.kwargs["json"] == {"pageNumber": 3, "pageSize": 50}
    assert session.post.await_args.args[0].endswith("/device-server/v1/code/page-lan")


async def test_paging_walks_until_a_short_page() -> None:
    """The page counters are inconsistent across this API, so a short page is the signal."""
    http, session = make_http_posting(HTTPStatus.OK.value, {})
    _responses(session, [_page("1", "2"), _page("3", "4"), _page("5")])

    collected = await http.get_all_error_codes_paged(page_size=PAGE_SIZE)

    assert sorted(collected) == ["1", "2", "3", "4", "5"]
    assert session.post.await_count == 3, "a short page must end the walk"


async def test_paging_stops_on_an_empty_page() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, {})
    _responses(session, [_page("1", "2"), {"code": 0, "msg": "success", "data": {"records": []}}])

    collected = await http.get_all_error_codes_paged(page_size=PAGE_SIZE)

    assert sorted(collected) == ["1", "2"]
    assert session.post.await_count == 2


async def test_a_failing_page_returns_what_was_already_collected() -> None:
    """A mid-table 5xx should degrade to a partial table, not lose the whole walk."""
    http, session = make_http_posting(HTTPStatus.OK.value, {})
    _responses(session, [_page("1", "2")], statuses=[HTTPStatus.OK.value])
    broken = MagicMock(status=HTTPStatus.INTERNAL_SERVER_ERROR.value, headers={"Content-Type": "application/json"})
    broken.json = AsyncMock(return_value={"code": 500, "msg": "boom"})
    session.post = AsyncMock(side_effect=[list(session.post.side_effect)[0], broken])

    collected = await http.get_all_error_codes_paged(page_size=PAGE_SIZE)

    assert sorted(collected) == ["1", "2"]


async def test_a_401_is_raised_rather_than_returned() -> None:
    """A rejected session must not look like an empty table — see CLAUDE.md."""
    http, _ = make_http_posting(HTTPStatus.UNAUTHORIZED.value, {"code": 401, "msg": "unauthorized"})

    with pytest.raises(UnauthorizedExceptionError):
        await http.get_error_codes_page()


async def test_the_version_endpoint_parses() -> None:
    """``data`` is a bare version string, not an object — confirmed against a live account."""
    http, session = make_http_posting(
        HTTPStatus.OK.value, {"code": 0, "msg": "success", "data": "17"}
    )

    response = await http.get_error_code_version()

    assert response.data is not None and response.data == "17"
    assert session.post.await_args.args[0].endswith("/device-server/v1/code/version")


async def test_the_product_list_parses_keys_and_their_models() -> None:
    """A GET, unlike the code endpoints; ``data`` is a bare list and empty models are normal."""
    body = {
        "code": 0,
        "msg": "Request success",
        "data": [
            {
                "productKey": "a1K4Ki2L5rK",
                "productModelVos": [
                    {"intMod": "HM050080LBAWD50", "intId": "0", "extMod": "LubaAWD5000"},
                    {"intMod": "HM060100LBAWD50OMNIH", "intId": "4", "extMod": "LubaAWD5000H"},
                ],
            },
            {"productKey": "a1jOhAYOIG8", "productModelVos": []},
        ],
    }
    http, session = make_http_posting(HTTPStatus.OK.value, body)

    response = await http.get_product_list()

    assert response.data is not None
    assert [product.product_key for product in response.data] == ["a1K4Ki2L5rK", "a1jOhAYOIG8"]
    assert [model.int_id for model in response.data[0].models] == ["0", "4"]
    assert response.data[1].models == [], "a product with no models must parse, not raise"
    assert session.get.await_args.args[0].endswith("/device-server/v1/product/product/list")
    session.post.assert_not_awaited()  # the product list is a GET


async def test_a_401_on_the_product_list_is_raised() -> None:
    http, _ = make_http_posting(HTTPStatus.UNAUTHORIZED.value, {"code": 401, "msg": "unauthorized"})

    with pytest.raises(UnauthorizedExceptionError):
        await http.get_product_list()


async def test_a_page_returning_more_rows_than_asked_for_terminates() -> None:
    """A short page is not the only exit: a server can ignore page_size, or paging itself.

    The walk used to end only on ``len(records) < page_size``, so a server answering
    every request with the same full page spun forever, allocating as it went.
    """
    http, session = make_http_posting(HTTPStatus.OK.value, {})
    _responses(session, [_page("1", "2", "3")] * 8)

    collected = await asyncio.wait_for(http.get_all_error_codes_paged(page_size=PAGE_SIZE), timeout=5)

    assert sorted(collected) == ["1", "2", "3"]
    assert session.post.await_count == 2, "the second page added nothing new and must end the walk"


async def test_an_in_body_401_is_raised_like_a_status_401() -> None:
    """The server uses either; a Response(401) would look like an empty table."""
    http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 401, "msg": "unauthorized"})

    with pytest.raises(UnauthorizedExceptionError):
        await http.get_error_codes_page()


async def test_a_401_from_the_get_path_is_raised_too() -> None:
    """The verb split must not lose the auth check — both paths share the same guard."""
    http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 401, "msg": "unauthorized"})

    with pytest.raises(UnauthorizedExceptionError):
        await http.get_product_list()
