"""How TokenManager treats a ``RateLimitedError`` (an auth endpoint's HTTP 429) on every refresh path.

A throttle is neither a rejected login nor a network blip: it must not set
``reauth_required`` or a transport give-up flag, must reach the caller as itself,
and the scheduler waits out the cooldown instead of its short retry timer.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import time_machine

from pymammotion.auth import token_manager as token_manager_module
from pymammotion.auth.token_manager import TokenManager
from pymammotion.http.model.http import RateLimitedError
from pymammotion.transport.base import SessionExpiredError, TransportType
from tests._helpers import let_others_run, wait_until
from tests.unit.auth._helpers import make_aliyun_gateway, make_http_mock

_COOLDOWN = 3600.0


def _throttle(endpoint: str = "oauth2/token", retry_after: float = _COOLDOWN) -> RateLimitedError:
    return RateLimitedError(endpoint, retry_after)


def _tm(http: AsyncMock) -> TokenManager:
    return TokenManager(account_id="user@example.com", mammotion_http=http)


def _assert_nothing_terminal(tm: TokenManager, http: AsyncMock) -> None:
    assert tm.reauth_required is None, "a throttle marked the login dead"
    assert tm.unavailable_transports == {}, "a throttle gave a transport up"
    http.mark_reauth_required.assert_not_called()
    http.login_v2.assert_not_awaited()


@pytest.mark.regression
async def test_refresh_http_raises_rate_limited_without_marking_the_login_dead() -> None:
    """A non-transient refresh failure was read as a rejected refresh token and prompted for the password."""
    http = make_http_mock(login_info=MagicMock())
    http.refresh_token_v2.side_effect = _throttle()
    tm = _tm(http)

    with pytest.raises(RateLimitedError):
        await tm.refresh_http()

    _assert_nothing_terminal(tm, http)


@pytest.mark.regression
async def test_refresh_mqtt_raises_rate_limited_without_giving_the_transport_up() -> None:
    """A throttled JWT fetch gave Mammotion MQTT up for good, although waiting would have cured it."""
    http = make_http_mock(login_info=MagicMock())
    http.get_mqtt_credentials.side_effect = _throttle("mqtt/auth/jwt")
    tm = _tm(http)

    with pytest.raises(RateLimitedError):
        await tm.refresh_mqtt_credentials()

    _assert_nothing_terminal(tm, http)


@pytest.mark.regression
async def test_refresh_aliyun_raises_rate_limited_without_giving_the_transport_up() -> None:
    """A throttled authorization code during a 2401 rebuild gave the Aliyun transport up for good."""
    http = make_http_mock(login_info=MagicMock())
    http.refresh_authorization_token.side_effect = _throttle("authorization/code")
    gateway = make_aliyun_gateway(http=http, issued_at=int(time.time()))
    gateway.check_or_refresh_session.side_effect = SessionExpiredError(TransportType.CLOUD_ALIYUN, "2401")
    tm = TokenManager("user@example.com", http, gateway)

    with pytest.raises(RateLimitedError):
        await tm.refresh_aliyun_credentials()

    _assert_nothing_terminal(tm, http)


@pytest.mark.regression
async def test_recover_aliyun_defers_a_throttled_session_until_the_cooldown_ends() -> None:
    """A restore whose Aliyun chain was throttled gave the transport up instead of trying again later."""
    http = make_http_mock(login_info=MagicMock())
    http.expires_in = time.time() + 86400
    http.refresh_authorization_token.side_effect = _throttle("authorization/code")
    tm = _tm(http)

    with time_machine.travel(time.time(), tick=False):
        assert await tm.recover_aliyun(make_aliyun_gateway(http=http)) is None

        assert tm.seconds_until_next_refresh == pytest.approx(_COOLDOWN)
    _assert_nothing_terminal(tm, http)


@pytest.mark.regression
async def test_refresh_invoke_token_raises_rate_limited_without_marking_the_login_dead() -> None:
    """A throttled bearer refresh after an invoke 401 marked the login dead and gave Mammotion MQTT up."""
    http = make_http_mock(login_info=MagicMock(access_token="tok"))
    http.refresh_token_v2.side_effect = _throttle()
    tm = _tm(http)

    with pytest.raises(RateLimitedError):
        await tm.refresh_invoke_token(stale_token="tok")

    _assert_nothing_terminal(tm, http)


@pytest.mark.regression
async def test_refresh_invoke_token_survives_a_throttled_authorization_code() -> None:
    """The bearer was renewed, then a throttled code fetch escaped and failed the retry it had made possible."""
    http = make_http_mock(refresh_code=0, login_info=MagicMock(access_token="tok"))
    http.fetch_authorization_token.side_effect = _throttle("authorization/code")
    tm = _tm(http)

    await tm.refresh_invoke_token(stale_token="tok")

    http.refresh_token_v2.assert_awaited_once()
    _assert_nothing_terminal(tm, http)


def _scheduled_with_a_due_throttled_token(retry_after: float) -> tuple[TokenManager, AsyncMock]:
    http = make_http_mock(login_info=MagicMock(access_token="tok", refresh_token="ref"))
    http.expires_in = time.time() + 60  # inside the 300 s lead, so the first pass refreshes
    http.refresh_token_v2.side_effect = _throttle(retry_after=retry_after)
    return _tm(http), http


@pytest.mark.regression
async def test_scheduler_does_not_retry_a_throttle_on_its_short_retry_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    """A throttle fell into the transient branch and was retried every retry interval for as long as it lasted."""
    monkeypatch.setattr(token_manager_module, "_SCHEDULER_RETRY_DELAY", 0.0)
    tm, http = _scheduled_with_a_due_throttled_token(retry_after=_COOLDOWN)

    tm.start_refresh_scheduler()
    try:
        await wait_until(lambda: http.refresh_token_v2.await_count == 1)
        await let_others_run(50)
        assert http.refresh_token_v2.await_count == 1, "the scheduler retried inside the cooldown"
    finally:
        await tm.stop_refresh_scheduler()

    _assert_nothing_terminal(tm, http)


async def test_scheduler_tries_again_once_the_cooldown_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the retry timer out of reach, a second attempt can only come from waiting out ``retry_after``."""
    monkeypatch.setattr(token_manager_module, "_SCHEDULER_RETRY_DELAY", 86400.0)
    tm, http = _scheduled_with_a_due_throttled_token(retry_after=0.0)

    tm.start_refresh_scheduler()
    try:
        await wait_until(lambda: http.refresh_token_v2.await_count >= 2)
    finally:
        await tm.stop_refresh_scheduler()

    _assert_nothing_terminal(tm, http)
