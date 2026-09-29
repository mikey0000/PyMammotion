"""``MammotionClient.get_latest_work_report`` — the record a "continue last job" action resumes.

Driven through a real ``MammotionHTTP`` (only its aiohttp session is canned) so
the token gate, the 401 detection and the parse are the production ones; the
account's ``TokenManager`` is autospecced because only its reactive refresh is
under test here.
"""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, create_autospec

from aiohttp import ClientConnectionError
import pytest

from pymammotion.auth.token_manager import TokenManager
from pymammotion.client import MammotionClient
from pymammotion.http.model.http import UnauthorizedExceptionError
from pymammotion.transport.base import ReLoginRequiredError
from tests._helpers import make_account_session, make_bare_client, make_mock_handle
from tests.unit._helpers import make_http_posting
from tests.unit.http._helpers import make_work_report_page_body, make_work_report_wire

ACCOUNT = "acct@example.com"
DEVICE = "Luba-VSLKJX"
#: The access token ``make_http_posting`` logs its client in with.
TOKEN = "tok"
UNAUTHORIZED = (HTTPStatus.OK.value, {"code": 401, "msg": "token expired", "data": None})


def _reply(status: int, body: dict) -> MagicMock:
    reply = MagicMock(status=status, headers={"Content-Type": "application/json"})
    reply.json = AsyncMock(return_value=body)
    return reply


async def _client(*replies: tuple[int, dict]) -> tuple[MammotionClient, MagicMock, MagicMock]:
    """A client whose one account owns *DEVICE*; consecutive POSTs answer with *replies*."""
    http, http_session = make_http_posting(HTTPStatus.OK.value, {})
    http_session.post = AsyncMock(side_effect=[_reply(status, body) for status, body in replies])
    token_manager = create_autospec(TokenManager, instance=True)
    session = make_account_session(ACCOUNT, http=http, token_manager=token_manager)
    client = make_bare_client(session)
    await client._device_registry.register(make_mock_handle(device_name=DEVICE), account_id=ACCOUNT)
    return client, http_session, token_manager


async def test_it_returns_the_newest_record() -> None:
    """The server lists newest first and the app resumes ``records[0]``."""
    page = make_work_report_page_body(make_work_report_wire(workId="2"), make_work_report_wire(workId="1"))
    client, http_session, _ = await _client((HTTPStatus.OK.value, page))

    record = await client.get_latest_work_report(DEVICE)

    assert record is not None and record.work_id == "2"
    assert http_session.post.await_args.kwargs["json"]["deviceName"] == DEVICE


async def test_it_returns_none_when_the_device_has_no_jobs() -> None:
    client, _, _ = await _client((HTTPStatus.OK.value, make_work_report_page_body()))

    assert await client.get_latest_work_report(DEVICE) is None


async def test_it_returns_none_when_the_server_answers_with_an_error_code() -> None:
    client, _, _ = await _client((HTTPStatus.OK.value, {"code": 500, "msg": "internal", "data": None}))

    assert await client.get_latest_work_report(DEVICE) is None


async def test_it_returns_none_for_a_device_no_account_owns() -> None:
    client, http_session, _ = await _client()

    assert await client.get_latest_work_report("Luba-UNKNOWN") is None
    http_session.post.assert_not_awaited()


async def test_a_network_error_propagates_rather_than_reading_as_no_jobs() -> None:
    """No refresh is attempted, so nothing can mark the account terminal.

    That a transient error never sets a terminal flag is TokenManager's contract,
    pinned in ``tests/unit/auth/test_token_manager.py::test_transient_network_error_marks_nothing_terminal``.
    """
    client, http_session, token_manager = await _client()
    http_session.post = AsyncMock(side_effect=ClientConnectionError("down"))

    with pytest.raises(ClientConnectionError):
        await client.get_latest_work_report(DEVICE)
    token_manager.refresh_invoke_token.assert_not_awaited()


async def test_a_401_refreshes_the_token_once_and_retries() -> None:
    """The refresh names the token that was rejected, so a concurrent refresh is not repeated."""
    page = make_work_report_page_body(make_work_report_wire(workId="7"))
    client, http_session, token_manager = await _client(UNAUTHORIZED, (HTTPStatus.OK.value, page))

    record = await client.get_latest_work_report(DEVICE)

    assert record is not None and record.work_id == "7"
    token_manager.refresh_invoke_token.assert_awaited_once_with(stale_token=TOKEN)
    assert http_session.post.await_count == 2


async def test_a_second_401_after_the_refresh_propagates() -> None:
    client, http_session, token_manager = await _client(UNAUTHORIZED, UNAUTHORIZED)

    with pytest.raises(UnauthorizedExceptionError):
        await client.get_latest_work_report(DEVICE)
    token_manager.refresh_invoke_token.assert_awaited_once()
    assert http_session.post.await_count == 2, "exactly one retry"


async def test_a_rejected_refresh_propagates_without_a_retry() -> None:
    """Marking the account and firing the reauth callback is TokenManager's job, pinned in
    ``tests/unit/auth/test_token_manager.py::test_reauth_fires_via_refresh_invoke_token_401``."""
    client, http_session, token_manager = await _client(UNAUTHORIZED)
    token_manager.refresh_invoke_token.side_effect = ReLoginRequiredError(ACCOUNT, "refresh token rejected")

    with pytest.raises(ReLoginRequiredError):
        await client.get_latest_work_report(DEVICE)
    assert http_session.post.await_count == 1


async def test_an_account_awaiting_reauth_fails_fast_without_a_request() -> None:
    """TokenManager pushes its terminal flag down to the HTTP login; the endpoint gate honours it."""
    client, http_session, _ = await _client()
    session = client._account_registry.get(ACCOUNT)
    assert session is not None and session.mammotion_http is not None
    session.mammotion_http.mark_reauth_required("refresh token rejected")

    with pytest.raises(ReLoginRequiredError):
        await client.get_latest_work_report(DEVICE)
    http_session.post.assert_not_awaited()


async def test_a_401_without_a_token_manager_propagates() -> None:
    client, http_session, _ = await _client(UNAUTHORIZED)
    session = client._account_registry.get(ACCOUNT)
    assert session is not None
    session.token_manager = None

    with pytest.raises(UnauthorizedExceptionError):
        await client.get_latest_work_report(DEVICE)
    assert http_session.post.await_count == 1


async def test_it_returns_none_when_the_owning_account_has_no_http_login() -> None:
    client, _, _ = await _client()
    session = client._account_registry.get(ACCOUNT)
    assert session is not None
    session.mammotion_http = None

    assert await client.get_latest_work_report(DEVICE) is None


async def test_account_id_picks_that_accounts_login() -> None:
    """A mower shared into two accounts: the named account's bearer token and refresh are used."""
    client, first_post, first_tm = await _client()
    page = make_work_report_page_body(make_work_report_wire(workId="9"))
    other_http, other_post = make_http_posting(HTTPStatus.OK.value, {})
    other_post.post = AsyncMock(side_effect=[_reply(*UNAUTHORIZED), _reply(HTTPStatus.OK.value, page)])
    other_tm = create_autospec(TokenManager, instance=True)
    other = make_account_session("other@example.com", http=other_http, token_manager=other_tm)
    await client._account_registry.register(other)
    await client._device_registry.register(make_mock_handle(device_name=DEVICE), account_id=other.account_id)

    record = await client.get_latest_work_report(DEVICE, account_id=other.account_id)

    assert record is not None and record.work_id == "9"
    other_tm.refresh_invoke_token.assert_awaited_once()
    first_post.post.assert_not_awaited()
    first_tm.refresh_invoke_token.assert_not_awaited()
