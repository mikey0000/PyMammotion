"""Shared builders for the auth unit tests.

Plain functions rather than fixtures, matching the tests/unit/transport/_fakes.py
and tests/unit/messaging/_helpers.py precedent: call sites stay terse and the
helpers stay greppable.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, create_autospec

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.auth.token_manager import AliyunCredentials, HTTPCredentials, MQTTCredentials

from tests._helpers import encode_jwt

__all__ = [
    "encode_jwt",
    "make_aliyun_creds",
    "make_aliyun_gateway",
    "make_http_creds",
    "make_http_mock",
    "make_mqtt_creds",
]

_UNSET: Any = object()


def make_http_creds(
    expires_in_seconds: float,
    *,
    access_token: str = "tok",
    refresh_token: str = "ref",
) -> HTTPCredentials:
    """Build an HTTPCredentials with the given expiry offset from now."""
    return HTTPCredentials(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=time.time() + expires_in_seconds,
    )


def make_mqtt_creds(
    expires_in_seconds: float,
    *,
    host: str = "host",
    client_id: str = "cid",
    username: str = "user",
    jwt: str = "jwt",
) -> MQTTCredentials:
    """Build a MQTTCredentials with the given expiry offset from now."""
    return MQTTCredentials(
        host=host,
        client_id=client_id,
        username=username,
        jwt=jwt,
        expires_at=time.time() + expires_in_seconds,
    )


def make_aliyun_creds(
    expires_in_seconds: float,
    *,
    refresh_expires_in_seconds: float = 86400.0,
) -> AliyunCredentials:
    """Build an AliyunCredentials with the given iotToken expiry offset from now."""
    return AliyunCredentials(
        iot_token="iot",
        iot_token_expires_at=time.time() + expires_in_seconds,
        refresh_token="ref",
        refresh_token_expires_at=time.time() + refresh_expires_in_seconds,
    )


def make_http_mock(
    *,
    refresh_code: int | None = None,
    access_token: str = "access-new",
    refresh_token: str = "refresh-new",
    expires_in: float = 3600.0,
    mqtt_jwt: str | None = None,
    mqtt_host: str = "mqtt.new.example.com",
    mqtt_client_id: str = "client-new",
    mqtt_username: str = "user-new",
    login_info: MagicMock | None = _UNSET,
) -> AsyncMock:
    """Return a MammotionHTTP mock with the reauth plumbing every test needs.

    Endpoints are configured only on request, so an unconfigured mock behaves
    exactly like a bare ``AsyncMock``:
    - ``refresh_code`` configures ``refresh_token_v2`` (its ``data`` is returned
      only on code 0, mirroring the real endpoint);
    - ``mqtt_jwt`` configures ``get_mqtt_credentials``;
    - ``login_info`` is set on the mock only when passed (``None`` is a valid
      explicit value).
    """
    http = AsyncMock()
    http.reauth_required = None
    http.mark_reauth_required = MagicMock()
    if refresh_code is not None:
        data = MagicMock()
        data.access_token = access_token
        data.refresh_token = refresh_token
        data.expires_in = expires_in
        http.refresh_token_v2.return_value = MagicMock(code=refresh_code, data=data if refresh_code == 0 else None)
    if mqtt_jwt is not None:
        mqtt_data = MagicMock()
        mqtt_data.host = mqtt_host
        mqtt_data.client_id = mqtt_client_id
        mqtt_data.username = mqtt_username
        mqtt_data.jwt = mqtt_jwt
        http.get_mqtt_credentials.return_value = MagicMock(data=mqtt_data)
    if login_info is not _UNSET:
        http.login_info = login_info
    return http


def make_aliyun_gateway(
    *,
    http: Any = None,
    issued_at: float = 0,
    iot_token: str = "iot",
    iot_token_expire: int = 7200,
    with_session: bool = True,
    region_response: Any = None,
    aep_response: Any = _UNSET,
) -> MagicMock:
    """Return an autospecced CloudIOTGateway whose Aliyun session was issued at *issued_at*.

    ``region_response`` defaults to ``None``: a gateway that has not run ``get_region``
    yet.  ``with_session=False`` leaves it with no session (an incomplete chain).
    """
    attrs: dict[str, Any] = {"region_response": region_response}
    if http is not None:
        attrs["mammotion_http"] = http
    gateway = create_autospec(CloudIOTGateway, instance=True, **attrs)
    gateway.aep_response = MagicMock() if aep_response is _UNSET else aep_response
    gateway.session_by_authcode_response = (
        MagicMock(
            data=MagicMock(
                iotToken=iot_token, iotTokenExpire=iot_token_expire, refreshToken="r", refreshTokenExpire=864000
            )
        )
        if with_session
        else None
    )
    gateway._iot_token_issued_at = issued_at  # noqa: SLF001
    return gateway
