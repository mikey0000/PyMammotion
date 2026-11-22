"""How TokenManager treats each outcome of POST /authorization/code.

The Mammotion MQTT JWT and the invoke bearer do not need the code, so a refusal to
mint one must not cost those paths anything; a refused bearer after a fresh
refresh means the login itself is dead.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import TokenManager
from pymammotion.http.model.http import AuthorizationCodeError, UnauthorizedExceptionError
from pymammotion.transport.base import ReLoginRequiredError
from tests.unit.auth._helpers import encode_jwt, make_http_mock


def _tm(http: AsyncMock) -> TokenManager:
    return TokenManager(account_id="user@example.com", mammotion_http=http)


_FRESH_JWT = encode_jwt(exp=9_999_999_999)


def _http_whose_jwt_needs_a_refresh() -> AsyncMock:
    """The first JWT fetch answers no data, so _refresh_mqtt refreshes the bearer and mints a code before retrying."""
    http = make_http_mock(refresh_code=0, mqtt_jwt=_FRESH_JWT, login_info=MagicMock())
    fresh = http.get_mqtt_credentials.return_value
    http.get_mqtt_credentials.side_effect = [MagicMock(data=None), fresh]
    return http


@pytest.mark.regression
async def test_refresh_mqtt_survives_a_refused_authorization_code() -> None:
    """A code refusal on the JWT path gave up on Mammotion MQTT, although the JWT never uses the code."""
    http = _http_whose_jwt_needs_a_refresh()
    http.fetch_authorization_token.side_effect = AuthorizationCodeError("429")
    tm = _tm(http)

    creds = await tm.refresh_mqtt_credentials()

    assert creds.jwt == _FRESH_JWT
    assert tm.mqtt_unavailable is None


async def test_refresh_mqtt_marks_the_account_dead_when_the_fresh_bearer_is_refused() -> None:
    http = _http_whose_jwt_needs_a_refresh()
    http.fetch_authorization_token.side_effect = UnauthorizedExceptionError("401")
    tm = _tm(http)

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_mqtt_credentials()

    assert tm.reauth_required is not None
    assert tm.mqtt_unavailable is None


@pytest.mark.regression
async def test_refresh_invoke_token_survives_a_refused_authorization_code() -> None:
    """The invoke bearer was refreshed, then a code refusal escaped and failed the retry it had just made possible."""
    http = make_http_mock(refresh_code=0, login_info=MagicMock(access_token="tok"))
    http.fetch_authorization_token.side_effect = AuthorizationCodeError("refused")
    tm = _tm(http)

    await tm.refresh_invoke_token()

    assert tm.reauth_required is None
