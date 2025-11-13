from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
import csv
from functools import wraps
import hashlib
import hmac
import json
import random
import time
from typing import Any, TypeVar, cast

from aiohttp import ClientSession
import jwt

from pymammotion.const import (
    MAMMOTION_API_DOMAIN,
    MAMMOTION_CLIENT_ID,
    MAMMOTION_CLIENT_SECRET,
    MAMMOTION_DOMAIN,
    MAMMOTION_OUATH2_CLIENT_ID,
    MAMMOTION_OUATH2_CLIENT_SECRET,
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
    UnauthorizedException,
)
from pymammotion.http.model.response_factory import response_factory
from pymammotion.http.model.rtk import RTK

T = TypeVar("T")


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


def create_oauth_signature(login_req: dict, client_id: str, client_secret: str, token_endpoint: str) -> str:
    """Create OAuth signature for login request.

    Args:
        login_req: Login request data as dictionary
        client_id: OAuth client ID
        client_secret: OAuth client secret
        token_endpoint: Token endpoint path

    Returns:
        HMAC-SHA256 signature

    """
    # Convert dict to JSON without HTML escaping (ensure_ascii=False handles this)
    json_data = json.dumps(login_req, ensure_ascii=False, separators=(",", ":"))

    # Get current timestamp in milliseconds
    timestamp = str(int(time.time() * 1000))

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
    signature = sign_with_hmac_sha256(str_to_sign, hashed_secret)

    return signature


class MammotionHTTP:
    def __init__(self, account: str | None = None, password: str | None = None) -> None:
        self.device_info: list[DeviceInfo] = []
        self.mqtt_credentials: MQTTConnection | None = None
        self.device_records: DeviceRecords = DeviceRecords(records=[], current=0, total=0, size=0, pages=0)
        self.expires_in = 0.0
        self.code = 0
        self.msg = None
        self.account = account
        self._password = password
        self._response: Response | None = None
        self.login_info: LoginResponseData | None = None
        self.jwt_info: JWTTokenInfo = JWTTokenInfo("", "")
        self._headers = {"User-Agent": "okhttp/4.9.3", "App-Version": "Home Assistant,1.15.6.14"}
        self.encryption_utils = EncryptionUtils()

        # Add this method to generate a 10-digit random number
        def get_10_random() -> str:
            """Generate a 10-digit random number as a string."""
            return "".join([str(random.randint(0, 9)) for _ in range(7)])

        # Replace the line in the __init__ method with:
        self.client_id = f"{int(time.time() * 1000)}_{get_10_random()}_1"

    @property
    def response(self) -> Response | None:
        return self._response

    @response.setter
    def response(self, response: Response) -> None:
        self._response = response
        decoded_token = jwt.decode(response.data.access_token, options={"verify_signature": False})
        if isinstance(decoded_token, dict):
            self.jwt_info = JWTTokenInfo(iot=decoded_token.get("iot", ""), robot=decoded_token.get("robot", ""))

    @staticmethod
    def generate_headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

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
                await self.refresh_login()
            return await func(self, *args, **kwargs)

        return wrapper

    async def handle_expiry(self, resp: Response) -> Response:
        if resp.code == 401 and self.account and self._password:
            return await self.login_v2(self.account, self._password)
        return resp

    async def login_by_email(self, email: str, password: str) -> Response[LoginResponseData]:
        return await self.login_v2(email, password)

    @refresh_token_decorator
    async def get_all_error_codes(self) -> dict[str, ErrorInfo]:
        """Retrieves and parses all error codes from the MAMMOTION API."""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/user-server/v1/code/record/export-data",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            ) as resp:
                data = await resp.json()
                reader = csv.DictReader(data.get("data", "").split("\n"), delimiter=",")
                codes = dict()
                for row in reader:
                    error_info = ErrorInfo(**cast(dict, row))
                    codes[error_info.code] = error_info
                return codes

    async def oauth_check(self) -> Response:
        """Check if token is valid.

        Returns 401 if token is invalid. We then need to re-authenticate, can try to refresh token first
        """
        async with ClientSession(MAMMOTION_DOMAIN) as session:
            async with session.post(
                "/user-server/v1/user/oauth/check",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            ) as resp:
                data = await resp.json()
                return Response.from_dict(data)

    @refresh_token_decorator
    async def refresh_authorization_code(self) -> Response:
        """Refresh token."""
        async with ClientSession(MAMMOTION_DOMAIN) as session:
            async with session.post(
                "/authorization/code",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
                json={"clientId": MAMMOTION_CLIENT_ID},
            ) as resp:
                data = await resp.json()
                print(data)
                self.login_info.access_token = data["data"].get("accessToken", self.login_info.access_token)
                self.login_info.authorization_code = data["data"].get("code", self.login_info.authorization_code)
                await self.get_mqtt_credentials()
                return Response.from_dict(data)

    @refresh_token_decorator
    async def pair_devices_mqtt(self, mower_name: str, rtk_name: str) -> Response:
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/device-server/v1/iot/device/pairing",
                headers=self._headers,
                json={"mowerName": mower_name, "rtkName": rtk_name},
            ) as resp:
                data = await resp.json()
                if data.get("status") == 200:
                    print(data)
                    return Response.from_dict(data)
                else:
                    print(data)
                    return Response.from_dict(data)

    @refresh_token_decorator
    async def unpair_devices_mqtt(self, mower_name: str, rtk_name: str) -> Response:
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/device-server/v1/iot/device/unpairing",
                headers=self._headers,
                json={"mowerName": mower_name, "rtkName": rtk_name},
            ) as resp:
                data = await resp.json()
                if data.get("status") == 200:
                    print(data)
                    return Response.from_dict(data)
                else:
                    print(data)
                    return Response.from_dict(data)

    @refresh_token_decorator
    async def net_rtk_enable(self, device_id: str) -> Response:
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/device-server/v1/iot/net-rtk/enable", headers=self._headers, json={"deviceId": device_id}
            ) as resp:
                data = await resp.json()
                if data.get("status") == 200:
                    print(data)
                    return Response.from_dict(data)
                else:
                    print(data)
                    return Response.from_dict(data)

    @refresh_token_decorator
    async def get_stream_subscription(self, iot_id: str) -> Response[StreamSubscriptionResponse]:
        """Fetches stream subscription data from agora.io for a given IoT device."""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/device-server/v1/stream/subscription",
                json={"deviceId": iot_id},
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            ) as resp:
                data = await resp.json()
                # TODO catch errors from mismatch like token expire etc
                # Assuming the data format matches the expected structure
                response = Response[StreamSubscriptionResponse].from_dict(data)
                await self.handle_expiry(response)
                if response.code != 0:
                    return response
                response.data = StreamSubscriptionResponse.from_dict(data.get("data", {}))
                return response

    @refresh_token_decorator
    async def get_stream_subscription_mini_or_x_series(
        self, iot_id: str, is_yuka: bool
    ) -> Response[StreamSubscriptionResponse]:
        # Prepare the payload with cameraStates based on is_yuka flag
        """Fetches stream subscription data for a given IoT device."""

        payload = {"deviceId": iot_id, "mode": 0, "cameraStates": []}

        # Add appropriate cameraStates based on the is_yuka flag
        if is_yuka:
            payload["cameraStates"] = [{"cameraState": 1}, {"cameraState": 0}, {"cameraState": 1}]
        else:
            payload["cameraStates"] = [{"cameraState": 1}, {"cameraState": 0}, {"cameraState": 0}]

        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/device-server/v1/stream/token",
                json=payload,
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            ) as resp:
                data = await resp.json()
                # TODO catch errors from mismatch like token expire etc
                # Assuming the data format matches the expected structure
                response = Response[StreamSubscriptionResponse].from_dict(data)
                await self.handle_expiry(response)
                if response.code != 0:
                    return response
                response.data = StreamSubscriptionResponse.from_dict(data.get("data", {}))
                return response

    @refresh_token_decorator
    async def get_video_resource(self, iot_id: str) -> Response[VideoResourceResponse]:
        """Fetch video resource for a given IoT ID."""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.get(
                f"/device-server/v1/video-resource/{iot_id}",
                headers={
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            ) as resp:
                data = await resp.json()
                # TODO catch errors from mismatch like token expire etc
                # Assuming the data format matches the expected structure
                response = Response[VideoResourceResponse].from_dict(data)
                if response.code != 0:
                    return response
                response.data = VideoResourceResponse.from_dict(data.get("data", {}))
                return response

    @refresh_token_decorator
    async def get_device_ota_firmware(self, iot_ids: list[str]) -> Response[list[CheckDeviceVersion]]:
        """Checks device firmware versions for a list of IoT IDs."""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/device-server/v1/devices/version/check",
                json={"deviceIds": iot_ids},
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
            ) as resp:
                data = await resp.json()
                # TODO catch errors from mismatch like token expire etc
                # Assuming the data format matches the expected structure
                return response_factory(Response[list[CheckDeviceVersion]], data)

    @refresh_token_decorator
    async def start_ota_upgrade(self, iot_id: str, version: str) -> Response[str]:
        """Initiates an OTA upgrade for a device."""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/device-server/v1/ota/device/upgrade",
                json={"deviceId": iot_id, "version": version},
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
            ) as resp:
                data = await resp.json()
                # TODO catch errors from mismatch like token expire etc
                # Assuming the data format matches the expected structure
                return response_factory(Response[str], data)

    @refresh_token_decorator
    async def get_rtk_devices(self) -> Response[list[RTK]]:
        """Fetches stream subscription data from agora.io for a given IoT device."""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.get(
                "/device-server/v1/rtk/devices",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            ) as resp:
                data = await resp.json()

                return response_factory(Response[list[RTK]], data)

    @refresh_token_decorator
    async def get_user_device_list(self) -> Response[list[DeviceInfo]]:
        """Fetches device list for a user (owned not shared, shared returns nothing)."""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.get(
                "/device-server/v1/device/list",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
            ) as resp:
                resp_dict = await resp.json()
                response = response_factory(Response[list[DeviceInfo]], resp_dict)
                self.device_info = response.data if response.data else self.device_info
                return response

    @refresh_token_decorator
    async def get_user_shared_device_page(self) -> Response[DeviceRecords]:
        """Fetches device list for a user (shared) but not accepted."""
        """Can set owned to zero or one to possibly check for not accepted mowers?"""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/user-server/v1/share/device/page",
                json={"iotId": "", "owned": 0, "pageNumber": 1, "pageSize": 200, "statusList": [-1]},
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            ) as resp:
                resp_dict = await resp.json()
                response = response_factory(Response[DeviceRecords], resp_dict)
                self.devices_shared_info = response.data if response.data else self.devices_shared_info
                return response

    @refresh_token_decorator
    async def get_user_device_page(self) -> Response[DeviceRecords]:
        """Fetches device list for a user, is either new API or for newer devices."""
        async with ClientSession(self.jwt_info.iot) as session:
            async with session.post(
                "/v1/user/device/page",
                json={
                    "iotId": "",
                    "pageNumber": 1,
                    "pageSize": 100,
                },
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
            ) as resp:
                if resp.status != 200:
                    return Response.from_dict({"code": resp.status, "msg": "get device list failed"})
                resp_dict = await resp.json()
                response = response_factory(Response[DeviceRecords], resp_dict)
                self.device_records = response.data if response.data else self.device_records
                return response

    @refresh_token_decorator
    async def get_mqtt_credentials(self) -> Response[MQTTConnection]:
        """Get mammotion mqtt credentials"""
        async with ClientSession(self.jwt_info.iot) as session:
            async with session.post(
                "/v1/mqtt/auth/jwt",
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                },
            ) as resp:
                if resp.status != 200:
                    return Response.from_dict({"code": resp.status, "msg": "get mqtt failed"})
                resp_dict = await resp.json()
                response = response_factory(Response[MQTTConnection], resp_dict)
                self.mqtt_credentials = response.data
                return response

    @refresh_token_decorator
    async def mqtt_invoke(self, content: str, device_name: str, iot_id: str) -> Response[dict]:
        """Send mqtt commands to devices."""
        async with ClientSession(self.jwt_info.iot) as session:
            async with session.post(
                "/v1/mqtt/rpc/thing/service/invoke",
                json={
                    "args": {"content": content},
                    "deviceName": device_name,
                    "identifier": "device_protobuf_sync_service",
                    "iotId": iot_id,
                    "productKey": "",
                },
                headers={
                    **self._headers,
                    "Authorization": f"Bearer {self.login_info.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/4.9.3",
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
            ) as resp:
                if resp.status != 200:
                    return Response.from_dict({"code": resp.status, "msg": "invoke mqtt failed"})
                if resp.status == 401:
                    raise UnauthorizedException("Access Token expired")
                resp_dict = await resp.json()
                return response_factory(Response[dict], resp_dict)

    async def refresh_login(self) -> Response[LoginResponseData]:
        if self.expires_in > time.time():
            res = await self.refresh_token_v2()
            if res.code == 0:
                return res
        return await self.login_v2(self.account, self._password)

    async def login(self, account: str, password: str) -> Response[LoginResponseData]:
        """Logs in to the service using provided account and password."""
        self.account = account
        self._password = password
        async with ClientSession(MAMMOTION_DOMAIN) as session:
            async with session.post(
                "/oauth/token",
                headers={
                    **self._headers,
                    "Encrypt-Key": self.encryption_utils.encrypt_by_public_key(),
                    "Decrypt-Type": "3",
                    "Ec-Version": "v1",
                },
                params={
                    "username": self.encryption_utils.encryption_by_aes(account),
                    "password": self.encryption_utils.encryption_by_aes(password),
                    "client_id": self.encryption_utils.encryption_by_aes(MAMMOTION_CLIENT_ID),
                    "client_secret": self.encryption_utils.encryption_by_aes(MAMMOTION_CLIENT_SECRET),
                    "grant_type": self.encryption_utils.encryption_by_aes("password"),
                },
            ) as resp:
                if resp.status != 200:
                    print(resp.json())
                    return Response.from_dict({"code": resp.status, "msg": "Login failed"})
                data = await resp.json()
                login_response = response_factory(Response[LoginResponseData], data)
                if login_response is None or login_response.data is None:
                    print(login_response)
                    return Response.from_dict({"code": resp.status, "msg": "Login failed"})
                self.login_info = login_response.data
                self.expires_in = login_response.data.expires_in + time.time()
                self._headers["Authorization"] = (
                    f"Bearer {self.login_info.access_token}" if login_response.data else None
                )
                self.response = login_response
                self.msg = login_response.msg
                self.code = login_response.code
                # TODO catch errors from mismatch user / password elsewhere
                # Assuming the data format matches the expected structure
                return login_response

    async def refresh_token_v2(self) -> Response[LoginResponseData]:
        """Refresh token v2."""

        refresh_request = {
            "client_id": MAMMOTION_OUATH2_CLIENT_ID,
            "refresh_token": self.login_info.refresh_token,
            "grant_type": "refresh_token",
        }

        oauth_signature = create_oauth_signature(
            login_req=refresh_request,
            client_id=MAMMOTION_OUATH2_CLIENT_ID,
            client_secret=MAMMOTION_OUATH2_CLIENT_SECRET,
            token_endpoint="/oauth2/token",
        )

        async with ClientSession(MAMMOTION_DOMAIN) as session:
            async with session.post(
                "/oauth2/token",
                headers={
                    **self._headers,
                    "Ma-Iot-Signature": oauth_signature,
                    "Ma-Timestamp": str(int(time.time())),
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
                params={
                    **refresh_request,
                },
            ) as resp:
                data = await resp.json()
                refresh_response = response_factory(Response[LoginResponseData], data)
                if refresh_response is None or refresh_response.data is None:
                    return Response.from_dict({"code": resp.status, "msg": "Login failed"})
                self.login_info = refresh_response.data
                self.expires_in = refresh_response.data.expires_in + time.time()
                self._headers["Authorization"] = (
                    f"Bearer {self.login_info.access_token}" if refresh_response.data else None
                )
                self.response = refresh_response
                self.msg = refresh_response.msg
                self.code = refresh_response.code
                return refresh_response

    async def login_v2(self, account: str, password: str) -> Response[LoginResponseData]:
        """Logs in to the service using provided account and password."""
        self.account = account
        self._password = password

        login_request = {
            "username": account,
            "password": base64.b64encode(password.encode("utf-8")).decode("utf-8"),
            "client_id": MAMMOTION_OUATH2_CLIENT_ID,
            "grant_type": "password",
            "authType": "0",
        }

        oauth_signature = create_oauth_signature(
            login_req=login_request,
            client_id=MAMMOTION_OUATH2_CLIENT_ID,
            client_secret=MAMMOTION_OUATH2_CLIENT_SECRET,
            token_endpoint="/oauth2/token",
        )

        async with ClientSession(MAMMOTION_DOMAIN) as session:
            async with session.post(
                "/oauth2/token",
                headers={
                    **self._headers,
                    "Ma-App-Key": MAMMOTION_OUATH2_CLIENT_ID,
                    "Ma-Signature": oauth_signature,
                    "Ma-Timestamp": str(int(time.time())),
                    "Client-Id": self.client_id,
                    "Client-Type": "1",
                },
                params={
                    **login_request,
                },
            ) as resp:
                if resp.status != 200:
                    print(resp.json())
                    return Response.from_dict({"code": resp.status, "msg": "Login failed"})
                data = await resp.json()
                login_response = response_factory(Response[LoginResponseData], data)
                if login_response is None or login_response.data is None:
                    return Response.from_dict({"code": resp.status, "msg": "Login failed"})
                self.login_info = login_response.data
                self.expires_in = login_response.data.expires_in + time.time()
                self._headers["Authorization"] = (
                    f"Bearer {self.login_info.access_token}" if login_response.data else None
                )
                self.response = login_response
                self.msg = login_response.msg
                self.code = login_response.code
                # TODO catch errors from mismatch user / password elsewhere
                # Assuming the data format matches the expected structure
                return login_response
