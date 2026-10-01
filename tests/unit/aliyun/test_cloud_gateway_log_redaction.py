"""``CloudIOTGateway`` debug logging: no Aliyun credential reaches a log record, the identifiers still do.

Mammotion-HA's "Enable debug logging" covers ``pymammotion``, so these logs end up attached to public
issues. Each test drives one auth/command call with distinctive secret values and scans every record
on the root logger at DEBUG.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from Tea.response import TeaResponse

from pymammotion.aliyun import cloud_gateway
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import CloudSetupError, FailedRequestException
from pymammotion.aliyun.model.connect_response import ConnectResponse
from pymammotion.aliyun.model.login_by_oauth_response import LoginByOAuthResponse
from pymammotion.http.http import MammotionHTTP
from pymammotion.transport.base import SessionExpiredError
from tests.unit.aliyun._helpers import make_region, make_session

pytestmark = pytest.mark.regression

_IOT_TOKEN = "SECRET-iot-token-4f1c"
_REFRESH_TOKEN = "SECRET-refresh-token-9a2e"
_SID = "SECRET-sid-77b0"
_OAUTH_TOKEN = "SECRET-oauth-token-31cd"
_OAUTH_REFRESH = "SECRET-oauth-refresh-c0de"
_UID_TOKEN = "SECRET-uid-token-5e5e"
_DEVICE_SECRET = "SECRET-device-secret-ab12"

_IDENTITY_ID = "identity-visible-1"
_IOT_ID = "iot-visible-1"
_OPEN_ID = "open-id-visible-1"
_PRODUCT_KEY = "pk-visible-1"
_DEVICE_NAME = "dn-visible-1"


class _FakeGatewayClient:
    """Stands in for ``pymammotion.aliyun.client.Client``: answers every request with one canned body."""

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    async def async_do_request(self, *_args: object, **_kwargs: object) -> TeaResponse:
        response = TeaResponse()
        response.status_code = 200
        response.status_message = "OK"
        response.headers = {"content-type": "application/json"}
        response.body = json.dumps(self._body).encode()
        return response


class _FakeAiohttpResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self.status = 200
        self._data = data

    async def json(self) -> dict[str, Any]:
        return self._data

    async def __aenter__(self) -> _FakeAiohttpResponse:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


class _FakeClientSession:
    """Stands in for ``aiohttp.ClientSession`` on the openaccount endpoints, which bypass the Tea client."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __call__(self) -> _FakeClientSession:
        return self

    def post(self, *_args: object, **_kwargs: object) -> _FakeAiohttpResponse:
        return _FakeAiohttpResponse(self._data)

    async def __aenter__(self) -> _FakeClientSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _connect_payload() -> dict[str, Any]:
    status = {"traceId": "t", "code": 1, "subCode": 0, "message": "ok", "successful": "true"}
    return {
        "success": "true",
        "api": "connect",
        "data": {
            **status,
            "vid": "vid-1",
            "data": {"device": {**status, "data": {"deviceId": "device-id-1"}}, "config": status},
        },
    }


def _login_by_oauth_payload() -> dict[str, Any]:
    return {
        "success": "true",
        "api": "loginbyoauth",
        "errorMsg": "",
        "data": {
            "traceId": "t",
            "vid": "vid-1",
            "code": 1,
            "subCode": 0,
            "message": "ok",
            "successful": "true",
            "data": {
                "mobileBindRequired": "false",
                "loginSuccessResult": {
                    "reTokenExpireIn": 1,
                    "uidToken": _UID_TOKEN,
                    "initPwd": "false",
                    "sidExpireIn": 1,
                    "oauthOtherInfo": {"SidExpiredTime": 1},
                    "refreshToken": _OAUTH_REFRESH,
                    "sid": _SID,
                    "token": _OAUTH_TOKEN,
                    "openAccount": {
                        "displayName": "Someone",
                        "openId": _OPEN_ID,
                        "hasPassword": "true",
                        "subAccount": "false",
                        "pwdVersion": 0,
                        "mobileConflictAccount": "false",
                        "id": 1,
                        "mobileLocationCode": "",
                        "avatarUrl": "",
                        "domainId": 1,
                        "enableDevice": "true",
                        "status": 0,
                    },
                },
            },
        },
    }


def _session_payload() -> dict[str, Any]:
    return {
        "code": 200,
        "data": {
            "identityId": _IDENTITY_ID,
            "refreshTokenExpire": 2_592_000,
            "iotToken": _IOT_TOKEN,
            "iotTokenExpire": 86_400,
            "refreshToken": _REFRESH_TOKEN,
        },
    }


def _gateway() -> CloudIOTGateway:
    http = MagicMock(spec=MammotionHTTP)
    http.account = "user@example.com"
    http.login_info.authorization_code = "auth-code-1"
    gateway = CloudIOTGateway(
        mammotion_http=http,
        connect_response=ConnectResponse.from_dict(_connect_payload()),
        login_by_oauth_response=LoginByOAuthResponse.from_dict(_login_by_oauth_payload()),
        session_by_authcode_response=make_session(iot_token=_IOT_TOKEN, iot_token_expire=999_999_999),
        region_response=make_region(),
    )
    gateway._iot_token_issued_at = 2_000_000_000  # noqa: SLF001 — far-future issue keeps send's refresh branch off
    return gateway


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


def _assert_redacted(caplog: pytest.LogCaptureFixture, secrets: tuple[str, ...], visible: tuple[str, ...]) -> None:
    logged = _logged(caplog)
    leaked = [secret for secret in secrets if secret in logged]
    assert not leaked, f"credentials reached the debug log: {leaked}"
    missing = [value for value in visible if value not in logged]
    assert not missing, f"identifiers dropped from the debug log: {missing}"


async def test_session_by_auth_code_log_omits_the_iot_and_refresh_tokens(caplog: pytest.LogCaptureFixture) -> None:
    """The raw createSessionByAuthCode response was logged, iotToken and refreshToken included."""
    caplog.set_level(logging.DEBUG)
    gateway = _gateway()

    with patch.object(cloud_gateway, "Client", return_value=_FakeGatewayClient(_session_payload())):
        await gateway.session_by_auth_code()

    _assert_redacted(caplog, (_IOT_TOKEN, _REFRESH_TOKEN), (_IDENTITY_ID,))


async def test_check_or_refresh_session_log_omits_the_iot_and_refresh_tokens(caplog: pytest.LogCaptureFixture) -> None:
    """The raw checkOrRefreshSession response was logged on every HA start and every scheduled refresh."""
    caplog.set_level(logging.DEBUG)
    gateway = _gateway()

    with patch.object(cloud_gateway, "Client", return_value=_FakeGatewayClient(_session_payload())):
        await gateway.check_or_refresh_session(force=True)

    _assert_redacted(caplog, (_IOT_TOKEN, _REFRESH_TOKEN), (_IDENTITY_ID,))


async def test_login_by_oauth_log_omits_the_session_tokens(caplog: pytest.LogCaptureFixture) -> None:
    """The loginbyoauth response dict was logged whole: sid, token, refreshToken and uidToken."""
    caplog.set_level(logging.DEBUG)
    gateway = _gateway()

    with patch.object(cloud_gateway, "ClientSession", _FakeClientSession(_login_by_oauth_payload())):
        await gateway.login_by_oauth("GB")

    _assert_redacted(caplog, (_SID, _OAUTH_TOKEN, _OAUTH_REFRESH, _UID_TOKEN), (_OPEN_ID,))


async def test_aep_handle_log_omits_the_device_secret(caplog: pytest.LogCaptureFixture) -> None:
    """The aepauth response was logged twice, raw and as a dict, deviceSecret included."""
    caplog.set_level(logging.DEBUG)
    gateway = _gateway()
    body = {
        "code": 200,
        "data": {"deviceSecret": _DEVICE_SECRET, "productKey": _PRODUCT_KEY, "deviceName": _DEVICE_NAME},
    }

    with patch.object(cloud_gateway, "Client", return_value=_FakeGatewayClient(body)):
        await gateway.aep_handle()

    _assert_redacted(caplog, (_DEVICE_SECRET,), (_PRODUCT_KEY, _DEVICE_NAME))


async def test_send_cloud_command_log_omits_the_iot_token(caplog: pytest.LogCaptureFixture) -> None:
    """The ``IoTApiRequest`` dict repr was logged on every command and heartbeat; its ``request`` block holds the iotToken."""
    caplog.set_level(logging.DEBUG)
    gateway = _gateway()

    with patch.object(cloud_gateway, "Client", return_value=_FakeGatewayClient({"code": 200})):
        message_id = await gateway.send_cloud_command(_IOT_ID, b"\x00\x01")

    _assert_redacted(caplog, (_IOT_TOKEN,), (_IOT_ID, message_id))


async def test_check_or_refresh_session_failure_omits_the_tokens_from_log_and_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A rejected refresh logged its body at ERROR and put its dict repr into the raised message."""
    caplog.set_level(logging.DEBUG)
    gateway = _gateway()
    body = {**_session_payload(), "code": 500}

    with (
        patch.object(cloud_gateway, "Client", return_value=_FakeGatewayClient(body)),
        pytest.raises(SessionExpiredError) as excinfo,
    ):
        await gateway.check_or_refresh_session(force=True)

    _assert_redacted(caplog, (_IOT_TOKEN, _REFRESH_TOKEN), (_IDENTITY_ID,))
    assert _IOT_TOKEN not in str(excinfo.value)
    assert _REFRESH_TOKEN not in str(excinfo.value)


async def test_session_by_auth_code_failure_omits_the_tokens_from_the_error(caplog: pytest.LogCaptureFixture) -> None:
    """A non-200 session response was embedded raw in the ``CloudSetupError`` message."""
    caplog.set_level(logging.DEBUG)
    gateway = _gateway()
    body = {**_session_payload(), "code": 500}

    with (
        patch.object(cloud_gateway, "Client", return_value=_FakeGatewayClient(body)),
        pytest.raises(CloudSetupError) as excinfo,
    ):
        await gateway.session_by_auth_code()

    _assert_redacted(caplog, (_IOT_TOKEN, _REFRESH_TOKEN), (_IDENTITY_ID,))
    assert _IOT_TOKEN not in str(excinfo.value)
    assert _REFRESH_TOKEN not in str(excinfo.value)
    assert _IDENTITY_ID in str(excinfo.value)


async def test_send_cloud_command_22000_error_log_omits_the_iot_token(caplog: pytest.LogCaptureFixture) -> None:
    """The 22000 branch logged the raw response body at ERROR."""
    caplog.set_level(logging.DEBUG)
    gateway = _gateway()
    body = {"code": 22000, "request": {"iotToken": _IOT_TOKEN}}

    with (
        patch.object(cloud_gateway, "Client", return_value=_FakeGatewayClient(body)),
        pytest.raises(FailedRequestException),
    ):
        await gateway.send_cloud_command(_IOT_ID, b"\x00\x01")

    _assert_redacted(caplog, (_IOT_TOKEN,), (_IOT_ID,))
