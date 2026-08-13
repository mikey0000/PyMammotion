"""Integration tests: MammotionClient credential restore / cloud bootstrap flows.

Exercises restore_credentials, login_and_initiate_cloud, cache round-trips and
device bootstrap across client + cloud gateway + http + token manager + transports.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import (
    DeviceRecords,
    JWTTokenInfo,
    LoginResponseData,
    LoginResponseUserInformation,
    MQTTConnection,
    Response,
)
from pymammotion.transport.base import TransportType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# (BLE polling-loop autoload-suppress fixture lives in tests/conftest.py.)

def _access_token(iot: str, robot: str) -> str:
    """Mint an unsigned-verifiable access token carrying the iot/robot/exp claims.

    ``MammotionHTTP.response``'s setter decodes the access_token to seed
    ``jwt_info`` and ``expires_in``, so a populated http needs a real JWT.
    """
    import jwt as pyjwt

    return pyjwt.encode({"iot": iot, "robot": robot, "exp": 9999999999}, "x" * 32, algorithm="HS256")

def _populated_mammotion_http(account: str = "user@test.com") -> MammotionHTTP:
    """Return a MammotionHTTP populated as it would be after a successful login.

    Carries a login response, MQTT credentials, and JWT info so a ``to_cache`` →
    restore round-trip has something to preserve.  The explicit ``jwt_info``
    intentionally differs from the access_token's claims so a round-trip can prove
    the cached JWT (not the token-derived one) is what gets restored.
    """
    user_info = LoginResponseUserInformation(
        areaCode="44", domainAbbreviation="EU", userId="u1", userAccount="123", authType="email"
    )
    login_data = LoginResponseData(
        access_token=_access_token("token-iot.example.com", "token-robot.example.com"),
        token_type="bearer",
        refresh_token="rt",
        expires_in=3600,
        authorization_code="ac",
        userInformation=user_info,
    )
    http = MammotionHTTP(account, "pass")
    http.response = Response(code=0, msg="ok", data=login_data)
    http.login_info = login_data
    http.mqtt_credentials = MQTTConnection(
        host="mqtt.example.com", jwt="jwt-token", client_id="client-1", username="user"
    )
    http.jwt_info = JWTTokenInfo(iot="iot.example.com", robot="robot.example.com")
    return http

def _cached_from(http: MammotionHTTP, **extra: object) -> dict:
    """Return the cache dict ``MammotionClient.to_cache`` would produce for *http*.

    Values are left as live models — ``MammotionHTTP.from_cache`` accepts both those
    and their JSON dict form, and the dict branch is covered separately.
    """
    raw: dict[str, object] = {
        "mammotion_data": http.response,
        "mammotion_mqtt": http.mqtt_credentials,
        "mammotion_jwt_info": http.jwt_info,
        "mammotion_device_records": http.device_records,
    }
    raw.update(extra)
    return raw

def _make_share_record(*, is_receiver: int = 1, status: int = -1, batch_id: str = "batch1", record_id: str = "1") -> MagicMock:
    """Return a MagicMock shaped like a ShareRecord."""
    r = MagicMock()
    r.is_receiver = is_receiver
    r.status = status
    r.batch_id = batch_id
    r.record_id = record_id
    return r

def _make_device_record(device_name: str = "Yuka-TEST", iot_id: str = "iot-yuka", product_key: str = "pk1") -> MagicMock:
    """Return a MagicMock shaped like a DeviceRecord."""
    r = MagicMock()
    r.device_name = device_name
    r.iot_id = iot_id
    r.product_key = product_key
    return r

def _make_mock_http(
    *,
    device_records: list[MagicMock] | None = None,
    share_records: list[MagicMock] | None = None,
    mqtt_creds: MagicMock | None = None,
) -> MagicMock:
    """Return a MagicMock shaped like MammotionHTTP with the given fixture data."""
    http = MagicMock()
    http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))
    http.get_user_shared_device_page = AsyncMock(
        return_value=MagicMock(data=MagicMock(records=share_records or []))
    )
    # get_user_device_page both returns data AND updates http.device_records (side-effect)
    page_data = MagicMock()
    page_data.records = device_records or []
    page_resp = MagicMock()
    page_resp.data = page_data
    http.get_user_device_page = AsyncMock(return_value=page_resp)
    http.get_mqtt_credentials = AsyncMock()
    http.confirm_share = AsyncMock()
    http.mqtt_credentials = mqtt_creds or MagicMock()
    http.login_info = MagicMock()
    # restore_credentials validates the restored login before touching any transport.
    http.validate_login = AsyncMock(return_value=True)
    http.device_records = MagicMock(records=[])
    return http

async def test_token_manager_set_after_restore_aliyun() -> None:
    """_restore_aliyun must give the session a token_manager holding the gateway."""
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")
    # restore_credentials establishes the login session before dispatching to a transport.
    http = _populated_mammotion_http()
    http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))  # type: ignore[method-assign]
    acct_session.mammotion_http = http

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = http
    mock_cloud.devices_by_account_response = None

    with (
        patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock(return_value=mock_cloud)),
        patch.object(client, "_setup_aliyun_transport", return_value=MagicMock()),
    ):
        await client._restore_aliyun("user@test.com", {}, acct_session, check_for_new_devices=False)

    assert acct_session.token_manager is not None
    # The gateway is attached to the account's one manager, not used to build a second.
    assert acct_session.token_manager.http is http
    assert acct_session.token_manager.cloud_gateway is mock_cloud

async def test_restore_aliyun_without_a_login_session_is_a_no_op() -> None:
    """A missing login session must skip the Aliyun transport, not crash or half-wire it."""
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    with patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock()) as mock_from_cache:
        await client._restore_aliyun("user@test.com", {}, acct_session, check_for_new_devices=False)

    mock_from_cache.assert_not_awaited()
    assert acct_session.cloud_client is None
    assert acct_session.token_manager is None

async def test_unusable_aliyun_cache_is_rebuilt_from_the_http_login() -> None:
    """An Aliyun session is minted from the HTTP login, so a bad cache costs no password.

    connect_iot re-derives the whole Aliyun session from the (already validated)
    login's authCode chain.  Falling back to a full login here would throw away a
    healthy login to re-derive exactly the same thing from a password grant.
    """
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")
    http = _populated_mammotion_http()
    http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))  # type: ignore[method-assign]
    acct_session.mammotion_http = http

    rebuilt: list[object] = []

    def _new_gateway(mammotion_http: object) -> MagicMock:
        """Stand in for CloudIOTGateway(http) — _connect_iot fills in the responses."""
        gateway = MagicMock()
        gateway.mammotion_http = mammotion_http
        gateway.devices_by_account_response = None
        return gateway

    async def _connect_iot(cloud_client: object) -> None:
        rebuilt.append(cloud_client)

    mock_gateway_cls = MagicMock(side_effect=_new_gateway)
    mock_gateway_cls.from_cache = AsyncMock(return_value=None)

    with (
        patch("pymammotion.client.CloudIOTGateway", mock_gateway_cls),
        patch.object(client, "_connect_iot", _connect_iot),
        patch.object(client, "login_and_initiate_cloud", AsyncMock()) as mock_login,
        patch.object(client, "_setup_aliyun_transport", return_value=MagicMock()),
        patch("pymammotion.http.http.MammotionHTTP.login_v2", new_callable=AsyncMock) as mock_login_v2,
    ):
        await client._restore_aliyun("user@test.com", {}, acct_session, check_for_new_devices=False)

    mock_login.assert_not_awaited()
    mock_login_v2.assert_not_awaited()
    # The rebuilt gateway hangs off the account's existing login session.
    assert len(rebuilt) == 1
    assert rebuilt[0].mammotion_http is http  # type: ignore[attr-defined]
    assert acct_session.cloud_client is rebuilt[0]
    assert acct_session.token_manager is not None
    assert acct_session.token_manager.cloud_gateway is rebuilt[0]

async def test_failed_aliyun_rebuild_costs_only_that_transport() -> None:
    """Aliyun being unreachable must not take the login or the other transport down."""
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")
    http = _populated_mammotion_http()
    acct_session.mammotion_http = http

    with (
        patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock(return_value=None)),
        patch.object(client, "_connect_iot", AsyncMock(side_effect=ConnectionError("aliyun down"))),
        patch.object(client, "login_and_initiate_cloud", AsyncMock()) as mock_login,
    ):
        await client._restore_aliyun("user@test.com", {}, acct_session, check_for_new_devices=False)

    mock_login.assert_not_awaited()
    assert acct_session.mammotion_http is http
    assert acct_session.aliyun_transport is None

async def test_incomplete_aliyun_rebuild_skips_the_transport() -> None:
    """A rebuild that returns without a usable session must not be wired up.

    _setup_aliyun_transport dereferences aep/region/session data directly, so a
    half-built gateway would surface as an AttributeError mid-restore.
    """
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")
    acct_session.mammotion_http = _populated_mammotion_http()

    with (
        patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock(return_value=None)),
        patch.object(client, "_connect_iot", AsyncMock()),  # leaves every response None
        patch.object(client, "_setup_aliyun_transport") as mock_setup,
    ):
        await client._restore_aliyun("user@test.com", {}, acct_session, check_for_new_devices=False)

    mock_setup.assert_not_called()
    assert acct_session.aliyun_transport is None

async def test_restore_aliyun_refreshes_session_before_device_list() -> None:
    """_restore_aliyun must check/refresh the Aliyun session before listing devices.

    The cached iotToken may have expired; list_binding_by_account uses it directly
    and would 401/460 otherwise.
    """
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    order: list[str] = []

    acct_session.mammotion_http = MagicMock()
    acct_session.mammotion_http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = acct_session.mammotion_http
    mock_cloud.devices_by_account_response = None
    mock_cloud.session_by_authcode_response = MagicMock()
    mock_cloud.session_by_authcode_response.data.iotToken = "tok"

    check_kwargs: dict[str, object] = {}

    async def _check(*_a: object, **kwargs: object) -> None:
        order.append("check_or_refresh_session")
        check_kwargs.update(kwargs)

    async def _list(*_a: object, **_k: object) -> MagicMock:
        order.append("list_binding_by_account")
        return MagicMock(data=None)

    mock_cloud.check_or_refresh_session = _check
    mock_cloud.list_binding_by_account = _list

    with (
        patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock(return_value=mock_cloud)),
        patch.object(client, "_setup_aliyun_transport", return_value=MagicMock()),
    ):
        await client._restore_aliyun("user@test.com", {}, acct_session, check_for_new_devices=True)

    assert order == ["check_or_refresh_session", "list_binding_by_account"]
    # Cold restore must FORCE the refresh — the cached token can't be trusted even when it
    # looks nominally fresh (server may have invalidated it early while HA was offline).
    assert check_kwargs.get("force") is True


async def test_restore_aliyun_applies_refreshed_token_before_listing() -> None:
    """_restore_aliyun must refresh the Aliyun session and have the UPDATED iotToken set on
    the gateway before list_binding_by_account runs.

    Regression for the 401 on restore: list_binding_by_account reads the token straight off
    the gateway session, so the refresh must have applied the new token to the gateway first.
    """
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    acct_session.mammotion_http = MagicMock()
    acct_session.mammotion_http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = acct_session.mammotion_http
    mock_cloud.devices_by_account_response = None
    mock_cloud.session_by_authcode_response = MagicMock()
    mock_cloud.session_by_authcode_response.data.iotToken = "stale-token"

    async def _check(*_a: object, **_k: object) -> None:
        # A real check_or_refresh_session applies the new token to the gateway session.
        mock_cloud.session_by_authcode_response.data.iotToken = "refreshed-token"

    token_seen_by_list: list[str] = []

    async def _list(*_a: object, **_k: object) -> MagicMock:
        token_seen_by_list.append(mock_cloud.session_by_authcode_response.data.iotToken)
        return MagicMock(data=None)

    mock_cloud.check_or_refresh_session = _check
    mock_cloud.list_binding_by_account = _list

    with (
        patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock(return_value=mock_cloud)),
        patch.object(client, "_setup_aliyun_transport", return_value=MagicMock()),
    ):
        await client._restore_aliyun("user@test.com", {}, acct_session, check_for_new_devices=True)

    # The device-list call ran with the refreshed token (set on the gateway), not the stale one.
    assert token_seen_by_list == ["refreshed-token"]
    assert mock_cloud.session_by_authcode_response.data.iotToken == "refreshed-token"

async def test_token_manager_set_after_restore_mammotion_mqtt() -> None:
    """_restore_mammotion_mqtt must set token_manager on the session when mqtt_creds are present."""
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    # The login session restore_credentials would have established, hydrated from the
    # same cache — the MQTT credentials come off it, not out of the cache dict again.
    http = MammotionHTTP.from_cache(_cached_from(_populated_mammotion_http()), "user@test.com", "pass")
    assert http is not None
    acct_session.mammotion_http = http

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    with (
        patch.object(client, "_setup_mammotion_transport", return_value=mock_transport),
        patch("pymammotion.http.http.MammotionHTTP.login_v2", new_callable=AsyncMock) as mock_login,
        patch("pymammotion.client.MammotionHTTP.get_user_device_list", new_callable=AsyncMock) as mock_list,
    ):
        mock_list.return_value = MagicMock(data=[])
        await client._restore_mammotion_mqtt("user@test.com", acct_session)

    assert acct_session.token_manager is not None
    # The cached MQTT credentials must actually be restored onto the http object,
    # not merely accepted.  (Catches the `data`/`cached_data` NameError regression.)
    assert http.mqtt_credentials is not None
    assert http.mqtt_credentials.host == "mqtt.example.com"
    # Restore never mints a session from a stored password.
    mock_login.assert_not_awaited()

async def test_restore_mammotion_mqtt_without_mqtt_credentials_is_a_no_op() -> None:
    """No cached MQTT credentials → no transport, and no attempt to invent one."""
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")
    http = _populated_mammotion_http()
    http.mqtt_credentials = None
    acct_session.mammotion_http = http

    with patch.object(client, "_setup_mammotion_transport") as mock_setup:
        await client._restore_mammotion_mqtt("user@test.com", acct_session)

    mock_setup.assert_not_called()
    assert acct_session.mammotion_transport is None

async def test_restore_mammotion_mqtt_reuses_existing_http_for_hybrid_account() -> None:
    """Hybrid (Aliyun+Mammotion) account must keep ONE MammotionHTTP and ONE TokenManager.

    Regression: _restore_aliyun runs first and sets acct_session.mammotion_http (A)
    plus a TokenManager bound to A.  _restore_mammotion_mqtt used to create a *new*
    MammotionHTTP (B) for the transport while keeping the A-bound TokenManager, so a
    401-driven refresh updated A's token while mqtt_invoke kept sending B's dead
    token — an unrecoverable 401 loop.  The transport, its TokenManager and the
    account must all share one instance, and the manager itself must not be replaced:
    a second one would leave the first's refresh scheduler running alongside it.
    """
    from pymammotion.auth.token_manager import TokenManager

    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    # State left by a preceding _restore_aliyun: an authenticated http (A) + bound TM.
    http_a = _populated_mammotion_http()
    acct_session.mammotion_http = http_a
    tm_a = TokenManager("user@test.com", http_a)
    acct_session.token_manager = tm_a

    captured: dict[str, object] = {}

    def _capture_setup(_mqtt_creds: object, mammotion_http: object, _acct: object, token_manager: object) -> object:
        captured["http"] = mammotion_http
        captured["tm"] = token_manager
        transport = MagicMock()
        transport.connect = AsyncMock()
        return transport

    with (
        patch.object(client, "_setup_mammotion_transport", side_effect=_capture_setup),
        patch("pymammotion.client.MammotionHTTP.get_user_device_list", new_callable=AsyncMock) as mock_list,
        # Keep the test hermetic: a regressed (instance-B) path would otherwise hit
        # the live login endpoint here, since the fresh instance has no login_info.
        patch("pymammotion.http.http.MammotionHTTP.login_v2", new_callable=AsyncMock) as mock_login,
    ):
        mock_list.return_value = MagicMock(data=[])
        mock_login.return_value = MagicMock(code=0, data=MagicMock())
        await client._restore_mammotion_mqtt("user@test.com", acct_session)

    # The account's http must NOT be replaced, and transport + token manager must be
    # wired to that same instance.
    assert acct_session.mammotion_http is http_a
    assert captured["http"] is http_a
    assert captured["tm"] is tm_a
    assert acct_session.token_manager is tm_a

async def test_to_cache_includes_mammotion_jwt_info() -> None:
    """to_cache() must emit mammotion_jwt_info so JWT survives a restore.

    Regression: the Mammotion-MQTT-only branch of to_cache previously omitted the
    JWT key entirely, so restore had nothing to read.
    """
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")
    acct_session.mammotion_http = _populated_mammotion_http()
    await client._account_registry.register(acct_session)

    raw = client.to_cache()

    assert "mammotion_mqtt" in raw
    assert "mammotion_jwt_info" in raw
    assert raw["mammotion_jwt_info"].iot == "iot.example.com"

async def test_mammotion_mqtt_cache_round_trips_mqtt_and_jwt() -> None:
    """A full to_cache() → JSON → from_cache round-trip preserves MQTT creds and JWT info.

    JSON-normalising the cache between save and restore mimics how the integration
    persists it to disk, exercising the dict-decoding branches of restore that the
    object-only tests skip.
    """
    import orjson

    # --- save side ---------------------------------------------------------
    saver = MammotionClient()
    save_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")
    save_session.mammotion_http = _populated_mammotion_http()
    save_session.mammotion_http.device_records = DeviceRecords(records=[], current=0, total=0, size=0, pages=0)
    await saver._account_registry.register(save_session)

    raw = saver.to_cache()
    # mimic persistence: model objects → plain JSON dicts and back
    cached_data = {
        k: (orjson.loads(v.to_json()) if hasattr(v, "to_json") else v) for k, v in raw.items()
    }
    # device_records is required by the restore path
    cached_data.setdefault("mammotion_device_records", {"records": [], "current": 0, "total": 0, "size": 0, "pages": 0})

    # --- restore side ------------------------------------------------------
    http = MammotionHTTP.from_cache(cached_data, "user@test.com", "pass")

    assert http is not None
    assert http.mqtt_credentials is not None
    assert http.mqtt_credentials.host == "mqtt.example.com"
    assert http.mqtt_credentials.jwt == "jwt-token"
    assert http.jwt_info.iot == "iot.example.com"
    assert http.jwt_info.robot == "robot.example.com"

async def test_token_manager_set_after_login_and_initiate_cloud() -> None:
    """login_and_initiate_cloud must set token_manager when Aliyun devices are present."""
    client = MammotionClient()

    mock_device = MagicMock()
    mock_device.device_name = "Luba-Cloud"
    mock_device.iot_id = "iot-123"

    mock_devices_data = MagicMock()
    mock_devices_data.data.data = [mock_device]

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = MagicMock()
    mock_cloud.mammotion_http.login_info = None
    mock_cloud.devices_by_account_response = mock_devices_data
    mock_cloud.aep_response = MagicMock()
    mock_cloud.aep_response.data = MagicMock(productKey="pk", deviceName="dn", deviceSecret="ds")
    mock_cloud.region_response = MagicMock()
    mock_cloud.region_response.data.regionId = "cn-shanghai"
    mock_cloud.session_by_authcode_response = MagicMock()
    mock_cloud.session_by_authcode_response.data = MagicMock(iotToken="tok")

    mock_http = MagicMock()
    mock_http.login_v2 = AsyncMock(return_value=MagicMock(code=0))
    mock_http.get_user_device_list = AsyncMock(return_value=MagicMock(data=None))
    mock_http.get_user_shared_device_page = AsyncMock(return_value=MagicMock(data=MagicMock(records=[])))
    mock_http.get_user_device_page = AsyncMock(return_value=MagicMock(data=None))
    mock_http.login_info = None
    mock_http.mqtt_credentials = None

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    with (
        patch("pymammotion.client.MammotionHTTP", return_value=mock_http),
        patch("pymammotion.client.CloudIOTGateway", return_value=mock_cloud),
        patch("pymammotion.client.MammotionClient._connect_iot", AsyncMock()),
        patch.object(client, "_setup_aliyun_transport", return_value=mock_transport),
        patch.object(client, "_register_aliyun_device", AsyncMock()),
    ):
        mock_cloud.get_shared_notice_list = AsyncMock(return_value=MagicMock(data=None))
        mock_cloud.get_shared_notice_list.return_value.data = None
        await client.login_and_initiate_cloud("user@test.com", "pass")

    session = client._account_registry.get("user@test.com")
    assert session is not None
    assert session.token_manager is not None

async def test_bootstrap_no_existing_transport_calls_connect_once() -> None:
    """When no transport exists, _bootstrap_mammotion_mqtt must connect exactly once."""
    from pymammotion.account.registry import AccountSession

    client = MammotionClient()
    acct_session = AccountSession(account_id="u@x.com", email="u@x.com", password="pw")

    mock_http = _make_mock_http(device_records=[_make_device_record()])
    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    with patch.object(client, "_setup_mammotion_transport", return_value=mock_transport), \
         patch.object(client, "_register_mammotion_device", AsyncMock()):
        await client._bootstrap_mammotion_mqtt("u@x.com", mock_http, acct_session, {})

    mock_transport.connect.assert_awaited_once()

async def test_bootstrap_existing_transport_does_not_call_connect() -> None:
    """When a transport already exists, _bootstrap_mammotion_mqtt must NOT call connect()."""
    from pymammotion.account.registry import AccountSession

    client = MammotionClient()
    acct_session = AccountSession(account_id="u@x.com", email="u@x.com", password="pw")

    existing_transport = MagicMock()
    existing_transport.connect = AsyncMock()
    acct_session.mammotion_transport = existing_transport

    mock_http = _make_mock_http(device_records=[_make_device_record("Yuka-NEW")])

    with patch.object(client, "_register_mammotion_device", AsyncMock()):
        await client._bootstrap_mammotion_mqtt(
            "u@x.com", mock_http, acct_session, {}, skip_ids=set()
        )

    existing_transport.connect.assert_not_awaited()

async def test_bootstrap_confirm_share_called_once_per_batch() -> None:
    """confirm_share must be called once for each unique batch_id with pending shares."""
    from pymammotion.account.registry import AccountSession

    client = MammotionClient()
    acct_session = AccountSession(account_id="u@x.com", email="u@x.com", password="pw")

    share_records = [
        _make_share_record(batch_id="batch1", record_id="1"),
        _make_share_record(batch_id="batch1", record_id="2"),  # same batch
        _make_share_record(batch_id="batch2", record_id="3"),  # different batch
        _make_share_record(is_receiver=0, batch_id="batch3", record_id="4"),  # not receiver → skip
        _make_share_record(status=0, batch_id="batch4", record_id="5"),  # already accepted → skip
    ]
    mock_http = _make_mock_http(
        device_records=[_make_device_record()],
        share_records=share_records,
    )

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    with patch.object(client, "_setup_mammotion_transport", return_value=mock_transport), \
         patch.object(client, "_register_mammotion_device", AsyncMock()):
        await client._bootstrap_mammotion_mqtt("u@x.com", mock_http, acct_session, {})

    # Only batch1 and batch2 should have been confirmed (2 calls total)
    assert mock_http.confirm_share.await_count == 2
    calls = {call.args[0] for call in mock_http.confirm_share.await_args_list}
    assert calls == {"batch1", "batch2"}

async def test_bootstrap_skip_ids_prevents_double_registration() -> None:
    """Devices listed in skip_ids must not be registered a second time."""
    from pymammotion.account.registry import AccountSession

    client = MammotionClient()
    acct_session = AccountSession(account_id="u@x.com", email="u@x.com", password="pw")

    existing_transport = MagicMock()
    existing_transport.connect = AsyncMock()
    acct_session.mammotion_transport = existing_transport

    already_registered = _make_device_record("Luba-OLD")
    new_device = _make_device_record("Yuka-NEW")
    mock_http = _make_mock_http(device_records=[already_registered, new_device])

    register_mock = AsyncMock()
    with patch.object(client, "_register_mammotion_device", register_mock):
        await client._bootstrap_mammotion_mqtt(
            "u@x.com", mock_http, acct_session, {}, skip_ids={"Luba-OLD"}
        )

    registered_names = [call.args[0].device_name for call in register_mock.await_args_list]
    assert registered_names == ["Yuka-NEW"]
    assert "Luba-OLD" not in registered_names

async def test_restore_credentials_connect_called_exactly_once_when_cache_has_devices() -> None:
    """restore_credentials with cached Mammotion MQTT devices must call connect() exactly once.

    _restore_mammotion_mqtt connects the transport; the subsequent _bootstrap_mammotion_mqtt
    call must reuse the existing transport (new_transport=False) and NOT connect again.
    """
    from pymammotion.http.model.http import MQTTConnection

    client = MammotionClient()

    mqtt_creds = MQTTConnection(host="h", client_id="c", username="u", jwt="j")
    cached_record = _make_device_record("Luba-OLD")

    cached_data = {
        "mammotion_mqtt": mqtt_creds.to_dict(),
        "mammotion_device_records": {
            "records": [
                {
                    "identityId": "id1", "iotId": "iot-old", "productKey": "pk1",
                    "deviceName": "Luba-OLD", "owned": 1, "status": 1,
                    "bindTime": 0, "createTime": "2024-01-01",
                }
            ],
            "total": 1, "size": 100, "current": 1, "pages": 1,
        },
    }

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    mock_http = _make_mock_http(
        device_records=[cached_record, _make_device_record("Yuka-NEW")],
        mqtt_creds=mqtt_creds,
    )
    mock_http.device_records = MagicMock(records=[cached_record])

    with (
        patch.object(client, "_setup_mammotion_transport", return_value=mock_transport),
        patch.object(client, "_register_mammotion_device", AsyncMock()),
        patch("pymammotion.client.MammotionHTTP.from_cache", return_value=mock_http),
        patch("pymammotion.http.http.MammotionHTTP.login_v2", new_callable=AsyncMock) as mock_login,
    ):
        mock_login.return_value = MagicMock(code=0)
        await client.restore_credentials(
            "u@x.com", "pass", cached_data, check_for_new_devices=True
        )

    # connect() must be called exactly once — from _restore_mammotion_mqtt, not again from bootstrap
    mock_transport.connect.assert_awaited_once()
    # A restorable, still-accepted login never falls back to a password grant.
    mock_login.assert_not_awaited()

async def test_restore_credentials_no_mammotion_cache_bootstraps_fresh() -> None:
    """restore_credentials with no mammotion_mqtt cache must bootstrap a fresh transport.

    When the account has only Aliyun credentials cached and a Mammotion MQTT device
    (e.g. a Yuka) appears, restore_credentials must discover it and call connect() once.
    """
    client = MammotionClient()

    mock_http = _make_mock_http(device_records=[_make_device_record("Yuka-NEW")])
    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = mock_http
    mock_cloud.devices_by_account_response = None
    mock_cloud.aep_response = None

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    cached_data = {"aep_data": {"some": "data"}}

    with (
        patch("pymammotion.client.MammotionHTTP.from_cache", return_value=mock_http),
        patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock(return_value=mock_cloud)),
        patch.object(client, "_setup_aliyun_transport", return_value=MagicMock()),
        patch.object(client, "_setup_mammotion_transport", return_value=mock_transport),
        patch.object(client, "_register_mammotion_device", AsyncMock()),
    ):
        await client.restore_credentials(
            "u@x.com", "pass", cached_data, check_for_new_devices=True
        )

    # The Mammotion MQTT bootstrap must have connected the new transport once
    mock_transport.connect.assert_awaited_once()

# ---------------------------------------------------------------------------
# restore_credentials — the login comes first
# ---------------------------------------------------------------------------

async def test_unrestorable_cache_falls_back_to_a_full_login() -> None:
    """A cache that yields no login session must go straight to a full login.

    No transport restore may run first: without a validated login there is nothing
    for a gateway or an MQTT transport to hang off.
    """
    client = MammotionClient()

    with (
        patch.object(client, "login_and_initiate_cloud", AsyncMock()) as mock_login,
        patch.object(client, "_restore_aliyun", AsyncMock()) as mock_aliyun,
        patch.object(client, "_restore_mammotion_mqtt", AsyncMock()) as mock_mammotion,
    ):
        await client.restore_credentials("u@x.com", "pass", {"aep_data": {"some": "data"}})

    mock_login.assert_awaited_once()
    mock_aliyun.assert_not_awaited()
    mock_mammotion.assert_not_awaited()

async def test_rejected_login_falls_back_to_a_full_login() -> None:
    """A restorable cache the server no longer accepts is not usable either."""
    client = MammotionClient()
    http = _populated_mammotion_http("u@x.com")
    http.validate_login = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with (
        patch("pymammotion.client.MammotionHTTP.from_cache", return_value=http),
        patch.object(client, "login_and_initiate_cloud", AsyncMock()) as mock_login,
        patch.object(client, "_restore_aliyun", AsyncMock()) as mock_aliyun,
    ):
        await client.restore_credentials("u@x.com", "pass", {"aep_data": {"some": "data"}})

    mock_login.assert_awaited_once()
    mock_aliyun.assert_not_awaited()

async def test_a_rotation_during_validation_is_persisted() -> None:
    """A refresh performed while validating the cached login must reach the host.

    Regression for the 40102 loop.  The server invalidates the previous refresh token
    the instant a rotation succeeds, so a rotation nobody persists leaves the cache
    replaying a spent token: every later run gets "Refresh token has expired" on
    credentials whose own `exp` is weeks away.  Only TokenManager wires
    MammotionHTTP.on_login_refreshed to the persistence callback, so it must be in
    place before validate_login can trigger a refresh — not after.
    """
    client = MammotionClient()
    persisted: list[str] = []

    async def _persist() -> None:
        http = client._account_registry.get("u@x.com").mammotion_http  # type: ignore[union-attr]
        persisted.append(http.login_info.refresh_token)  # type: ignore[union-attr]

    client.on_credentials_updated = _persist

    http = _populated_mammotion_http("u@x.com")

    async def _validate() -> bool:
        # Stand in for the refresh ensure_token_valid performs near expiry: rotate the
        # tokens exactly as _refresh_token_v2_locked does, hook included.
        http.login_info.refresh_token = "rotated-rt"  # type: ignore[union-attr]
        await http._fire_login_refreshed()
        return True

    http.validate_login = _validate  # type: ignore[method-assign]

    with patch("pymammotion.client.MammotionHTTP.from_cache", return_value=http):
        await client.restore_credentials(
            "u@x.com", "pass", {"mammotion_data": http.response}, check_for_new_devices=False
        )

    assert persisted == ["rotated-rt"]

async def test_hybrid_restore_shares_one_http_and_one_token_manager() -> None:
    """Aliyun + Mammotion in one cache must produce exactly one login and one manager.

    Both branches read the session restore_credentials established, and the Aliyun
    gateway is attached to that manager rather than used to build a second one.
    """
    client = MammotionClient()
    persist = AsyncMock()
    client.on_credentials_updated = persist

    http = _populated_mammotion_http("u@x.com")
    http.validate_login = AsyncMock(return_value=True)  # type: ignore[method-assign]
    http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))  # type: ignore[method-assign]

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = http
    mock_cloud.devices_by_account_response = None
    mock_cloud.check_or_refresh_session = AsyncMock()
    mock_cloud.list_binding_by_account = AsyncMock(return_value=MagicMock(data=None))

    mammotion_transport = MagicMock()
    mammotion_transport.connect = AsyncMock()

    cached_data = _cached_from(http, aep_data={"some": "data"})

    with (
        patch("pymammotion.client.MammotionHTTP.from_cache", return_value=http),
        patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock(return_value=mock_cloud)),
        patch.object(client, "_setup_aliyun_transport", return_value=MagicMock()),
        patch.object(client, "_setup_mammotion_transport", return_value=mammotion_transport),
        patch.object(client, "_start_token_refresh", MagicMock()),
    ):
        await client.restore_credentials("u@x.com", "pass", cached_data, check_for_new_devices=False)

    acct_session = client._account_registry.get("u@x.com")
    assert acct_session is not None
    assert acct_session.mammotion_http is http
    token_manager = acct_session.token_manager
    assert token_manager is not None
    assert token_manager.http is http
    assert token_manager.cloud_gateway is mock_cloud
    # The persistence callback must survive both branches — a rotation nobody stores
    # leaves the cached refresh token dead on the next restart.
    assert token_manager.on_credentials_updated is persist
    # The manager adopted the credentials the restored session already carries, so the
    # first MQTT send doesn't spend a round-trip re-fetching a JWT we have.
    assert token_manager._mqtt_creds is not None
    assert token_manager._mqtt_creds.host == "mqtt.example.com"

async def test_restoring_twice_never_leaves_two_token_managers() -> None:
    """A re-restore must retire the previous manager, not run a second one beside it.

    Two managers for one account means two refresh schedulers rotating the same
    refresh token concurrently, and transports still holding the retired one — so its
    terminal flags land where the session no longer looks.
    """
    client = MammotionClient()
    # Login-only cache: this is about the manager, so no transport branch should run.
    cached_data = {"mammotion_data": _populated_mammotion_http("u@x.com").response}

    first_http = _populated_mammotion_http("u@x.com")
    first_http.validate_login = AsyncMock(return_value=True)  # type: ignore[method-assign]

    with (
        patch("pymammotion.client.MammotionHTTP.from_cache", return_value=first_http),
        patch.object(client, "_start_token_refresh", MagicMock()),
    ):
        await client.restore_credentials("u@x.com", "pass", cached_data, check_for_new_devices=False)

    acct_session = client._account_registry.get("u@x.com")
    assert acct_session is not None
    first_tm = acct_session.token_manager
    assert first_tm is not None
    first_tm.stop_refresh_scheduler = AsyncMock()  # type: ignore[method-assign]

    # A second restore mints a new login session, so the old manager is refreshing
    # something nothing reads any more.
    second_http = _populated_mammotion_http("u@x.com")
    second_http.validate_login = AsyncMock(return_value=True)  # type: ignore[method-assign]

    with (
        patch("pymammotion.client.MammotionHTTP.from_cache", return_value=second_http),
        patch.object(client, "_start_token_refresh", MagicMock()),
    ):
        await client.restore_credentials("u@x.com", "pass", cached_data, check_for_new_devices=False)

    second_tm = acct_session.token_manager
    assert second_tm is not first_tm
    assert second_tm is not None
    assert second_tm.http is second_http
    first_tm.stop_refresh_scheduler.assert_awaited_once()

async def test_restoring_the_same_login_reuses_its_token_manager() -> None:
    """An unchanged login session keeps its manager — scheduler, flags and all."""
    client = MammotionClient()
    http = _populated_mammotion_http("u@x.com")
    http.validate_login = AsyncMock(return_value=True)  # type: ignore[method-assign]
    cached_data = {"mammotion_data": http.response}

    with (
        patch("pymammotion.client.MammotionHTTP.from_cache", return_value=http),
        patch.object(client, "_start_token_refresh", MagicMock()),
    ):
        await client.restore_credentials("u@x.com", "pass", cached_data, check_for_new_devices=False)
        acct_session = client._account_registry.get("u@x.com")
        assert acct_session is not None
        first_tm = acct_session.token_manager
        assert first_tm is not None
        first_tm.stop_refresh_scheduler = AsyncMock()  # type: ignore[method-assign]

        await client.restore_credentials("u@x.com", "pass", cached_data, check_for_new_devices=False)

    assert acct_session.token_manager is first_tm
    first_tm.stop_refresh_scheduler.assert_not_awaited()

async def test_credentials_callback_reaches_every_account() -> None:
    """on_credentials_updated is per-account state, not just the default session's.

    Each account refreshes its own credentials, and a rotation that isn't persisted
    leaves that account's cached refresh token dead on the next restart.
    """
    from pymammotion.auth.token_manager import TokenManager

    client = MammotionClient()
    sessions = []
    for account in ("a@x.com", "b@x.com"):
        acct_session = AccountSession(account_id=account, email=account, password="pass")
        acct_session.mammotion_http = _populated_mammotion_http(account)
        acct_session.token_manager = TokenManager(account, acct_session.mammotion_http)
        await client._account_registry.register(acct_session)
        sessions.append(acct_session)

    persist = AsyncMock()
    client.on_credentials_updated = persist

    assert [s.token_manager.on_credentials_updated for s in sessions] == [persist, persist]  # type: ignore[union-attr]

async def test_relogin_does_not_revoke_the_session_it_is_replacing() -> None:
    """A re-login must not end the old session server-side before minting its replacement.

    login_v2 supersedes the previous session anyway, so calling logout first only
    creates a window where the host's cached credentials are already dead.  If the
    login (or the save that follows) then fails, the cache can only ever answer 401
    and 40102 "Refresh token has expired" — recoverable only by a manual re-login.
    """
    client = MammotionClient()
    acct_session = AccountSession(account_id="u@x.com", email="u@x.com", password="pass")
    old_http = _populated_mammotion_http("u@x.com")
    old_http.logout = AsyncMock()  # type: ignore[method-assign]
    acct_session.mammotion_http = old_http
    old_cloud = MagicMock()
    old_cloud.sign_out = AsyncMock()
    acct_session.cloud_client = old_cloud
    await client._account_registry.register(acct_session)

    new_http = _make_mock_http()
    new_http.login_v2 = AsyncMock(return_value=MagicMock(code=0))
    # No Aliyun devices and no Mammotion records: this test is about the teardown,
    # not about what gets registered afterwards.
    new_http.get_user_shared_device_page = AsyncMock(return_value=MagicMock(data=None))
    new_http.get_user_device_page = AsyncMock(return_value=MagicMock(data=MagicMock(records=[])))

    with (
        patch("pymammotion.client.MammotionHTTP", return_value=new_http),
        patch.object(client, "_start_token_refresh", MagicMock()),
    ):
        await client.login_and_initiate_cloud("u@x.com", "pass")

    old_http.logout.assert_not_awaited()
    old_cloud.sign_out.assert_not_awaited()
    # The replacement is still what the account ends up with.
    assert client._account_registry.get("u@x.com").mammotion_http is new_http  # type: ignore[union-attr]
