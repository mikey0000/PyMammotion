"""The Aliyun half of the cloud: the OpenAccount login and the IoT API gateway.

Served from the same aiohttp app as the Mammotion API.  The real hosts differ
(``api.link.aliyun.com``, ``sdk.openaccount.aliyun.com`` and the per-region
gateways getRegion hands out), but their paths do not collide, so the client is
pointed at one loopback base URL for all of them.  getRegion returns that base URL
with its ``http://`` scheme, which the Tea client and ``CloudIOTGateway`` keep.

Every reply mirrors the shape the pymammotion models deserialize.  IoT gateway
requests carry their params in a JSON body (``params`` / ``request.iotToken``);
the OpenAccount endpoints use a query string (connect) or a form (loginbyoauth).
"""

from __future__ import annotations

import base64
import json
import secrets
from typing import Awaitable, Callable

from aiohttp import web

from .http_api import fault_response
from .scenario import OPENID_EMPTY, Scenario


def _ok(data: object) -> web.Response:
    return web.json_response({"code": 200, "data": data, "id": "fake-req"})


def _refused(code: int, message: str) -> web.Response:
    return web.json_response({"code": code, "message": message, "id": "fake-req"})


def _openaccount(api: str, inner: dict) -> web.Response:
    envelope = {
        "traceId": "fake-trace",
        "vid": "fake-vid",
        "code": 1,
        "subCode": 0,
        "message": "",
        "successful": "true",
    }
    return web.json_response({"data": {**envelope, "data": inner}, "success": "true", "api": api, "errorMsg": ""})


def _device_listing(scenario: Scenario) -> dict:
    d = scenario.aliyun_device
    devices = [
        {
            "gmtModified": 1700000000000,
            "nodeType": "DEVICE",
            "deviceName": d.device_name,
            "productName": "Luba",
            "status": 1,
            "identityId": d.identity_id,
            "netType": "NET_WIFI",
            "categoryKey": "LawnMower",
            "productKey": d.product_key,
            "isEdgeGateway": False,
            "categoryName": "Lawn mower",
            "identityAlias": "fake",
            "iotId": d.iot_id,
            "bindTime": 1700000000000,
            "owned": 1,
            "thingType": "DEVICE",
        }
    ]
    listed = devices if scenario.aliyun_device_bound else []
    return {"total": len(listed), "data": listed, "pageNo": 1, "pageSize": 100}


def add_aliyun_routes(
    app: web.Application,
    scenario: Scenario,
    base_url_getter: Callable[[], str],
    on_invoke: Callable[[str, bytes], Awaitable[None]] | None = None,
) -> None:
    """Register the Aliyun endpoints on *app*.

    Args:
        app: the fake cloud's aiohttp app.
        scenario: shared mutable state.
        base_url_getter: this server's base URL, handed out as every regional endpoint.
        on_invoke: fired with (iot_id, protobuf_bytes) for each accepted thing/service/invoke.

    """

    async def _gateway_body(request: web.Request, counter: str) -> tuple[dict, web.Response | None]:
        scenario.count(counter)
        if (fault := scenario.faults.get(counter)) is not None:
            return {}, fault_response(request, fault)
        return await request.json(), None

    async def _iot_token_body(request: web.Request, counter: str) -> tuple[dict, web.Response | None]:
        body, refused = await _gateway_body(request, counter)
        if refused is None and not scenario.iot_token_ok(body.get("request", {}).get("iotToken")):
            refused = _refused(401, "request auth error")
        return body, refused

    async def region(request: web.Request) -> web.Response:
        body, refused = await _gateway_body(request, "aliyun_region")
        if refused is not None:
            return refused
        if body["params"]["authCode"] not in scenario.live_auth_codes:
            return web.json_response(OPENID_EMPTY)
        base = base_url_getter()
        return _ok(
            {
                "shortRegionId": "eu",
                "oaApiGatewayEndpoint": base,
                "regionId": "eu-central-1",
                "mqttEndpoint": base,
                "pushChannelEndpoint": base,
                "regionEnglishName": "Germany",
                "apiGatewayEndpoint": base,
            }
        )

    async def connect(request: web.Request) -> web.Response:
        scenario.count("aliyun_connect")
        if (fault := scenario.faults.get("aliyun_connect")) is not None:
            return fault_response(request, fault)
        status = {"traceId": "fake-trace", "code": 1, "subCode": 0, "message": "", "successful": "true"}
        return _openaccount(
            "mtop.openaccount.connect", {"device": {**status, "data": {"deviceId": "fake-oa-device"}}, "config": status}
        )

    async def login_by_oauth(request: web.Request) -> web.Response:
        scenario.count("aliyun_oauth")
        if (fault := scenario.faults.get("aliyun_oauth")) is not None:
            return fault_response(request, fault)
        form = await request.post()
        auth_code = json.loads(str(form["loginByOauthRequest"]))["authCode"]
        if auth_code not in scenario.live_auth_codes:
            return web.json_response(OPENID_EMPTY)
        scenario.live_auth_codes.discard(auth_code)
        sid = f"sid-{secrets.token_hex(8)}"
        scenario.live_sids.add(sid)
        open_account = {
            "displayName": scenario.account,
            "openId": "fake-open-id",
            "hasPassword": "false",
            "subAccount": "false",
            "pwdVersion": 0,
            "mobileConflictAccount": "false",
            "id": 1,
            "mobileLocationCode": "",
            "avatarUrl": "",
            "domainId": 1,
            "enableDevice": "true",
            "status": 0,
        }
        result = {
            "reTokenExpireIn": 2592000,
            "uidToken": "fake-uid-token",
            "openAccount": open_account,
            "initPwd": "false",
            "sidExpireIn": 3600,
            "oauthOtherInfo": {"SidExpiredTime": 3600},
            "refreshToken": "fake-oa-refresh",
            "sid": sid,
            "token": "fake-oa-token",
        }
        return _openaccount(
            "mtop.openaccount.loginbyoauth", {"loginSuccessResult": result, "mobileBindRequired": "false"}
        )

    async def aep_handle(request: web.Request) -> web.Response:
        _, refused = await _gateway_body(request, "aliyun_aep")
        if refused is not None:
            return refused
        return _ok({"deviceSecret": "fake-app-secret", "productKey": "FAKEAPPPK", "deviceName": "fakeapp"})

    async def session_by_auth_code(request: web.Request) -> web.Response:
        body, refused = await _gateway_body(request, "aliyun_session")
        if refused is not None:
            return refused
        sid = body["params"]["request"]["authCode"]
        if sid not in scenario.live_sids:
            return _refused(2064, "authCode invalid")
        scenario.live_sids.discard(sid)
        return _ok(scenario.mint_aliyun_session())

    async def check_or_refresh_session(request: web.Request) -> web.Response:
        body, refused = await _gateway_body(request, "aliyun_check_session")
        if refused is not None:
            return refused
        refresh_token = body["params"]["request"]["refreshToken"]
        if refresh_token not in scenario.valid_aliyun_refresh_tokens:
            return _refused(2401, "refreshToken invalid")
        return _ok(scenario.mint_aliyun_session(refresh_token))

    async def list_binding_by_account(request: web.Request) -> web.Response:
        _, refused = await _iot_token_body(request, "aliyun_list_binding")
        return refused or _ok(_device_listing(scenario))

    async def share_notice_list(request: web.Request) -> web.Response:
        _, refused = await _iot_token_body(request, "aliyun_share_notices")
        if refused is not None:
            return refused
        d = scenario.aliyun_device
        pending = {
            "gmtModified": 1700000000000,
            "targetId": d.iot_id,
            "targetType": "DEVICE",
            "gmtCreate": 1700000000000,
            "batchId": "fake-batch",
            "nodeType": "DEVICE",
            "deviceName": d.device_name,
            "productName": "Luba",
            "recordId": "fake-share-record",
            "initiatorIdentityId": "fake-initiator",
            "isReceiver": 1,
            "initiatorAlias": "owner@example.com",
            "status": -1,
        }
        records = [pending] if scenario.aliyun_pending_share else []
        return _ok({"total": len(records), "data": records, "pageNo": 1, "pageSize": 100})

    async def confirm_share(request: web.Request) -> web.Response:
        body, refused = await _iot_token_body(request, "aliyun_confirm_share")
        if refused is not None:
            return refused
        scenario.confirmed_shares.append(body["params"]["recordIdList"])
        return _ok({})

    async def invalid_session(request: web.Request) -> web.Response:
        _, refused = await _gateway_body(request, "aliyun_sign_out")
        return refused or _ok({})

    async def invoke(request: web.Request) -> web.Response:
        body, refused = await _gateway_body(request, "aliyun_invokes")
        if refused is not None:
            return refused
        if not scenario.iot_token_ok(body.get("request", {}).get("iotToken")):
            return _refused(460, "iotToken expired")
        params = body["params"]
        if on_invoke is not None:
            await on_invoke(params["iotId"], base64.b64decode(params["args"]["content"]))
        return _ok({})

    app.router.add_post("/living/account/region/get", region)
    app.router.add_post("/api/prd/connect.json", connect)
    app.router.add_post("/api/prd/loginbyoauth.json", login_by_oauth)
    app.router.add_post("/app/aepauth/handle", aep_handle)
    app.router.add_post("/account/createSessionByAuthCode", session_by_auth_code)
    app.router.add_post("/account/checkOrRefreshSession", check_or_refresh_session)
    app.router.add_post("/uc/listBindingByAccount", list_binding_by_account)
    app.router.add_post("/uc/getShareNoticeList", share_notice_list)
    app.router.add_post("/uc/confirmShare", confirm_share)
    app.router.add_post("/iotx/account/invalidSession", invalid_session)
    app.router.add_post("/thing/service/invoke", invoke)
