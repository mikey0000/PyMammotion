from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import csv
from functools import wraps
import hashlib
import hmac
import json
import logging
import random
import time
from typing import TYPE_CHECKING, Any, TypeVar, cast

from aiohttp import ClientError, ClientSession, ClientTimeout
import jwt

from pymammotion.const import (
    APP_VERSION,
    MAMMOTION_API_DOMAIN,
    MAMMOTION_CLIENT_ID,
    MAMMOTION_CLIENT_SECRET,
    MAMMOTION_DOMAIN,
    MAMMOTION_OAUTH2_CLIENT_ID,
    MAMMOTION_OAUTH2_CLIENT_SECRET,
)
from pymammotion.http.encryption import EncryptionUtils
from pymammotion.http.model.camera_stream import StreamSubscriptionResponse, VideoResourceResponse
from pymammotion.http.model.http import (
    CheckDeviceVersion,
    DeviceInfo,
    DeviceRecords,
    ErrorInfo,
    JWTTokenInfo,
    LoginResponseData,
    MQTTConnection,
    Response,
    ShareRecords,
    UnauthorizedExceptionError,
)
from pymammotion.http.model.response_factory import response_factory
from pymammotion.http.model.rtk import RTK
from pymammotion.transport.base import AuthError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

T = TypeVar("T")

_LOGGER = logging.getLogger(__name__)


def _token_fingerprint(token: str | None) -> str:
    """Return a non-sensitive fingerprint of a JWT for correlating refreshes in logs.

    Emits ``<jti-or-hash>@exp=<unix>`` so successive refreshes that rotate the
    access token are visible (a new fingerprint each line) and a stale token being
    reused is visible (the same fingerprint reappearing after a "refreshed" log).
    Never logs the token itself.
    """
    if not token:
        return "none"
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
        ident = claims.get("jti") or hashlib.sha1(token.encode(), usedforsecurity=False).hexdigest()[:8]
        return f"{ident}@exp={claims.get('exp', '?')}"
    except Exception:  # noqa: BLE001 — a malformed token must never break logging
        return f"sha1:{hashlib.sha1((token or '').encode(), usedforsecurity=False).hexdigest()[:8]}"


def sign_with_hmac_sha256(data: str, app_secret: str) -> str:
    """Sign data with HMAC-SHA256 algorithm.

    Args:
        data: The data to sign
        app_secret: The secret key for signing

    Returns:
        Hex string of the signature

    Raises:
        RuntimeError: If signing fails

    """
    if data is None:
        raise ValueError("data cannot be None")
    if app_secret is None:
        raise ValueError("app_secret cannot be None")

    try:
        # Convert strings to bytes using UTF-8 encoding
        data_bytes = data.encode("utf-8")
        secret_bytes = app_secret.encode("utf-8")

        # Create HMAC-SHA256 hash
        hmac_obj = hmac.new(secret_bytes, data_bytes, hashlib.sha256)

        # Get the digest
        digest = hmac_obj.digest()

        # Convert to hex string
        hex_string = digest.hex()

        return hex_string

    except Exception as e:
        raise RuntimeError(f"toSignWithHmacSha256 error: {e}") from e


def create_oauth_signature(
    login_req: dict, client_id: str, client_secret: str, token_endpoint: str, timestamp: int
) -> str:
    """Create OAuth signature for login request.

    Args:
        login_req: Login request data as dictionary
        client_id: OAuth client ID
        client_secret: OAuth client secret
        token_endpoint: Token endpoint path

    Returns:
        HMAC-SHA256 signature
        :param timestamp:

    """
    # Convert dict to JSON without HTML escaping (ensure_ascii=False handles this)
    json_data = json.dumps(login_req, ensure_ascii=False, separators=(",", ":"))

    # Construct the string to sign
    str_to_sign = f"{client_id}{timestamp}{token_endpoint}{json_data}"

    # Create MD5 hash of client secret
    try:
        md5_hash = hashlib.md5(client_secret.encode("utf-8")).digest()
        # Convert to hex string
        hashed_secret = md5_hash.hex()
    except Exception:
        hashed_secret = ""

    # Sign with HMAC-SHA256
    return sign_with_hmac_sha256(str_to_sign, hashed_secret)


class MammotionHTTP:
    """HTTP client for the Mammotion cloud API (login, device list, MQTT credentials, OTA)."""

    def __init__(
        self,
        account: str | None = None,
        password: str | None = None,
        session: ClientSession | None = None,
        ha_version: str | None = None,
    ) -> None:
        self.device_info: list[DeviceInfo] = []
        self.mqtt_credentials: MQTTConnection | None = None
        self.device_records: DeviceRecords = DeviceRecords(records=[], current=0, total=0, size=0, pages=0)
        self.expires_in = 0.0
        self.code = 0
        self.msg = None
        self._session: ClientSession | None = session  # None → new session per request
        self.account = account
        self._password = password
        self._response: Response | None = None
        self._login_info: LoginResponseData | None = None
        self.devices_shared_info = ShareRecords()
        self.jwt_info: JWTTokenInfo = JWTTokenInfo("", "")
        app_version = f"HA,2.{ha_version}" if ha_version else f"NOT HA,{APP_VERSION}"
        # app_version = f"ALIYUN DEMO,{APP_VERSION}"  # f"HA,{ha_version}"
        self._headers = {"User-Agent": "okhttp/4.9.3", "App-Version": app_version}
        self.encryption_utils = EncryptionUtils()

        # Add this method to generate a 10-digit random number
        def get_10_random() -> str:
            """Generate a 10-digit random number as a string."""
            return "".join([str(random.randint(0, 9)) for _ in range(7)])

        # Replace the line in the __init__ method with:
        self.client_id = f"{int(time.time() * 1000)}_{get_10_random()}_1"

    #: Default total timeout for internally-created ClientSessions.  Bounds how
    #: long any HTTP round-trip (login, refresh, MQTT credentials, …) can take,
    #: which in turn bounds how long ``TokenManager._lock`` is held by an
    #: in-flight refresh.  Without this, aiohttp's 5-min default would let a
    #: slow Mammotion server stall every other coroutine waiting on a token.
    _DEFAULT_HTTP_TIMEOUT: ClientTimeout = ClientTimeout(total=30)

    @asynccontextmanager
    async def _client_session(self) -> AsyncIterator[ClientSession]:
        """Yield the externally-provided session, or a fresh one that is closed after use."""
        if self._session is not None:
            yield self._session
        else:
            async with ClientSession(timeout=self._DEFAULT_HTTP_TIMEOUT) as session:
                yield session

    @property
    def login_info(self) -> LoginResponseData | None:
        """Return login info, or None if not yet logged in."""
        return self._login_info

    @login_info.setter
    def login_info(self, value: LoginResponseData | None) -> None:
        self._login_info = value

    @property
    def _require_login_info(self) -> LoginResponseData:
        """Return login_info, raising AuthError if not logged in."""
        if self._login_info is None:
            raise AuthError("Not logged in — login_info is None")
        return self._login_info

    @property
    def response(self) -> Response | None:
        """Return the most recent login response."""
        return self._response

    @response.setter
    def response(self, response: Response) -> None:
        self._response = response
        decoded_token = jwt.decode(response.data.access_token, options={"verify_signature": False})  # type: ignore
        if isinstance(decoded_token, dict):
            self.jwt_info = JWTTokenInfo(iot=decoded_token.get("iot", ""), robot=decoded_token.get("robot", ""))
            # Initialise expires_in from the JWT exp claim so the refresh_token_decorator
            # does not fire on every request after a cache restore (exp is an absolute
            # Unix timestamp, matching the semantics of self.expires_in).
            self.expires_in = float(decoded_token.get("exp", 0))

    @staticmethod
    def generate_headers(token: str) -> dict:
        """Generate Authorization headers for the given bearer token."""
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def retry_on_network_error(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        """Retry a method up to 3 times on transient network errors.

        Catches aiohttp.ClientError and asyncio.TimeoutError between attempts.
        Auth failures and application errors are never retried.
        """
        _MAX_ATTEMPTS = 3
        _RETRY_DELAYS = (1.0, 2.0)

        @wraps(func)
        async def wrapper(self: MammotionHTTP, *args: Any, **kwargs: Any) -> T:
            last_exc: Exception = RuntimeError("no attempts made")
            for attempt in range(_MAX_ATTEMPTS):
                if attempt > 0:
                    await asyncio.sleep(_RETRY_DELAYS[attempt - 1])
                try:
                    return await func(self, *args, **kwargs)
                except (TimeoutError, ClientError) as exc:
                    last_exc = exc
                    _LOGGER.debug("Network error on attempt %d/%d: %s", attempt + 1, _MAX_ATTEMPTS, exc)
            raise last_exc

        return wrapper

    @staticmethod
    def refresh_token_decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        """Decorator to handle token refresh before executing a function.

        Args:
            func: The async function to be decorated

        Returns:
            The wrapped async function that handles token refresh

        """

        @wraps(func)
        async def wrapper(self: MammotionHTTP, *args: Any, **kwargs: Any) -> T:
            # Check if token will expire in the next 5 minutes
            if self.expires_in < time.time() + 300:  # 300 seconds = 5 minutes
                # NOTE: this refresh is NOT serialised — N concurrent decorated calls
                # (e.g. one per device sharing this MammotionHTTP) can all enter here
                # at once and each fire refresh_login(), rotating the server-side
                # refresh token and invalidating each other.  The log below makes that
                # stampede visible: multiple "decorator refresh" lines for the same
                # account within milliseconds == the race.
                _LOGGER.debug(
                    "refresh_token_decorator[%s]: token near expiry (expires_in=%s, now=%.0f, fp=%s) — refreshing",
                    getattr(func, "__name__", "?"),
                    self.expires_in,
                    time.time(),
                    _token_fingerprint(self._login_info.access_token if self._login_info else None),
                )
                await self.refresh_login()
            return await func(self, *args, **kwargs)

        return wrapper

    async def handle_expiry(self, resp: Response) -> Response:
        """Re-login and return a fresh response if the given response indicates an expired token (401)."""
        if resp.code == 401 and self.account and self._password:
            return await self.login_v2(self.account, self._password)
        return resp

    async def login_by_email(self, email: str, password: str) -> Response[LoginResponseData]:
        """Log in using email and password via the v2 OAuth endpoint."""
        return await self.login_v2(email, password)

    @refresh_token_decorator
    async def get_all_error_codes(self) -> dict[str, ErrorInfo]:
        """Retrieves and parses all error codes from the MAMMOTION API."""
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_API_DOMAIN}/user-server/v1/code/record/export-data",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                },
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                reader = csv.DictReader(data.get("data", "").split("\n"), delimiter=",")
                codes = dict()
                for row in reader:
                    error_info = ErrorInfo(**cast(dict[str, Any], row))
                    codes[error_info.code] = error_info
                return codes

        return {}

    async def oauth_check(self) -> Response:
        """Check if token is valid.

        Returns 401 if token is invalid. We then need to re-authenticate, can try to refresh token first
        """
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_DOMAIN}/user-server/v1/user/oauth/check",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                },
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                return Response.from_dict(data)

        return Response(code=200, msg="success")

    @refresh_token_decorator
    async def refresh_authorization_token(self) -> Response:
        """Proactively refresh the /authorization/code token.

        The @refresh_token_decorator checks whether the OAuth access token is
        close to expiry and calls refresh_login() first if needed.  Use this
        for scheduled / background refreshes.  For reactive refreshes (after a
        401 is already in hand) use fetch_authorization_token() directly so the
        caller can ensure the access token is already fresh before calling.
        """
        return await self.fetch_authorization_token()

    async def fetch_authorization_token(self) -> Response:
        """Call POST /authorization/code with the current access token.

        Does **not** check token expiry first — the caller is responsible for
        ensuring login_info.access_token is valid before calling this.  This is
        the shared implementation used by both the proactive decorated path and
        the reactive force-refresh path in TokenManager.
        """
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_DOMAIN}/authorization/code",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                },
                json={"clientId": MAMMOTION_CLIENT_ID},
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                # This is the /authorization/code endpoint, NOT handle_expiry.  Its
                # response carries data.code (a fresh authorization *code*), and only
                # SOMETIMES data.accessToken.  When accessToken is absent (the common
                # case — see logs) the access token is left UNCHANGED, so this call
                # alone does not recover an expired bearer; the access token must come
                # from refresh_login()/refresh_token_v2().  Logged explicitly so a
                # "still 401 after token refresh" can be traced to a no-op authz fetch.
                had_access_token = "accessToken" in (data.get("data") or {})
                _LOGGER.debug(
                    "fetch_authorization_token: code=%s, carries_accessToken=%s (access_token left fp=%s)",
                    data.get("code"),
                    had_access_token,
                    _token_fingerprint(self._login_info.access_token if self._login_info else None),
                )
                if data.get("code") != 0:
                    return Response(code=data.get("code"), msg="Failed to refresh token")
                login_info = self._require_login_info
                login_info.access_token = data["data"].get("accessToken", login_info.access_token)
                login_info.authorization_code = data["data"].get("code", login_info.authorization_code)
                return Response.from_dict(data)

        return Response(code=200, msg="success")

    @refresh_token_decorator
    async def pair_devices_mqtt(self, mower_name: str, rtk_name: str) -> Response:
        """Pair a mower and an RTK device together via the cloud API."""
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_API_DOMAIN}/device-server/v1/iot/device/pairing",
                headers=self._headers,
                json={"mowerName": mower_name, "rtkName": rtk_name},
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                _LOGGER.debug("pair_devices_mqtt response: %s", data)
                return Response.from_dict(data)

        return Response(code=200, msg="success")

    @refresh_token_decorator
    async def unpair_devices_mqtt(self, mower_name: str, rtk_name: str) -> Response:
        """Unpair a mower and an RTK device via the cloud API."""
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_API_DOMAIN}/device-server/v1/iot/device/unpairing",
                headers=self._headers,
                json={"mowerName": mower_name, "rtkName": rtk_name},
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                _LOGGER.debug("unpair_devices_mqtt response: %s", data)
                return Response.from_dict(data)

        return Response(code=200, msg="success")

    @refresh_token_decorator
    async def net_rtk_enable(self, device_id: str) -> Response:
        """Enable network RTK for the given device."""
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_API_DOMAIN}/device-server/v1/iot/net-rtk/enable",
                headers=self._headers,
                json={"deviceId": device_id},
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                _LOGGER.debug("net_rtk_enable response: %s", data)
                return Response.from_dict(data)

        return Response(code=200, msg="success")

    @refresh_token_decorator
    async def get_stream_subscription(self, iot_id: str, is_yuka: bool) -> Response[StreamSubscriptionResponse]:
        # Prepare the payload with cameraStates based on is_yuka flag
        """Fetches stream subscription data for a given IoT device."""

        payload = {"deviceId": iot_id, "mode": 0, "cameraStates": []}

        # Add appropriate cameraStates based on the is_yuka flag
        # yukas have two cameras you could view [{"cameraState": 1}, {"cameraState": 0}, {"cameraState": 1}]
        # but its not useful so ignore this and only subscribe to the front one.
        if is_yuka:
            payload["cameraStates"] = [{"cameraState": 1}, {"cameraState": 0}, {"cameraState": 0}]
        else:
            payload["cameraStates"] = [{"cameraState": 1}, {"cameraState": 0}, {"cameraState": 0}]

        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_API_DOMAIN}/device-server/v1/stream/token",
                json=payload,
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                },
            )
            content_type = resp.headers.get("Content-Type") or ""
            body = await resp.text()
            _LOGGER.debug(
                "stream/token response: status=%s content-type=%s body=%.500s",
                resp.status,
                content_type,
                body,
            )
            if content_type.startswith("application/json"):
                response = response_factory(Response[StreamSubscriptionResponse], json.loads(body))
                if response.data is None:
                    _LOGGER.warning(
                        "stream/token returned JSON with no stream data (code=%s msg=%s)",
                        response.code,
                        response.msg,
                    )
                return response

            _LOGGER.warning(
                "stream/token returned non-JSON response (status=%s content-type=%s)",
                resp.status,
                content_type,
            )
            return Response(code=resp.status, msg="non-json response")

    @refresh_token_decorator
    async def get_video_resource(self, iot_id: str) -> Response[VideoResourceResponse]:
        """Fetch video resource for a given IoT ID."""
        async with self._client_session() as session:
            resp = await session.get(
                f"{MAMMOTION_API_DOMAIN}/device-server/v1/video-resource/{iot_id}",
                headers={
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                },
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                return response_factory(Response[VideoResourceResponse], data)

        return Response(code=200, msg="success")

    @refresh_token_decorator
    async def get_device_ota_firmware(self, iot_ids: list[str]) -> Response[list[CheckDeviceVersion]]:
        """Checks device firmware versions for a list of IoT IDs."""
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_API_DOMAIN}/device-server/v1/devices/version/check",
                json={"deviceIds": iot_ids},
                headers={
                    **self._headers,
                    "App-Version": f"HA,{APP_VERSION}",
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                # TODO catch errors from mismatch like token expire etc
                return response_factory(Response[list[CheckDeviceVersion]], data)

        return Response(code=200, msg="success", data=[])

    @refresh_token_decorator
    async def start_ota_upgrade(self, iot_id: str, version: str) -> Response[str]:
        """Initiates an OTA upgrade for a device."""
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_API_DOMAIN}/device-server/v1/ota/device/upgrade",
                json={"deviceId": iot_id, "version": version},
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                # TODO catch errors from mismatch like token expire etc
                return response_factory(Response[str], data)

        return Response(code=200, msg="success")

    @refresh_token_decorator
    async def get_rtk_devices(self) -> Response[list[RTK]]:
        """Fetches stream subscription data from agora.io for a given IoT device."""
        async with self._client_session() as session:
            resp = await session.get(
                f"{MAMMOTION_API_DOMAIN}/device-server/v1/rtk/devices",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                },
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                data = await resp.json()
                return response_factory(Response[list[RTK]], data)

        return Response(code=200, msg="success", data=[])

    @refresh_token_decorator
    async def get_user_device_list(self) -> Response[list[DeviceInfo]]:
        """Fetches device list for a user (owned not shared, shared returns nothing)."""
        async with self._client_session() as session:
            resp = await session.get(
                f"{MAMMOTION_API_DOMAIN}/device-server/v1/device/list",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                resp_dict = await resp.json()
                response = response_factory(Response[list[DeviceInfo]], resp_dict)
                self.device_info = response.data if response.data else self.device_info
                return response

        return Response(code=200, msg="success", data=[])

    @refresh_token_decorator
    async def get_user_shared_device_page(self) -> Response[ShareRecords]:
        """Fetches pending share invitations for the current user."""
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_API_DOMAIN}/user-server/v1/share/device/page",
                json={"iotId": "", "owned": 0, "pageNumber": 1, "pageSize": 200, "statusList": [-1]},
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                resp_dict = await resp.json()
                response = response_factory(Response[ShareRecords], resp_dict)
                self.devices_shared_info = response.data if response.data else self.devices_shared_info
                return response

        return Response(code=200, msg="success")

    @refresh_token_decorator
    async def confirm_share(self, batch_id: str, record_ids: list[int], agree: int = 1) -> Response[dict]:
        """Accept or reject share invitations for a single batch.

        agree=1 accepts, agree=0 rejects.  record_ids are the integer values of
        ShareRecord.record_id for all records in the batch.
        """
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_API_DOMAIN}/user-server/v1/share/device/confirm",
                json={"agree": agree, "batchId": batch_id, "recordIds": record_ids},
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            )
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                resp_dict = await resp.json()
                return response_factory(Response[dict], resp_dict)

        return Response(code=200, msg="success")

    @refresh_token_decorator
    async def get_user_device_page(self) -> Response[DeviceRecords]:
        """Fetches device list for a user, is either new API or for newer devices."""
        async with self._client_session() as session:
            resp = await session.post(
                f"{self.jwt_info.iot}/v1/user/device/page",
                json={
                    "iotId": "",
                    "pageNumber": 1,
                    "pageSize": 100,
                },
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
            )
            if resp.status != 200:
                return Response.from_dict({"code": resp.status, "msg": "get device list failed"})
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                resp_dict = await resp.json()
                response = response_factory(Response[DeviceRecords], resp_dict)
                self.device_records = response.data if response.data else self.device_records
                return response

        return Response(code=200, msg="success")

    @retry_on_network_error
    @refresh_token_decorator
    async def get_mqtt_credentials(self) -> Response[MQTTConnection]:
        """Get mammotion mqtt credentials"""
        async with self._client_session() as session:
            resp = await session.post(
                f"{self.jwt_info.iot}/v1/mqtt/auth/jwt",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            )
            if resp.status != 200:
                return Response.from_dict({"code": resp.status, "msg": "get mqtt failed"})
            if (resp.headers.get("Content-Type") or "").startswith("application/json"):
                resp_dict = await resp.json()
                response = response_factory(Response[MQTTConnection], resp_dict)
                self.mqtt_credentials = response.data
                return response

        return Response(code=200, msg="success")

    async def mqtt_invoke(self, content: str, device_name: str, iot_id: str) -> Response[dict]:
        """Send mqtt commands to devices."""
        _LOGGER.debug(f"mqtt invoke content: {content}, {self.jwt_info.iot}")
        async with self._client_session() as session:
            resp = await session.post(
                f"{self.jwt_info.iot}/v1/mqtt/rpc/thing/service/invoke",
                json={
                    "args": {"content": content},
                    "deviceName": device_name,
                    "identifier": "device_protobuf_sync_service",
                    "iotId": iot_id,
                    "productKey": "",
                },
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self._require_login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                    "Request-Id": "".join([str(random.randint(0, 9)) for _ in range(21)]),
                    "Accept-Language": "en-US",
                    "L-T-Z": f"{int(time.time())}/0/0",
                },
            )
            resp_dict = await resp.json()
        # Check auth failure BEFORE the generic non-200 bail-out: a 401 can arrive as
        # an HTTP status or as an in-body code, and it must surface as
        # UnauthorizedException (which drives the force-refresh path) rather than a
        # plain Response(code=401).
        if resp.status == 401 or resp_dict.get("code") == 401:
            _LOGGER.debug(
                "mqtt_invoke: 401 for iot_id=%s with access_token fp=%s",
                iot_id,
                _token_fingerprint(self._login_info.access_token if self._login_info else None),
            )
            raise UnauthorizedExceptionError("Access Token expired")
        if resp.status != 200:
            return Response.from_dict({"code": resp.status, "msg": "invoke mqtt failed"})
        if resp_dict.get("code") != 0:
            return Response.from_dict({"code": resp_dict.get("code"), "msg": resp_dict.get("msg")})

        return response_factory(Response[dict], resp_dict)

    async def logout(self) -> None:
        """Invalidate the current session by calling the v3 logout endpoint."""
        if self.login_info is None:
            return
        async with self._client_session() as session:
            await session.post(
                f"{MAMMOTION_API_DOMAIN}/user-server/v3/user/logout",
                headers=self.generate_headers(self._require_login_info.access_token),
            )
        self.login_info = None
        self._headers.pop("Authorization", None)
        # Any caller reading these after a logout should see "no creds" rather
        # than a JWT/expiry bound to the previous login.  Without this, a stale
        # MQTT JWT survives the logout and gets re-used until the next explicit
        # get_mqtt_credentials() call.
        self.mqtt_credentials = None
        self.expires_in = 0.0
        self.jwt_info = JWTTokenInfo("", "")

    async def refresh_login(self) -> Response[LoginResponseData]:
        """Attempt a token refresh, falling back to a full re-login if the token has already expired."""
        if self._login_info is not None:
            res = await self.refresh_token_v2()
            if res.code == 0:
                return res
            _LOGGER.debug("refresh_login: refresh_token_v2 failed (code=%s) — falling back to full login_v2", res.code)
        return await self.login_v2(self.account, self._password)  # type: ignore

    async def login(self, account: str, password: str) -> Response[LoginResponseData]:
        """Logs in to the service using provided account and password."""
        self.account = account
        self._password = password
        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_DOMAIN}/oauth/token",
                headers={
                    **self._headers,
                    "Encrypt-Key": self.encryption_utils.encrypt_by_public_key() or "",
                    "Decrypt-Type": "3",
                    "Ec-Version": "v1",
                },
                params={
                    "username": self.encryption_utils.encryption_by_aes(account) or "",
                    "password": self.encryption_utils.encryption_by_aes(password) or "",
                    "client_id": self.encryption_utils.encryption_by_aes(MAMMOTION_CLIENT_ID) or "",
                    "client_secret": self.encryption_utils.encryption_by_aes(MAMMOTION_CLIENT_SECRET) or "",
                    "grant_type": self.encryption_utils.encryption_by_aes("password") or "",
                },
            )
            if resp.status != 200:
                _LOGGER.debug("login_v2 failed (status=%s): %s", resp.status, resp.json())
                return Response.from_dict({"code": resp.status, "msg": "Login failed"})
            data = await resp.json()
        login_response = response_factory(Response[LoginResponseData], data)
        if login_response is None or login_response.data is None:
            _LOGGER.debug("login_v2 returned empty response: %s", login_response)
            return Response.from_dict({"code": resp.status, "msg": "Login failed"})
        self.login_info = login_response.data
        self.expires_in = login_response.data.expires_in + time.time()
        self._headers["Authorization"] = (
            f"Bearer {self._require_login_info.access_token}" if login_response.data else ""
        )
        self.response = login_response
        self.msg = login_response.msg
        self.code = login_response.code
        # TODO catch errors from mismatch user / password elsewhere
        # Assuming the data format matches the expected structure
        return login_response

    async def refresh_token_v2(self) -> Response[LoginResponseData]:
        """Refresh token v2."""

        timestamp = int(time.time() * 1000)

        refresh_request = {
            "client_id": MAMMOTION_OAUTH2_CLIENT_ID,
            "refresh_token": self._require_login_info.refresh_token,
            "grant_type": "refresh_token",
        }

        oauth_signature = create_oauth_signature(
            login_req=refresh_request,
            client_id=MAMMOTION_OAUTH2_CLIENT_ID,
            client_secret=MAMMOTION_OAUTH2_CLIENT_SECRET,
            token_endpoint="/oauth2/token",
            timestamp=timestamp,
        )

        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_DOMAIN}/oauth2/token",
                headers={
                    **self._headers,
                    "Ma-Iot-Signature": oauth_signature,
                    "Ma-Timestamp": str(timestamp),
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
                params={
                    **refresh_request,
                },
            )
            data = await resp.json()
        refresh_response = response_factory(Response[LoginResponseData], data)
        if refresh_response is None or refresh_response.data is None:
            _LOGGER.debug("refresh_token_v2: empty/failed response (status=%s, code=%s)", resp.status, data.get("code"))
            return Response.from_dict({"code": resp.status, "msg": "Refresh login token failed"})
        _LOGGER.debug(
            "refresh_token_v2: OK — access_token %s -> %s",
            _token_fingerprint(self._login_info.access_token if self._login_info else None),
            _token_fingerprint(refresh_response.data.access_token),
        )
        self.login_info = refresh_response.data
        self.expires_in = refresh_response.data.expires_in + time.time()
        self._headers["Authorization"] = (
            f"Bearer {self._require_login_info.access_token}" if refresh_response.data else ""
        )
        self.response = refresh_response
        self.msg = refresh_response.msg
        self.code = refresh_response.code
        return refresh_response

    async def login_v2(self, account: str, password: str) -> Response[LoginResponseData]:
        """Logs in to the service using provided account and password."""
        self.account = account
        self._password = password

        timestamp = int(time.time() * 1000)

        login_request = {
            "username": account,
            "password": base64.b64encode(password.encode("utf-8")).decode("utf-8"),
            "client_id": MAMMOTION_OAUTH2_CLIENT_ID,
            "grant_type": "password",
            "authType": "0",
        }

        oauth_signature = create_oauth_signature(
            login_req=login_request,
            client_id=MAMMOTION_OAUTH2_CLIENT_ID,
            client_secret=MAMMOTION_OAUTH2_CLIENT_SECRET,
            token_endpoint="/oauth2/token",
            timestamp=timestamp,
        )

        async with self._client_session() as session:
            resp = await session.post(
                f"{MAMMOTION_DOMAIN}/oauth2/token",
                headers={
                    **self._headers,
                    "Ma-App-Key": MAMMOTION_OAUTH2_CLIENT_ID,
                    "Ma-Signature": oauth_signature,
                    "Ma-Timestamp": str(timestamp),
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
                params={
                    **login_request,
                },
            )
            if resp.status != 200:
                return Response.from_dict({"code": resp.status, "msg": "Login failed"})
            data = await resp.json()
        if data.get("code") != 0:
            return Response.from_dict({"code": resp.status, "msg": data.get("msg") or "Login failed"})
        login_response = response_factory(Response[LoginResponseData], data)
        if login_response is None or login_response.data is None:
            return Response.from_dict({"code": resp.status, "msg": "Login failed"})
        self.login_info = login_response.data
        self.expires_in = login_response.data.expires_in + time.time()
        self._headers["Authorization"] = (
            f"Bearer {self._require_login_info.access_token}" if login_response.data else ""
        )
        self.response = login_response
        self.msg = login_response.msg
        self.code = login_response.code
        # TODO catch errors from mismatch user / password elsewhere
        # Assuming the data format matches the expected structure
        return login_response
