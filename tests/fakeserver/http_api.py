"""aiohttp app emulating the Mammotion HTTP API, plus a /control API.

Response shapes follow the wire-contract the pymammotion models deserialize
(see the spec notes in tests/fakeserver/__init__.py's docstring).  Every JSON
body carries both ``code`` and ``msg`` (the Response envelope requires both),
and success is signalled by in-body ``code == 0``.
"""

from __future__ import annotations

import base64
from dataclasses import fields as dataclass_fields
import time
from typing import Awaitable, Callable

from aiohttp import web

from pymammotion.http.model.http import ErrorInfo

from .scenario import BAD_CREDENTIALS_MSG, Scenario


def _json(payload: dict, status: int = 200) -> web.Response:
    return web.json_response(payload, status=status)


def _ok(data: object | None = None, **extra: object) -> web.Response:
    body: dict = {"code": 0, "msg": "success", "requestId": "fake-req"}
    if data is not None:
        body["data"] = data
    body.update(extra)
    return _json(body)


def _error_codes_csv() -> str:
    """One CSV row whose header matches ErrorInfo's fields exactly."""
    names = [f.name for f in dataclass_fields(ErrorInfo)]
    row = {name: "" for name in names}
    row.update(code="1002", platform="LUBA", module="NAV", variant="A", level="2", description="fake error")
    for name in names:
        if name.endswith("_implication"):
            row[name] = "Fake implication"
        elif name.endswith("_solution"):
            row[name] = "Fake solution"
    header = ",".join(names)
    values = ",".join(row[name] for name in names)
    return f"{header}\n{values}"


def build_app(
    scenario: Scenario,
    base_url_getter: Callable[[], str],
    mqtt_host_getter: Callable[[], str],
    on_invoke: Callable[[str, bytes], Awaitable[None]] | None = None,
) -> web.Application:
    """Build the fake API app.

    Args:
        scenario: shared mutable state.
        base_url_getter: returns this server's own base URL (for the JWT ``iot`` claim).
        mqtt_host_getter: returns the MQTT credential host string, e.g. ``tcp://127.0.0.1:1883``.
        on_invoke: fired with (iot_id, protobuf_bytes) for each successful mqtt_invoke,
            so the fake mower can answer over the broker.

    """
    app = web.Application()

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    async def oauth2_token(request: web.Request) -> web.Response:
        grant = request.query.get("grant_type", "")
        if scenario.oauth_http_status is not None:
            scenario.count(f"oauth_{scenario.oauth_http_status}")
            return _json({"code": scenario.oauth_http_status, "msg": "server unavailable"},
                         status=scenario.oauth_http_status)
        if grant == "password":
            scenario.count("password_grants")
            if scenario.login_reject is not None:
                code, msg = scenario.login_reject
                return _json({"code": code, "msg": msg})
            username = request.query.get("username", "")
            password_b64 = request.query.get("password", "")
            try:
                password = base64.b64decode(password_b64).decode()
            except Exception:  # noqa: BLE001
                password = ""
            if username != scenario.account or password != scenario.password:
                return _json({"code": 40001, "msg": BAD_CREDENTIALS_MSG})
            return _ok(scenario.mint_login_data(base_url_getter()))
        if grant == "refresh_token":
            scenario.count("refresh_grants")
            supplied = request.query.get("refresh_token", "")
            if scenario.refresh_rejected or supplied != scenario.current_refresh_token:
                return _json({"code": 40102, "msg": "Refresh token has expired"})
            return _ok(scenario.mint_login_data(base_url_getter()))
        return _json({"code": 40002, "msg": f"unsupported grant_type {grant!r}"})

    async def oauth_token_legacy(request: web.Request) -> web.Response:
        # Params are AES-encrypted with a key the fake cannot know; accept or
        # reject purely on scenario state.
        scenario.count("legacy_logins")
        if scenario.login_reject is not None:
            code, msg = scenario.login_reject
            return _json({"code": code, "msg": msg})
        return _ok(scenario.mint_login_data(base_url_getter()))

    async def authorization_code(request: web.Request) -> web.Response:
        scenario.count("auth_code_fetches")
        if not scenario.bearer_ok(request.headers.get("Authorization")):
            return _json({"code": 401, "msg": "unauthorized"})
        return _ok({"code": f"authcode-{int(time.time() * 1000)}"})

    # ------------------------------------------------------------------
    # Device / account endpoints (MAMMOTION_API_DOMAIN)
    # ------------------------------------------------------------------

    async def device_list(request: web.Request) -> web.Response:
        scenario.count("device_list_calls")
        if not scenario.bearer_ok(request.headers.get("Authorization")):
            return _json({"code": 401, "msg": "unauthorized"}, status=401)
        d = scenario.device
        return _ok([
            {
                "iotId": d.iot_id,
                "deviceId": "dev-1",
                "deviceName": d.device_name,
                "deviceType": "LUBA",
                "generation": 2,
                "status": 1,
                "isSubscribe": 0,
                "activeTime": "2026-06-03T14:48:26",
                "activeTimestamp": 1780498106000,
            }
        ])

    async def share_device_page(request: web.Request) -> web.Response:
        scenario.count("share_page_calls")
        if not scenario.bearer_ok(request.headers.get("Authorization")):
            return _json({"code": 401, "msg": "unauthorized"}, status=401)
        # data deliberately absent: a non-None value (even an empty ShareRecords)
        # drags MammotionClient into the Aliyun connect_iot chain.
        return _json({"code": 0, "msg": "success"})

    async def confirm_share(_request: web.Request) -> web.Response:
        return _ok(True)

    async def logout(_request: web.Request) -> web.Response:
        scenario.count("logouts")
        return _json({"code": 0, "msg": "success"})

    async def error_codes(request: web.Request) -> web.Response:
        if not scenario.bearer_ok(request.headers.get("Authorization")):
            return _json({"code": 401, "msg": "unauthorized"}, status=401)
        return _ok(_error_codes_csv())

    async def ota_check(_request: web.Request) -> web.Response:
        return _ok([])

    async def ota_upgrade(_request: web.Request) -> web.Response:
        return _ok("fake-ota-task-1")

    async def rtk_devices(_request: web.Request) -> web.Response:
        return _ok([])

    async def stream_token(_request: web.Request) -> web.Response:
        return _ok(
            {
                "appid": "fake-agora-app",
                "openEncrypt": 0,
                "cameras": [{"cameraId": 0, "token": "fake-cam-token"}],
                "channelName": "fake-channel",
                "areaCode": "EU",
                "token": "fake-agora-token",
                "uid": 12345,
            }
        )

    async def video_resource(request: web.Request) -> web.Response:
        return _ok(
            {
                "id": "vr-1",
                "deviceId": request.match_info.get("iot_id", ""),
                "deviceName": scenario.device.device_name,
                "cycleType": 0,
                "usageYearMonth": "2026-08",
                "totalTime": 3600,
                "availableTime": 1800,
            }
        )

    async def generic_ok(_request: web.Request) -> web.Response:
        return _json({"code": 0, "msg": "success"})

    # ------------------------------------------------------------------
    # {jwt.iot}-based endpoints (same host here)
    # ------------------------------------------------------------------

    async def user_device_page(request: web.Request) -> web.Response:
        scenario.count("device_page_calls")
        if not scenario.bearer_ok(request.headers.get("Authorization")):
            return _json({"code": 401, "msg": "unauthorized"}, status=401)
        d = scenario.device
        return _ok(
            {
                "records": [
                    {
                        "identityId": d.identity_id,
                        "iotId": d.iot_id,
                        "productKey": d.product_key,
                        "deviceName": d.device_name,
                        "owned": 1,
                        "bindTime": 1780498106000,
                        "createTime": "2026-06-03T14:48:26",
                        "status": 1,
                    }
                ],
                "total": 1,
                "size": 100,
                "current": 1,
                "pages": 1,
            }
        )

    async def mqtt_auth_jwt(request: web.Request) -> web.Response:
        scenario.count("mqtt_jwt_fetches")
        if not scenario.bearer_ok(request.headers.get("Authorization")):
            return _json({"code": 401, "msg": "unauthorized"}, status=401)
        if scenario.mqtt_jwt_returns_no_data:
            # 200 with no payload: the login is fine, this one transport is not.
            return _json({"code": 0, "msg": "success"})
        return _ok(
            {
                "host": mqtt_host_getter(),
                "jwt": scenario.mint_broker_jwt(),
                "clientId": "fake-mqtt-client-1",
                "username": scenario.device.identity_id,
            }
        )

    async def mqtt_invoke(request: web.Request) -> web.Response:
        scenario.count("invoke_calls")
        if not scenario.bearer_ok(request.headers.get("Authorization")):
            scenario.count("invoke_401s")
            return _json({"code": 401, "msg": "token expired"})
        mode = scenario.invoke_mode
        if mode == "http_401":
            return _json({"code": 401, "msg": "token expired"}, status=401)
        if mode == "body_401":
            return _json({"code": 401, "msg": "token expired"})
        if mode == "body_460":
            return _json({"code": 460, "msg": "access token expired"})
        if mode == "offline":
            return _json({"code": 50104, "msg": "device offline"})
        if mode == "gateway_timeout":
            return _json({"code": 20056, "msg": "device did not answer"})
        if mode == "error":
            return _json({"code": 9999, "msg": "internal error"})
        body = await request.json()
        if on_invoke is not None:
            try:
                content = base64.b64decode(body.get("args", {}).get("content", ""))
            except Exception:  # noqa: BLE001
                content = b""
            await on_invoke(body.get("iotId", ""), content)
        return _ok({})

    # ------------------------------------------------------------------
    # /control — runtime fault injection (for tests and for driving HA by hand)
    # ------------------------------------------------------------------

    async def control_state(_request: web.Request) -> web.Response:
        return _json(
            {
                "code": 0,
                "msg": "success",
                "counters": scenario.counters,
                "login_reject": scenario.login_reject,
                "refresh_rejected": scenario.refresh_rejected,
                "oauth_http_status": scenario.oauth_http_status,
                "invoke_mode": scenario.invoke_mode,
                "mammotion_connack_rc": scenario.mammotion_connack_rc,
                "aliyun_connack_rc": scenario.aliyun_connack_rc,
                "bind_reply_code": scenario.bind_reply_code,
                "live_access_tokens": len(scenario.valid_access_tokens),
                "account": scenario.account,
            }
        )

    async def control_action(request: web.Request) -> web.Response:
        action = request.match_info["action"]
        params = await request.json() if request.can_read_body else {}
        handlers = {
            "reset": scenario.reset,
            "revoke-refresh-token": scenario.revoke_refresh_token,
            "revoke-access-tokens": scenario.revoke_access_tokens,
            "deactivate-account": scenario.deactivate_account,
            "expire-session": scenario.expire_session,
        }
        if action in handlers:
            handlers[action]()
        elif action == "set-invoke-mode":
            scenario.invoke_mode = params["mode"]
        elif action == "set-connack-rc":
            scenario.mammotion_connack_rc = int(params["rc"])
        elif action == "set-aliyun-connack-rc":
            scenario.aliyun_connack_rc = int(params["rc"])
        elif action == "set-bind-reply":
            scenario.bind_reply_code = int(params["code"])
        elif action == "set-oauth-status":
            scenario.oauth_http_status = params.get("status")
        elif action == "set-login-reject":
            scenario.login_reject = (int(params["code"]), params["msg"]) if params else None
        elif action == "restore-login":
            scenario.login_reject = None
            scenario.refresh_rejected = False
        else:
            return _json({"code": 404, "msg": f"unknown control action {action!r}"}, status=404)
        return _json({"code": 0, "msg": f"applied {action}"})

    app.router.add_post("/oauth2/token", oauth2_token)
    app.router.add_post("/oauth/token", oauth_token_legacy)
    app.router.add_post("/authorization/code", authorization_code)
    app.router.add_get("/device-server/v1/device/list", device_list)
    app.router.add_post("/user-server/v1/share/device/page", share_device_page)
    app.router.add_post("/user-server/v1/share/device/confirm", confirm_share)
    app.router.add_post("/user-server/v3/user/logout", logout)
    app.router.add_post("/user-server/v1/code/record/export-data", error_codes)
    app.router.add_post("/device-server/v1/devices/version/check", ota_check)
    app.router.add_post("/device-server/v1/ota/device/upgrade", ota_upgrade)
    app.router.add_get("/device-server/v1/rtk/devices", rtk_devices)
    app.router.add_post("/device-server/v1/stream/token", stream_token)
    app.router.add_get("/device-server/v1/video-resource/{iot_id}", video_resource)
    app.router.add_post("/device-server/v1/iot/device/pairing", generic_ok)
    app.router.add_post("/device-server/v1/iot/device/unpairing", generic_ok)
    app.router.add_post("/device-server/v1/iot/net-rtk/enable", generic_ok)
    app.router.add_post("/v1/user/device/page", user_device_page)
    app.router.add_post("/v1/mqtt/auth/jwt", mqtt_auth_jwt)
    app.router.add_post("/v1/mqtt/rpc/thing/service/invoke", mqtt_invoke)
    app.router.add_get("/control/state", control_state)
    app.router.add_post("/control/{action}", control_action)
    return app
