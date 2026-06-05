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
    return http

async def test_token_manager_set_after_restore_aliyun() -> None:
    """_restore_aliyun must set token_manager on the session."""
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = MagicMock()
    mock_cloud.mammotion_http.login_info = None
    mock_cloud.devices_by_account_response = None

    with (
        patch("pymammotion.client.CloudIOTGateway.from_cache", AsyncMock(return_value=mock_cloud)),
        patch.object(client, "_setup_aliyun_transport", return_value=MagicMock()),
    ):
        await client._restore_aliyun(
            "user@test.com", "pass", {}, acct_session, check_for_new_devices=False
        )

    assert acct_session.token_manager is not None

async def test_restore_aliyun_refreshes_session_before_device_list() -> None:
    """_restore_aliyun must check/refresh the Aliyun session before listing devices.

    The cached iotToken may have expired; list_binding_by_account uses it directly
    and would 401/460 otherwise.
    """
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    order: list[str] = []

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = MagicMock()
    mock_cloud.mammotion_http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))
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
        await client._restore_aliyun(
            "user@test.com", "pass", {}, acct_session, check_for_new_devices=True
        )

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

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = MagicMock()
    mock_cloud.mammotion_http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))
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
        await client._restore_aliyun(
            "user@test.com", "pass", {}, acct_session, check_for_new_devices=True
        )

    # The device-list call ran with the refreshed token (set on the gateway), not the stale one.
    assert token_seen_by_list == ["refreshed-token"]
    assert mock_cloud.session_by_authcode_response.data.iotToken == "refreshed-token"

async def test_token_manager_set_after_restore_mammotion_mqtt() -> None:
    """_restore_mammotion_mqtt must set token_manager on the session when mqtt_creds are present."""
    from pymammotion.http.model.http import MQTTConnection

    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    mqtt_creds = MQTTConnection(
        host="mqtt.example.com",
        client_id="client-1",
        username="user",
        jwt="token",
    )
    cached_data = {
        "mammotion_mqtt": mqtt_creds.to_dict(),
        "mammotion_device_records": {"records": []},
    }

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    with (
        patch.object(client, "_setup_mammotion_transport", return_value=mock_transport),
        patch("pymammotion.http.http.MammotionHTTP.login_v2", new_callable=AsyncMock) as mock_login,
    ):
        mock_login.return_value = MagicMock(code=0, data=MagicMock())
        await client._restore_mammotion_mqtt(
            "user@test.com", "pass", cached_data, None, acct_session
        )

    assert acct_session.token_manager is not None
    # The cached MQTT credentials must actually be restored onto the http object,
    # not merely accepted.  (Catches the `data`/`cached_data` NameError regression.)
    assert acct_session.mammotion_http is not None
    assert acct_session.mammotion_http.mqtt_credentials is not None
    assert acct_session.mammotion_http.mqtt_credentials.host == "mqtt.example.com"

async def test_restore_mammotion_mqtt_reuses_existing_http_for_hybrid_account() -> None:
    """Hybrid (Aliyun+Mammotion) account must keep ONE MammotionHTTP.

    Regression: _restore_aliyun runs first and sets acct_session.mammotion_http (A)
    plus a TokenManager bound to A.  _restore_mammotion_mqtt used to create a *new*
    MammotionHTTP (B) for the transport while keeping the A-bound TokenManager, so a
    401-driven refresh updated A's token while mqtt_invoke kept sending B's dead
    token — an unrecoverable 401 loop.  The transport and its TokenManager must share
    the same instance.
    """
    from pymammotion.auth.token_manager import TokenManager

    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    # State left by a preceding _restore_aliyun: an authenticated http (A) + bound TM.
    http_a = _populated_mammotion_http()
    acct_session.mammotion_http = http_a
    acct_session.token_manager = TokenManager("user@test.com", http_a)

    mqtt_creds = MQTTConnection(host="mqtt.example.com", client_id="client-1", username="user", jwt="token")
    cached_data = {
        "mammotion_mqtt": mqtt_creds.to_dict(),
        "mammotion_device_records": {"records": []},
    }

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
        await client._restore_mammotion_mqtt("user@test.com", "pass", cached_data, None, acct_session)

    # The account's http must NOT be replaced, and transport + token manager must be
    # wired to that same instance.
    assert acct_session.mammotion_http is http_a
    assert captured["http"] is http_a
    assert captured["tm"].http is http_a  # type: ignore[attr-defined]

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
    """A full to_cache() → JSON → restore round-trip preserves MQTT creds and JWT info.

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
    client = MammotionClient()
    acct_session = AccountSession(account_id="user@test.com", email="user@test.com", password="pass")

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()
    with (
        patch.object(client, "_setup_mammotion_transport", return_value=mock_transport),
        patch("pymammotion.client.MammotionHTTP.get_user_device_list", new_callable=AsyncMock) as mock_list,
    ):
        mock_list.return_value = MagicMock(data=[])
        await client._restore_mammotion_mqtt("user@test.com", "pass", cached_data, None, acct_session)

    http = acct_session.mammotion_http
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
    )

    with (
        patch.object(client, "_setup_mammotion_transport", return_value=mock_transport),
        patch.object(client, "_register_mammotion_device", AsyncMock()),
        patch("pymammotion.client.MammotionHTTP", return_value=mock_http),
        patch("pymammotion.http.http.MammotionHTTP.login_v2", new_callable=AsyncMock) as mock_login,
    ):
        mock_login.return_value = MagicMock(code=0)
        await client.restore_credentials(
            "u@x.com", "pass", cached_data, check_for_new_devices=True
        )

    # connect() must be called exactly once — from _restore_mammotion_mqtt, not again from bootstrap
    mock_transport.connect.assert_awaited_once()

async def test_restore_credentials_no_mammotion_cache_bootstraps_fresh() -> None:
    """restore_credentials with no mammotion_mqtt cache must bootstrap a fresh transport.

    When the account has only Aliyun credentials cached and a Mammotion MQTT device
    (e.g. a Yuka) appears, restore_credentials must discover it and call connect() once.
    """
    client = MammotionClient()

    mock_cloud = MagicMock()
    mock_cloud.mammotion_http = _make_mock_http(
        device_records=[_make_device_record("Yuka-NEW")],
    )
    mock_cloud.devices_by_account_response = None
    mock_cloud.aep_response = None

    mock_transport = MagicMock()
    mock_transport.connect = AsyncMock()

    cached_data = {"aep_data": {"some": "data"}}

    with (
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
