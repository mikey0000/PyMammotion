"""Tests for pymammotion.auth.token_manager."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth.token_manager import (
    AliyunCredentials,
    HTTPCredentials,
    MQTTCredentials,
    TokenManager,
)
from pymammotion.transport.base import ReLoginRequiredError


def make_http_creds(expires_in_seconds: float) -> HTTPCredentials:
    """Build an HTTPCredentials with the given expiry offset from now."""
    return HTTPCredentials(
        access_token="tok",
        refresh_token="ref",
        expires_at=time.time() + expires_in_seconds,
    )


def make_mqtt_creds(expires_in_seconds: float) -> MQTTCredentials:
    """Build a MQTTCredentials with the given expiry offset from now."""
    return MQTTCredentials(
        host="host",
        client_id="cid",
        username="user",
        jwt="jwt",
        expires_at=time.time() + expires_in_seconds,
    )


async def test_http_token_refreshed_when_expiring_soon() -> None:
    """get_valid_http_token() must call _refresh_http when creds expire in < 5 min."""
    http = AsyncMock()
    http.refresh_login = AsyncMock(
        return_value=MagicMock(
            data=MagicMock(access_token="new_tok", refresh_token="new_ref", expires_in=3600)
        )
    )
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(180), None, None)  # expires in 3 min
    # Patch _refresh_http to verify it's called
    tm._refresh_http = AsyncMock()  # type: ignore[method-assign]
    # Re-set creds to force refresh
    tm._http_creds = make_http_creds(180)
    await tm.get_valid_http_token()
    tm._refresh_http.assert_awaited_once()  # type: ignore[attr-defined]


async def test_http_token_not_refreshed_when_fresh() -> None:
    """get_valid_http_token() must NOT call _refresh_http when token is fresh."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(600), None, None)  # expires in 10 min
    tm._refresh_http = AsyncMock()  # type: ignore[method-assign]
    await tm.get_valid_http_token()
    tm._refresh_http.assert_not_awaited()  # type: ignore[attr-defined]


async def test_mqtt_creds_refreshed_when_expiring_soon() -> None:
    """get_mammotion_mqtt_credentials() must refresh when creds expire in < 30 min."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(600), None, make_mqtt_creds(900))  # expires in 15 min < 30 min
    tm._refresh_mqtt_creds = AsyncMock()  # type: ignore[method-assign]
    await tm.get_mammotion_mqtt_credentials()
    tm._refresh_mqtt_creds.assert_awaited_once()  # type: ignore[attr-defined]


async def test_concurrent_refresh_called_once() -> None:
    """Concurrent calls to get_valid_http_token() must only trigger one refresh."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(100), None, None)  # will refresh (< 300 s)

    refresh_count = 0

    async def counting_refresh() -> None:
        nonlocal refresh_count
        refresh_count += 1
        await asyncio.sleep(0.01)
        tm._http_creds = make_http_creds(3600)

    tm._refresh_http = counting_refresh  # type: ignore[method-assign]
    await asyncio.gather(
        tm.get_valid_http_token(),
        tm.get_valid_http_token(),
    )
    assert refresh_count == 1


async def test_force_refresh_raises_relogin_on_auth_failure() -> None:
    """force_refresh() must propagate ReLoginRequiredError from _refresh_http."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(100), None, None)

    async def failing_refresh() -> None:
        raise ReLoginRequiredError("acc1", "401")

    tm._refresh_http = failing_refresh  # type: ignore[method-assign]
    with pytest.raises(ReLoginRequiredError):
        await tm.force_refresh()


async def test_relogin_error_has_account_id() -> None:
    """ReLoginRequiredError must expose account_id and include it in the message."""
    err = ReLoginRequiredError("my_account", "expired")
    assert err.account_id == "my_account"
    assert "my_account" in str(err)


async def test_get_aliyun_credentials_raises_without_gateway() -> None:
    """get_aliyun_credentials() must raise RuntimeError when no gateway is configured."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(None, None, None)
    with pytest.raises(RuntimeError, match="No Aliyun cloud gateway configured"):
        await tm.get_aliyun_credentials()


async def test_mqtt_creds_not_refreshed_when_fresh() -> None:
    """get_mammotion_mqtt_credentials() must NOT refresh when creds are fresh (> 30 min)."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    await tm.initialize(make_http_creds(600), None, make_mqtt_creds(7200))  # expires in 2 hours
    tm._refresh_mqtt_creds = AsyncMock()  # type: ignore[method-assign]
    await tm.get_mammotion_mqtt_credentials()
    tm._refresh_mqtt_creds.assert_not_awaited()  # type: ignore[attr-defined]


async def test_initialize_stores_credentials() -> None:
    """initialize() must store all three credential types."""
    http = AsyncMock()
    tm = TokenManager("acc1", http)
    http_creds = make_http_creds(3600)
    mqtt_creds = make_mqtt_creds(86400)
    aliyun_creds = AliyunCredentials(
        iot_token="iot",
        iot_token_expires_at=time.time() + 7200,
        refresh_token="ref",
        refresh_token_expires_at=time.time() + 86400,
    )
    await tm.initialize(http_creds, aliyun_creds, mqtt_creds)
    assert tm._http_creds is http_creds
    assert tm._aliyun_creds is aliyun_creds
    assert tm._mqtt_creds is mqtt_creds
