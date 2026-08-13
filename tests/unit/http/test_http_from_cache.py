"""Tests for restoring a login session from a credential cache.

Two halves, deliberately separate:

- ``MammotionHTTP.from_cache`` is pure — it decodes a cache dict and performs no
  I/O.  A cache is untrusted input (written by an older version, hand-edited,
  truncated, or still holding live models), so it must degrade to ``None`` rather
  than raise from the middle of a restore.
- ``MammotionHTTP.validate_login`` decides whether the restored session is usable.
  It is a local expiry check that only reaches the network when the token is inside
  the refresh lead window; a rejected refresh is the one thing that marks the cached
  login unusable.  There is deliberately no server-side "is this token live" probe:
  ``/user/oauth/check`` answered 404 on live accounts, so every restore refreshed —
  spending the cached refresh token — and then fell back to a full login anyway.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

from aiohttp import ClientError
import jwt as pyjwt
import pytest

from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import (
    DeviceInfo,
    DeviceRecords,
    JWTTokenInfo,
    LoginResponseData,
    LoginResponseUserInformation,
    MQTTConnection,
    Response,
    UnauthorizedExceptionError,
)
from pymammotion.transport.base import ReLoginRequiredError

_EXP = 9999999999


def _access_token(iot: str = "token-iot", robot: str = "token-robot", exp: int = _EXP) -> str:
    """Mint an unsigned-verifiable access token carrying the iot/robot/exp claims."""
    return pyjwt.encode({"iot": iot, "robot": robot, "exp": exp}, "x" * 32, algorithm="HS256")


def _login_data(access_token: str | None = None) -> LoginResponseData:
    """A complete login payload as the oauth2/token endpoint returns it."""
    return LoginResponseData(
        access_token=access_token if access_token is not None else _access_token(),
        token_type="bearer",
        refresh_token="rt",
        expires_in=3600,
        authorization_code="ac",
        userInformation=LoginResponseUserInformation(
            areaCode="44", domainAbbreviation="EU", userId="u1", userAccount="123", authType="email"
        ),
    )


def _cache(**overrides: object) -> dict:
    """A full cache dict of live models, as ``MammotionClient.to_cache`` produces."""
    raw: dict[str, object] = {
        "mammotion_data": Response(code=0, msg="ok", data=_login_data()),
        "mammotion_mqtt": MQTTConnection(host="mqtt.example.com", jwt="jwt-token", client_id="c1", username="u"),
        "mammotion_jwt_info": JWTTokenInfo(iot="cached-iot", robot="cached-robot"),
        "mammotion_device_records": DeviceRecords(records=[], current=1, total=0, size=100, pages=0),
    }
    raw.update(overrides)
    return raw


def _json_cache(**overrides: object) -> dict:
    """The same cache after a round-trip through JSON, as the host persists it."""
    import orjson

    raw = {k: (orjson.loads(v.to_json()) if hasattr(v, "to_json") else v) for k, v in _cache().items()}
    raw.update(overrides)
    return raw


# ---------------------------------------------------------------------------
# from_cache — the happy paths
# ---------------------------------------------------------------------------


def test_restores_every_field_from_live_models() -> None:
    """A cache of live models restores the whole session."""
    http = MammotionHTTP.from_cache(_cache(), "user@test.com", "pw")

    assert http is not None
    assert http.account == "user@test.com"
    assert http.login_info is not None
    assert http.login_info.refresh_token == "rt"
    assert http.response is not None
    assert http.mqtt_credentials is not None
    assert http.mqtt_credentials.host == "mqtt.example.com"
    assert http.device_records.size == 100


def test_restores_every_field_from_json_dicts() -> None:
    """The same cache after JSON persistence restores identically."""
    http = MammotionHTTP.from_cache(_json_cache(), "user@test.com", "pw")

    assert http is not None
    assert http.login_info is not None
    assert http.login_info.refresh_token == "rt"
    # A dict `data` must be decoded into the model, not left as a dict — the
    # response setter dereferences .access_token on it.
    assert isinstance(http.login_info, LoginResponseData)
    assert http.mqtt_credentials is not None
    assert http.mqtt_credentials.jwt == "jwt-token"
    assert http.device_records.size == 100


def test_expiry_comes_from_the_access_token_exp_claim() -> None:
    """expires_in is seeded from the JWT so a warm cache costs no refresh."""
    http = MammotionHTTP.from_cache(_cache(), "user@test.com", "pw")

    assert http is not None
    assert http.expires_in == float(_EXP)


def test_cached_jwt_info_wins_over_the_token_derived_one() -> None:
    """The cached JWT is what the live session was using — it must survive the restore."""
    http = MammotionHTTP.from_cache(_cache(), "user@test.com", "pw")

    assert http is not None
    assert http.jwt_info.iot == "cached-iot"
    assert http.jwt_info.robot == "cached-robot"


def test_device_list_is_restored() -> None:
    """mammotion_device_list is written only by the Aliyun branch of to_cache."""
    device = DeviceInfo(iot_id="iot-1", device_name="Luba-TEST")
    http = MammotionHTTP.from_cache(_cache(mammotion_device_list=[device.to_dict()]), "user@test.com", "pw")

    assert http is not None
    assert [d.device_name for d in http.device_info] == ["Luba-TEST"]

    # Live models survive too, and an entry the cache mangled is dropped rather than
    # planted in the list for a later reader to trip over.
    http = MammotionHTTP.from_cache(_cache(mammotion_device_list=[device, "junk"]), "user@test.com", "pw")
    assert http is not None
    assert http.device_info == [device]


def test_optional_fields_may_all_be_absent() -> None:
    """A login-only cache still produces a usable session."""
    http = MammotionHTTP.from_cache({"mammotion_data": Response(code=0, msg="ok", data=_login_data())})

    assert http is not None
    assert http.login_info is not None
    assert http.mqtt_credentials is None
    assert http.device_records.records == []


# ---------------------------------------------------------------------------
# from_cache — a bad cache degrades, it never raises
# ---------------------------------------------------------------------------


def test_missing_login_data_returns_none() -> None:
    """No mammotion_data → nothing to restore."""
    assert MammotionHTTP.from_cache({"mammotion_mqtt": {"host": "h"}}) is None


def test_null_login_data_returns_none() -> None:
    """A Response whose data never arrived carries no access token."""
    assert MammotionHTTP.from_cache({"mammotion_data": Response(code=0, msg="ok", data=None)}) is None


def test_empty_access_token_returns_none() -> None:
    """An access token we cannot send is not a session."""
    assert MammotionHTTP.from_cache({"mammotion_data": Response(code=0, msg="ok", data=_login_data(""))}) is None


def test_nested_live_model_inside_a_dict_returns_none_instead_of_raising() -> None:
    """Regression: the cache shape that used to escape as mashumaro InvalidFieldValue.

    A half-serialised cache — outer Response as a dict, inner `data` still a live
    model — is what a host writes when it stringifies only the top level.  It used
    to raise out of CloudIOTGateway.from_cache, past the caller's own None-check,
    and abort the whole restore instead of falling back to a login.
    """
    half_serialised = {"code": 0, "msg": "ok", "data": _login_data()}

    assert MammotionHTTP.from_cache({"mammotion_data": half_serialised}) is None


def test_garbage_login_data_returns_none() -> None:
    """Truncated / hand-edited caches are untrusted input, not a crash."""
    assert MammotionHTTP.from_cache({"mammotion_data": {"code": 0, "msg": "ok"}}) is None
    assert MammotionHTTP.from_cache({"mammotion_data": "not-a-response"}) is None


def test_undecodable_access_token_returns_none() -> None:
    """The response setter decodes the token; a non-JWT there is not a usable session."""
    assert MammotionHTTP.from_cache({"mammotion_data": Response(code=0, msg="ok", data=_login_data("nope"))}) is None


def test_malformed_mqtt_credentials_cost_only_the_mqtt_credentials() -> None:
    """One bad optional field must not take the login session down with it."""
    http = MammotionHTTP.from_cache(_cache(mammotion_mqtt={"host": "h"}))

    assert http is not None
    assert http.login_info is not None
    assert http.mqtt_credentials is None


def test_malformed_optional_fields_leave_the_rest_intact() -> None:
    """A bad JWT block keeps the token-derived one; bad records keep the empty default."""
    http = MammotionHTTP.from_cache(_cache(mammotion_jwt_info={"bogus": 1}, mammotion_device_records="nope"))

    assert http is not None
    assert http.jwt_info.iot == "token-iot"  # derived from the access token
    assert http.device_records.records == []
    assert http.mqtt_credentials is not None  # untouched by its neighbours' failures


# ---------------------------------------------------------------------------
# validate_login
# ---------------------------------------------------------------------------


def _restored() -> MammotionHTTP:
    """A session restored from a warm cache: token valid for years."""
    http = MammotionHTTP.from_cache(_cache(), "user@test.com", "pw")
    assert http is not None
    return http


async def test_a_warm_cache_validates_without_spending_a_refresh() -> None:
    """A token nowhere near expiry is accepted as-is — no rotation, one probe.

    Every rotation invalidates the previous refresh token server-side, so a restore
    that refreshes when it did not have to is not merely wasteful: if that rotation
    is ever lost, the cached token is dead for good.
    """
    http = _restored()
    http.get_user_device_list = AsyncMock(return_value=Response(code=0, msg="ok", data=[]))  # type: ignore[method-assign]

    with patch.object(MammotionHTTP, "_refresh_token_v2_locked", new_callable=AsyncMock) as mock_refresh:
        assert await http.validate_login() is True

    mock_refresh.assert_not_awaited()
    http.get_user_device_list.assert_awaited_once()


async def test_near_expiry_token_is_refreshed() -> None:
    """Inside the 5-minute lead window, validation renews before handing the login on."""
    http = _restored()
    http.expires_in = time.time() + 60
    http.get_user_device_list = AsyncMock(return_value=Response(code=0, msg="ok", data=[]))  # type: ignore[method-assign]

    with patch.object(MammotionHTTP, "_refresh_token_v2_locked", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.return_value = Response(code=0, msg="ok", data=_login_data())
        assert await http.validate_login() is True

    mock_refresh.assert_awaited_once()


async def test_a_revoked_session_is_detected_even_though_the_token_looks_fresh() -> None:
    """The case a local expiry check cannot see: logged out, or signed in elsewhere.

    The token's own exp is weeks away, so without a real call the restore reports
    success and the user gets an integration that fails on its first command.
    """
    http = _restored()
    http.get_user_device_list = AsyncMock(side_effect=UnauthorizedExceptionError("Access Token expired"))  # type: ignore[method-assign]

    assert await http.validate_login() is False


async def test_probe_transient_failure_does_not_condemn_the_login() -> None:
    """A network blip must not be reported as a rejected session.

    Returning False here would send the caller to a password grant for a login that
    is probably still perfectly good.
    """
    http = _restored()
    http.get_user_device_list = AsyncMock(side_effect=ClientError("boom"))  # type: ignore[method-assign]

    with pytest.raises(ClientError):
        await http.validate_login()


async def test_dead_refresh_token_reports_invalid() -> None:
    """ReLoginRequiredError from the proactive refresh means the cache is spent."""
    http = _restored()
    with patch.object(
        MammotionHTTP, "ensure_token_valid", AsyncMock(side_effect=ReLoginRequiredError("user@test.com", "dead"))
    ):
        assert await http.validate_login() is False


async def test_no_login_session_is_invalid() -> None:
    """Nothing to validate, and nothing to refresh."""
    http = MammotionHTTP("user@test.com", "pw")

    with patch.object(MammotionHTTP, "ensure_token_valid", new_callable=AsyncMock) as mock_ensure:
        assert await http.validate_login() is False

    mock_ensure.assert_not_awaited()


