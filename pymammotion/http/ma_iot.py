"""Client for Mammotion's MA-IoT proxy API (``api-iot-business-*.mammotion.com``).

Why this exists
---------------
Prior to app version 2.2.4.x the Mammotion client talked to the Aliyun IoT
gateway directly (via the `pymammotion.aliyun.cloud_gateway.CloudIOTGateway`
path in this library).  That flow drives the ``eu-central-1.api-iot.aliyuncs.com``
endpoints for auth-code → session → IoT commands, and the Aliyun IoT MQTT
broker for device state.  Those endpoints have strict per-account rate
limits — hitting them from a long-running HA integration routinely surfaces
``TooManyRequestsException`` errors and burns the session (``code=2401
refreshToken invalid!!``).

The current app has migrated to Mammotion's own HTTPS proxy at
``api-iot-business-<region>-dcdn.mammotion.com``:

* ``POST /v1/ma-user/region`` → regional base URL (also encoded in the
  access-token's ``iot`` JWT claim, so callers can usually skip this hop).
* ``POST /v1/user/device/page`` → list bound devices.
* ``POST /v1/mqtt/auth/jwt`` → MQTT broker host + JWT credentials.
* ``POST /v1/mqtt/rpc/thing/properties/get`` → read device state.
* ``POST /v1/mqtt/rpc/thing/properties/set`` → write device state.
* ``POST /v1/mqtt/rpc/thing/service/invoke`` → run a device action
  (protobuf command payload in ``args.content``).

All endpoints authenticate with a single ``Authorization: Bearer <access_token>``
header — the same token minted by :py:meth:`MammotionHTTP.login_v2`.  There is
no per-request HMAC signing on this proxy; the Ma-Iot-* headers described in
the decompiled ``MaIoTApiService.java`` only apply to the deprecated
region-lookup/login endpoints.

This client is deliberately transport-only: it knows nothing about the
coordinator, retry policy, or the Aliyun transport, so it can be wired in
alongside the existing code path without disrupting it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientSession

from pymammotion.const import APP_VERSION, MA_IOT_REGION_DOMAIN
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import Response
from pymammotion.http.model.ma_iot import (
    MaIotDeviceList,
    MaIotDeviceListRequest,
    MaIotGetPropertiesRequest,
    MaIotJwtRequest,
    MaIotJwtResponse,
    MaIotProperty,
    MaIotServiceInvokeRequest,
    MaIotServiceInvokeResponse,
    MaIotSetPropertiesRequest,
    MaRegionData,
    MaRegionRequest,
)
from pymammotion.http.model.response_factory import response_factory

_LOGGER = logging.getLogger(__name__)


@dataclass
class MaIotEndpoints:
    """Resolved paths for the MA-IoT proxy endpoints (all POST)."""

    device_page = "/v1/user/device/page"
    mqtt_jwt = "/v1/mqtt/auth/jwt"
    properties_get = "/v1/mqtt/rpc/thing/properties/get"
    properties_set = "/v1/mqtt/rpc/thing/properties/set"
    service_invoke = "/v1/mqtt/rpc/thing/service/invoke"
    region_lookup = "/v1/ma-user/region"


class MaIotError(Exception):
    """Raised when the MA-IoT proxy returns a non-zero application code."""

    def __init__(self, code: int, msg: str, endpoint: str) -> None:
        super().__init__(f"{endpoint} failed: code={code} msg={msg}")
        self.code = code
        self.msg = msg
        self.endpoint = endpoint


class MammotionMaIoT:
    """Thin async client for the MA-IoT proxy.

    Must be constructed with an already-authenticated :class:`MammotionHTTP`
    instance — this class reuses its bearer token and (optionally) its
    aiohttp session.  Calls are stateless beyond the cached ``base_url``.
    """

    def __init__(
        self,
        mammotion_http: MammotionHTTP,
        base_url: str | None = None,
        session: ClientSession | None = None,
    ) -> None:
        self._http = mammotion_http
        self._session = session
        self._base_url = base_url.rstrip("/") if base_url else None
        self._common_headers = {
            "User-Agent": "okhttp/4.9.3",
            "App-Version": APP_VERSION,
            "Accept-Language": "EN-US",
        }

    @asynccontextmanager
    async def _client_session(self) -> AsyncIterator[ClientSession]:
        """Yield an aiohttp session, creating a disposable one if none given."""
        if self._session is not None:
            yield self._session
        else:
            async with ClientSession() as session:
                yield session

    def _auth_headers(self) -> dict[str, str]:
        """Return a fresh Authorization header from the current access token."""
        if self._http.login_info is None:
            raise RuntimeError("MammotionHTTP is not logged in — call login_v2 first")
        return {**self._common_headers, "Authorization": f"Bearer {self._http.login_info.access_token}"}

    @property
    def base_url(self) -> str | None:
        """Return the cached regional base URL, if known."""
        return self._base_url

    async def resolve_base_url(self) -> str:
        """Resolve (and cache) the per-region MA-IoT base URL.

        Prefers the ``iot`` claim embedded in the access token (the app uses
        that fast path too — see ``RetrofitUtil.getRegionRetrofit``) and falls
        back to the public ``/v1/ma-user/region`` lookup if missing.
        """
        if self._base_url:
            return self._base_url

        iot_claim = self._http.jwt_info.iot if self._http.jwt_info else ""
        if iot_claim:
            self._base_url = _normalise_base_url(iot_claim)
            _LOGGER.debug("MA-IoT base URL from JWT iot claim: %s", self._base_url)
            return self._base_url

        if self._http.login_info is None:
            raise RuntimeError("Cannot resolve MA-IoT region: not logged in")

        request = MaRegionRequest(access_token=self._http.login_info.access_token)
        data = await self._post(
            MA_IOT_REGION_DOMAIN,
            MaIotEndpoints.region_lookup,
            request.to_dict(),
            MaRegionData,
            authenticated=True,
        )
        self._base_url = _normalise_base_url(data.region_endpoint)
        _LOGGER.debug("MA-IoT base URL from /v1/ma-user/region: %s", self._base_url)
        return self._base_url

    async def list_devices(
        self, page_number: int = 1, page_size: int = 100, owned: int | None = None
    ) -> MaIotDeviceList:
        """List the authenticated user's bound devices."""
        base = await self.resolve_base_url()
        request = MaIotDeviceListRequest(page_number=page_number, page_size=page_size, owned=owned)
        return await self._post(base, MaIotEndpoints.device_page, request.to_dict(), MaIotDeviceList)

    async def get_mqtt_credentials(self, client_id: str, username: str) -> MaIotJwtResponse:
        """Fetch MQTT broker host + JWT credentials for the given client identity."""
        base = await self.resolve_base_url()
        request = MaIotJwtRequest(client_id=client_id, username=username)
        return await self._post(base, MaIotEndpoints.mqtt_jwt, request.to_dict(), MaIotJwtResponse)

    async def get_properties(self, iot_id: str, product_key: str, device_name: str) -> list[MaIotProperty]:
        """Read the current property set for a specific device.

        Returns a list of ``MaIotProperty`` entries (the app deserialises the
        proxy's body to ``List<GetPropertiesResponse>``; each entry is an
        opaque ``identifier`` / ``value`` pair).
        """
        base = await self.resolve_base_url()
        request = MaIotGetPropertiesRequest(iot_id=iot_id, product_key=product_key, device_name=device_name)
        return await self._post_list(base, MaIotEndpoints.properties_get, request.to_dict(), MaIotProperty)

    async def set_properties(
        self,
        iot_id: str,
        product_key: str,
        device_name: str,
        items: dict[str, Any],
    ) -> None:
        """Write a batch of properties to a device (no payload on success)."""
        base = await self.resolve_base_url()
        request = MaIotSetPropertiesRequest(
            iot_id=iot_id, product_key=product_key, device_name=device_name, items=items
        )
        await self._post(base, MaIotEndpoints.properties_set, request.to_dict(), dict)

    async def service_invoke(
        self,
        iot_id: str,
        product_key: str,
        device_name: str,
        identifier: str,
        args: dict[str, Any] | None = None,
    ) -> MaIotServiceInvokeResponse:
        """Invoke a device service (a protobuf command, for Mammotion mowers).

        ``args`` is a free-form JSON map in the app; typical Mammotion usage
        packs a base64-encoded protobuf into ``{"content": "<base64>"}``.
        """
        base = await self.resolve_base_url()
        request = MaIotServiceInvokeRequest(
            iot_id=iot_id,
            product_key=product_key,
            device_name=device_name,
            identifier=identifier,
            args=args or {},
        )
        return await self._post(
            base, MaIotEndpoints.service_invoke, request.to_dict(), MaIotServiceInvokeResponse
        )

    async def _post(
        self,
        base_url: str,
        path: str,
        body: dict[str, Any],
        model: type,
        authenticated: bool = True,
    ) -> Any:
        """POST JSON to ``<base_url><path>`` and return parsed ``model`` from ``data``."""
        url = f"{base_url.rstrip('/')}{path}"
        headers = self._auth_headers() if authenticated else self._common_headers
        async with self._client_session() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                raw = await resp.text()
                if resp.status != 200:
                    _LOGGER.debug("MA-IoT %s failed (status=%s): %s", path, resp.status, raw[:500])
                    raise MaIotError(resp.status, raw[:500], path)
                payload = await resp.json(content_type=None)

        code = payload.get("code")
        if code != 0:
            raise MaIotError(code, payload.get("msg", ""), path)

        data = payload.get("data")
        if model is dict:
            return data if isinstance(data, dict) else {}
        if data is None:
            raise MaIotError(code or -1, "empty data field", path)
        # Use mashumaro deserialiser when available (DataClassORJSONMixin), else raw dict
        if hasattr(model, "from_dict"):
            return model.from_dict(data)
        return data

    async def _post_list(
        self, base_url: str, path: str, body: dict[str, Any], item_model: type
    ) -> list[Any]:
        """POST JSON to ``<base_url><path>`` and deserialise ``data`` as a list."""
        url = f"{base_url.rstrip('/')}{path}"
        headers = self._auth_headers()
        async with self._client_session() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                if resp.status != 200:
                    raise MaIotError(resp.status, await resp.text(), path)
                payload = await resp.json(content_type=None)

        code = payload.get("code")
        if code != 0:
            raise MaIotError(code, payload.get("msg", ""), path)

        items = payload.get("data") or []
        if not isinstance(items, list):
            raise MaIotError(code or -1, "expected list under data", path)
        if hasattr(item_model, "from_dict"):
            return [item_model.from_dict(item) for item in items]
        return items


def _normalise_base_url(url: str) -> str:
    """Ensure the MA-IoT base URL has an ``https://`` scheme and no trailing slash."""
    if not url:
        raise ValueError("empty MA-IoT base URL")
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc or parsed.path
    return f"{parsed.scheme or 'https'}://{host}".rstrip("/")
