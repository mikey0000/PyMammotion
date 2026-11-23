"""MammotionHTTP's handling of an HTTP 429 from the auth endpoints (oauth2/token, mqtt/auth/jwt, authorization/code).

A throttle is not a network blip and not a rejected login: it raises ``RateLimitedError``,
which ``is_transient_network_error`` does not count as transient, and arms one cooldown
during which every auth endpoint fails fast without a request.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import time
from unittest.mock import MagicMock

import pytest
import time_machine

from pymammotion.http.http import _AUTH_RATE_LIMIT_COOLDOWN_SEC, MammotionHTTP
from pymammotion.http.model.http import RateLimitedError
from pymammotion.transport.base import is_transient_network_error
from tests.unit._helpers import make_http_posting

_ENDPOINTS: dict[str, Callable[[MammotionHTTP], Awaitable[object]]] = {
    "refresh": lambda http: http.refresh_token_v2(),
    "login": lambda http: http.login_v2("a@b.c", "pw"),
    "jwt": lambda http: http.get_mqtt_credentials(),
    "code": lambda http: http.fetch_authorization_token(),
}

_GATED = ("refresh", "jwt", "code")


def _throttled() -> tuple[MammotionHTTP, MagicMock]:
    http, session = make_http_posting(429, {"code": 429, "msg": "too many requests"})
    http.login_info = MagicMock(access_token="tok", refresh_token="ref")  # type: ignore[assignment]
    return http, session


@pytest.mark.regression
@pytest.mark.parametrize("endpoint", list(_ENDPOINTS))
async def test_auth_endpoint_raises_rate_limited_on_a_429(endpoint: str) -> None:
    """A 429 raised ``ConnectionError``, so the scheduler and the host retried a throttle as a network blip."""
    http, _session = _throttled()

    with pytest.raises(RateLimitedError) as excinfo:
        await _ENDPOINTS[endpoint](http)

    assert not is_transient_network_error(excinfo.value)
    assert excinfo.value.retry_after == _AUTH_RATE_LIMIT_COOLDOWN_SEC


@pytest.mark.regression
@pytest.mark.parametrize("first", list(_ENDPOINTS))
@pytest.mark.parametrize("then", _GATED)
async def test_auth_endpoints_fail_fast_without_a_request_during_the_cooldown(first: str, then: str) -> None:
    """Each caller after a 429 sent its own request, one more throttled hit per queued refresh."""
    http, session = _throttled()
    with time_machine.travel(time.time(), tick=False) as clock:
        with pytest.raises(RateLimitedError):
            await _ENDPOINTS[first](http)
        clock.shift(_AUTH_RATE_LIMIT_COOLDOWN_SEC - 60)

        with pytest.raises(RateLimitedError) as excinfo:
            await _ENDPOINTS[then](http)

    assert session.post.await_count == 1, "a throttled endpoint was asked again inside the cooldown"
    assert excinfo.value.retry_after == pytest.approx(60)


async def test_ensure_token_valid_fails_fast_during_the_cooldown() -> None:
    """A decorated endpoint's refresh bypasses the TokenManager, so the HTTP layer must hold the gate."""
    http, session = _throttled()
    http.expires_in = 0.0
    with time_machine.travel(time.time(), tick=False):
        with pytest.raises(RateLimitedError):
            await http.refresh_token_v2()

        with pytest.raises(RateLimitedError):
            await http.ensure_token_valid()

    assert session.post.await_count == 1


async def test_auth_endpoints_are_asked_again_once_the_cooldown_ends() -> None:
    """The cooldown is a pause, not a give-up: after it the endpoint is asked as usual."""
    http, session = _throttled()
    with time_machine.travel(time.time(), tick=False) as clock:
        with pytest.raises(RateLimitedError):
            await http.refresh_token_v2()
        clock.shift(_AUTH_RATE_LIMIT_COOLDOWN_SEC + 1)

        with pytest.raises(RateLimitedError):
            await http.refresh_token_v2()

    assert session.post.await_count == 2


async def test_password_login_is_not_gated_by_the_cooldown() -> None:
    """A login is a person's action, so it is sent; only the automatic renewals are held back."""
    http, session = _throttled()
    with time_machine.travel(time.time(), tick=False):
        with pytest.raises(RateLimitedError):
            await http.refresh_token_v2()

        with pytest.raises(RateLimitedError):
            await http.login_v2("a@b.c", "pw")

    assert session.post.await_count == 2
