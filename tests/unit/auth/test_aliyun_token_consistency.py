"""Thorough consistency tests for the Aliyun iotToken across CloudIOTGateway and TokenManager.

The 401-on-restore investigation hinges on one invariant: the iotToken that
``list_binding_by_account`` sends (read straight off
``CloudIOTGateway._session_by_authcode_response.data.iotToken``) must always equal the
token the ``TokenManager`` last derived.  These tests walk every refresh entry point and
assert the gateway and the token manager stay in lockstep, that a fresh token is NOT
re-fetched, and that a refresh genuinely replaces the token everywhere.

The mock Aliyun backend hands out a brand-new iotToken on *every* checkOrRefreshSession
call, so "stale token" regressions surface immediately as a mismatch.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.model.regions_response import RegionResponse, RegionResponseData
from pymammotion.aliyun.model.session_by_authcode_response import (
    SessionByAuthCodeResponse,
    SessionOauthToken,
)
from pymammotion.auth.token_manager import AliyunCredentials, TokenManager
from pymammotion.transport.base import ReLoginRequiredError, SessionExpiredError, TransportType

_IOT_TOKEN_EXPIRE = 72_000  # 20 h, matching the real Aliyun value
_REFRESH_TOKEN_EXPIRE = 720_000


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _session(iot_token: str, iot_token_expire: int = _IOT_TOKEN_EXPIRE) -> SessionByAuthCodeResponse:
    return SessionByAuthCodeResponse(
        code=200,
        data=SessionOauthToken(
            identityId="identity-1",
            refreshTokenExpire=_REFRESH_TOKEN_EXPIRE,
            iotToken=iot_token,
            iotTokenExpire=iot_token_expire,
            refreshToken="refresh-0",
        ),
    )


def _region() -> RegionResponse:
    return RegionResponse(
        code=200,
        data=RegionResponseData(
            shortRegionId="EU",
            oaApiGatewayEndpoint="oa.example.com",
            regionId="EU",
            mqttEndpoint="mqtt.example.com:1883",
            pushChannelEndpoint="push.example.com",
            regionEnglishName="Europe",
            apiGatewayEndpoint="api.example.com",
        ),
    )


def _make_gateway(initial_token: str = "iot-token-initial", *, age: int = 0) -> CloudIOTGateway:
    """A real gateway carrying ``initial_token``, issued ``age`` seconds ago."""
    gw = CloudIOTGateway(
        mammotion_http=MagicMock(),
        session_by_authcode_response=_session(initial_token),
        region_response=_region(),
    )
    gw._iot_token_issued_at = int(time.time()) - age  # noqa: SLF001
    return gw


def _make_token_manager(gw: CloudIOTGateway) -> TokenManager:
    """TokenManager wired to ``gw`` with the HTTP refresh stubbed (force_refresh calls it first)."""
    tm = TokenManager("acc@test.com", gw.mammotion_http, gw)
    tm.refresh_http = AsyncMock()  # type: ignore[method-assign]
    return tm


def _fresh_creds(iot_token: str) -> AliyunCredentials:
    now = time.time()
    return AliyunCredentials(
        iot_token=iot_token,
        iot_token_expires_at=now + _IOT_TOKEN_EXPIRE,
        refresh_token="refresh-0",
        refresh_token_expires_at=now + _REFRESH_TOKEN_EXPIRE,
    )


class _AliyunBackend:
    """Mock Aliyun gateway backend that hands out a NEW iotToken on every refresh call.

    Patches ``cloud_gateway.Client`` so the *real* ``check_or_refresh_session`` and
    ``list_binding_by_account`` code runs (real token assignment), while the network is
    faked.  Records every token issued and the iotToken carried by the last device-list
    request so tests can assert the refreshed token flows through.
    """

    def __init__(self, iot_token_expire: int = _IOT_TOKEN_EXPIRE) -> None:
        self.refresh_calls = 0
        self.issued: list[str] = []
        self.iot_token_expire = iot_token_expire
        self.last_list_iot_token: str | None = None

    @property
    def latest(self) -> str:
        return self.issued[-1]

    def _respond(self, path: str, *args: object, **kwargs: object) -> MagicMock:
        # async_do_request(path, scheme, method, headers, body, options)
        body = args[3] if len(args) >= 4 else kwargs.get("body")
        resp = MagicMock()
        if path == "/account/checkOrRefreshSession":
            self.refresh_calls += 1
            token = f"iot-token-{self.refresh_calls}"
            self.issued.append(token)
            resp.body = orjson.dumps(
                {
                    "code": 200,
                    "data": {
                        "identityId": "identity-1",
                        "refreshTokenExpire": _REFRESH_TOKEN_EXPIRE,
                        "iotToken": token,
                        "iotTokenExpire": self.iot_token_expire,
                        "refreshToken": f"refresh-{self.refresh_calls}",
                    },
                }
            )
        elif path == "/uc/listBindingByAccount":
            self.last_list_iot_token = body.request.iot_token  # type: ignore[union-attr]
            resp.body = orjson.dumps({"code": 200, "data": {"total": 0, "data": [], "pageNo": 1, "pageSize": 100}})
        else:
            resp.body = orjson.dumps({"code": 200})
        return resp

    def patch(self) -> object:
        mock_client = MagicMock()
        mock_client.async_do_request = AsyncMock(side_effect=self._respond)
        return patch("pymammotion.aliyun.cloud_gateway.Client", return_value=mock_client)


def _assert_consistent(tm: TokenManager, gw: CloudIOTGateway, expected: str | None = None) -> None:
    """The TokenManager's cached iotToken must equal the gateway's session iotToken."""
    gw_token = gw.session_by_authcode_response.data.iotToken  # type: ignore[union-attr]
    tm_token = tm._aliyun_creds.iot_token  # noqa: SLF001
    assert tm_token == gw_token, f"TokenManager ({tm_token}) and gateway ({gw_token}) diverged"
    if expected is not None:
        assert gw_token == expected


# ---------------------------------------------------------------------------
# Gateway token is stable until a refresh
# ---------------------------------------------------------------------------


def test_gateway_token_is_stable_across_reads() -> None:
    """Reading the gateway session token repeatedly must not mutate it."""
    gw = _make_gateway("iot-token-initial")
    first = gw.session_by_authcode_response.data.iotToken  # type: ignore[union-attr]
    for _ in range(5):
        assert gw.session_by_authcode_response.data.iotToken == first  # type: ignore[union-attr]
    assert first == "iot-token-initial"


async def test_get_aliyun_credentials_without_gateway_raises() -> None:
    """A TokenManager with no gateway cannot serve Aliyun credentials."""
    tm = TokenManager("acc@test.com", MagicMock())
    with pytest.raises(RuntimeError, match="Aliyun cloud gateway"):
        await tm.get_aliyun_credentials()


# ---------------------------------------------------------------------------
# Fresh token: no refresh, token unchanged everywhere
# ---------------------------------------------------------------------------


async def test_fresh_credentials_returned_without_touching_gateway() -> None:
    """A still-valid cached token is returned via the fast path; the gateway is not called."""
    gw = _make_gateway("iot-token-initial")
    tm = _make_token_manager(gw)
    tm._aliyun_creds = _fresh_creds("iot-token-initial")  # noqa: SLF001
    gw.check_or_refresh_session = AsyncMock()  # type: ignore[method-assign] — spy: must NOT fire

    creds = await tm.get_aliyun_credentials()

    assert creds.iot_token == "iot-token-initial"
    gw.check_or_refresh_session.assert_not_awaited()
    # Token unchanged in both places.
    assert gw.session_by_authcode_response.data.iotToken == "iot-token-initial"  # type: ignore[union-attr]
    assert tm._aliyun_creds.iot_token == "iot-token-initial"  # noqa: SLF001


# ---------------------------------------------------------------------------
# Expired / first fetch: refresh runs, gateway assigns, TokenManager mirrors it
# ---------------------------------------------------------------------------


async def test_expired_get_refreshes_and_matches_gateway() -> None:
    """A near-expiry token triggers a refresh; gateway + TokenManager end on the SAME new token."""
    gw = _make_gateway("iot-token-initial", age=_IOT_TOKEN_EXPIRE)  # already past expiry
    tm = _make_token_manager(gw)
    backend = _AliyunBackend()

    with backend.patch():
        creds = await tm.get_aliyun_credentials()

    assert creds.iot_token == backend.latest  # the freshly minted token
    assert creds.iot_token != "iot-token-initial"  # genuinely changed
    _assert_consistent(tm, gw, expected=backend.latest)


async def test_refresh_aliyun_credentials_matches_gateway() -> None:
    """refresh_aliyun_credentials() refreshes via the gateway and stays consistent."""
    gw = _make_gateway("iot-token-initial")
    tm = _make_token_manager(gw)
    backend = _AliyunBackend()

    with backend.patch():
        await tm.refresh_aliyun_credentials()

    _assert_consistent(tm, gw, expected=backend.latest)
    assert backend.refresh_calls == 1


async def test_refresh_sets_expiry_from_gateway_issued_at() -> None:
    """The cached expiry must be derived from the gateway's issued-at + iotTokenExpire."""
    gw = _make_gateway("iot-token-initial")
    tm = _make_token_manager(gw)
    backend = _AliyunBackend()

    with backend.patch():
        await tm.refresh_aliyun_credentials()

    issued_at = gw._iot_token_issued_at  # noqa: SLF001
    assert tm._aliyun_creds.iot_token_expires_at == issued_at + _IOT_TOKEN_EXPIRE  # noqa: SLF001
    assert tm._aliyun_creds.refresh_token_expires_at == issued_at + _REFRESH_TOKEN_EXPIRE  # noqa: SLF001


async def test_token_refreshed_callback_receives_latest_token() -> None:
    """on_aliyun_token_refreshed (used to push the token to the transport) gets the new token."""
    gw = _make_gateway("iot-token-initial")
    tm = _make_token_manager(gw)
    callback = MagicMock()
    tm.on_aliyun_token_refreshed = callback
    backend = _AliyunBackend()

    with backend.patch():
        await tm.refresh_aliyun_credentials()

    callback.assert_called_once_with(backend.latest)
    # Transport (callback) and gateway agree.
    assert callback.call_args[0][0] == gw.session_by_authcode_response.data.iotToken  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# force_refresh permutations
# ---------------------------------------------------------------------------


async def test_force_refresh_aliyun_only_matches_gateway() -> None:
    """force_refresh(CLOUD_ALIYUN) refreshes the Aliyun session and stays consistent."""
    gw = _make_gateway("iot-token-initial")
    tm = _make_token_manager(gw)
    backend = _AliyunBackend()

    with backend.patch():
        await tm.force_refresh(TransportType.CLOUD_ALIYUN)

    tm.refresh_http.assert_awaited_once()  # type: ignore[attr-defined]
    _assert_consistent(tm, gw, expected=backend.latest)


async def test_force_refresh_all_matches_gateway() -> None:
    """force_refresh(None) refreshes Aliyun (no MQTT creds present) and stays consistent."""
    gw = _make_gateway("iot-token-initial")
    tm = _make_token_manager(gw)
    backend = _AliyunBackend()

    with backend.patch():
        await tm.force_refresh(None)

    _assert_consistent(tm, gw, expected=backend.latest)


async def test_force_refresh_mammotion_leaves_aliyun_token_untouched() -> None:
    """force_refresh(CLOUD_MAMMOTION) must NOT change the Aliyun token on either side."""
    gw = _make_gateway("iot-token-initial")
    tm = _make_token_manager(gw)
    tm._aliyun_creds = _fresh_creds("iot-token-initial")  # noqa: SLF001
    gw.check_or_refresh_session = AsyncMock()  # type: ignore[method-assign] — spy: must NOT fire

    await tm.force_refresh(TransportType.CLOUD_MAMMOTION)

    gw.check_or_refresh_session.assert_not_awaited()
    assert gw.session_by_authcode_response.data.iotToken == "iot-token-initial"  # type: ignore[union-attr]
    assert tm._aliyun_creds.iot_token == "iot-token-initial"  # noqa: SLF001


# ---------------------------------------------------------------------------
# Sequential refreshes: a new token each time, gateway + TM always in lockstep
# ---------------------------------------------------------------------------


async def test_sequential_refreshes_generate_new_tokens_in_lockstep() -> None:
    """Each refresh yields a distinct token; gateway and TokenManager track the latest every time."""
    gw = _make_gateway("iot-token-initial")
    tm = _make_token_manager(gw)
    backend = _AliyunBackend()

    seen: list[str] = []
    with backend.patch():
        for _ in range(4):
            await tm.refresh_aliyun_credentials()
            _assert_consistent(tm, gw, expected=backend.latest)
            seen.append(tm._aliyun_creds.iot_token)  # noqa: SLF001

    assert seen == ["iot-token-1", "iot-token-2", "iot-token-3", "iot-token-4"]
    assert len(set(seen)) == 4  # every refresh produced a genuinely new token
    assert backend.refresh_calls == 4


async def test_list_binding_sends_the_refreshed_token() -> None:
    """After a refresh, list_binding_by_account must send the gateway's new token (the 401 path)."""
    gw = _make_gateway("iot-token-initial", age=_IOT_TOKEN_EXPIRE)
    tm = _make_token_manager(gw)
    backend = _AliyunBackend()

    with backend.patch():
        await tm.refresh_aliyun_credentials()
        await gw.list_binding_by_account()

    assert backend.last_list_iot_token == backend.latest
    assert backend.last_list_iot_token == tm._aliyun_creds.iot_token  # noqa: SLF001


# ---------------------------------------------------------------------------
# SessionExpired → re-login: the NEW gateway token is used, never the stale one
# ---------------------------------------------------------------------------


async def test_session_expired_relogin_uses_new_gateway_token() -> None:
    """On 2401, _refresh_aliyun re-runs IoT login and derives the token from the NEW session.

    Regression: an early return here once handed back the stale iotToken.
    """
    gw = _make_gateway("stale-token")
    tm = _make_token_manager(gw)
    gw.check_or_refresh_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=SessionExpiredError(TransportType.CLOUD_ALIYUN, "2401 refreshToken invalid")
    )

    async def _relogin() -> None:
        # connect_iot() is now a no-arg instance method — establish a brand-new session
        # on the gateway (mirrors session_by_auth_code re-running off a fresh login).
        gw._session_by_authcode_response = _session("post-relogin-token")  # noqa: SLF001
        gw._iot_token_issued_at = int(time.time())  # noqa: SLF001

    with patch.object(TokenManager, "connect_iot", AsyncMock(side_effect=_relogin)):
        await tm.refresh_aliyun_credentials()

    _assert_consistent(tm, gw, expected="post-relogin-token")
    assert tm._aliyun_creds.iot_token != "stale-token"  # noqa: SLF001


async def test_session_expired_beyond_limit_raises_relogin_required() -> None:
    """Repeated 2401s within the window escalate to ReLoginRequiredError; creds stay unchanged."""
    gw = _make_gateway("stale-token")
    tm = _make_token_manager(gw)
    tm._aliyun_creds = _fresh_creds("stale-token")  # noqa: SLF001
    gw.check_or_refresh_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=SessionExpiredError(TransportType.CLOUD_ALIYUN, "2401")
    )

    # connect_iot (no-arg instance method) also fails to recover, so failures accumulate.
    async def _relogin_fail() -> None:
        raise SessionExpiredError(TransportType.CLOUD_ALIYUN, "2401 again")

    with patch.object(TokenManager, "connect_iot", AsyncMock(side_effect=_relogin_fail)):
        # First call: 1 failure, attempts connect_iot (which raises SessionExpiredError →
        # propagates), so wrap each call.
        with pytest.raises((ReLoginRequiredError, SessionExpiredError)):
            await tm.refresh_aliyun_credentials()
        with pytest.raises(ReLoginRequiredError):
            await tm.refresh_aliyun_credentials()

    # The cached token was never overwritten with anything stale-but-different.
    assert tm._aliyun_creds.iot_token == "stale-token"  # noqa: SLF001


# ---------------------------------------------------------------------------
# Invariant across every refresh entry point
# ---------------------------------------------------------------------------


async def test_refresh_with_none_session_data_raises_and_keeps_creds() -> None:
    """If the gateway session has no data after a 'successful' refresh, raise rather than
    assign a None token — and leave the previous cached credentials untouched."""
    gw = _make_gateway("iot-token-initial")
    tm = _make_token_manager(gw)
    tm._aliyun_creds = _fresh_creds("iot-token-initial")  # noqa: SLF001

    async def _refresh_to_empty(*_a: object, **_k: object) -> None:
        gw._session_by_authcode_response = SessionByAuthCodeResponse(code=200, data=None)  # noqa: SLF001

    gw.check_or_refresh_session = AsyncMock(side_effect=_refresh_to_empty)  # type: ignore[method-assign]

    with pytest.raises(ReLoginRequiredError):
        await tm.refresh_aliyun_credentials()

    # Previous creds were not corrupted with a None token.
    assert tm._aliyun_creds.iot_token == "iot-token-initial"  # noqa: SLF001


@pytest.mark.parametrize(
    "trigger",
    ["get", "refresh_aliyun_credentials", "force_refresh_aliyun", "force_refresh_all"],
)
async def test_token_invariant_holds_for_every_entrypoint(trigger: str) -> None:
    """Whichever way a refresh is triggered, the gateway and TokenManager end up consistent."""
    gw = _make_gateway("iot-token-initial", age=_IOT_TOKEN_EXPIRE)
    tm = _make_token_manager(gw)
    backend = _AliyunBackend()

    with backend.patch():
        if trigger == "get":
            await tm.get_aliyun_credentials()
        elif trigger == "refresh_aliyun_credentials":
            await tm.refresh_aliyun_credentials()
        elif trigger == "force_refresh_aliyun":
            await tm.force_refresh(TransportType.CLOUD_ALIYUN)
        else:
            await tm.force_refresh(None)

    _assert_consistent(tm, gw, expected=backend.latest)
