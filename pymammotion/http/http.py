import csv
from typing import cast

from aiohttp import ClientSession

from pymammotion.aliyun.model.stream_subscription_response import StreamSubscriptionResponse
from pymammotion.const import MAMMOTION_API_DOMAIN, MAMMOTION_CLIENT_ID, MAMMOTION_CLIENT_SECRET, MAMMOTION_DOMAIN
from pymammotion.http.encryption import EncryptionUtils
from pymammotion.http.model.http import ErrorInfo, LoginResponseData, Response


class MammotionHTTP:
    def __init__(self) -> None:
        self.code = None
        self.msg = None
        self.response: Response | None = None
        self.login_info: LoginResponseData | None = None
        self._headers = {"User-Agent": "okhttp/3.14.9", "App-Version": "google Pixel 2 XL taimen-Android 11,1.11.332"}
        self.encryption_utils = EncryptionUtils()

    @staticmethod
    def generate_headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    async def login_by_email(self, email: str, password: str) -> Response[LoginResponseData]:
        return await self.login(email, password)

    async def get_all_error_codes(self) -> dict[str, ErrorInfo]:
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/user-server/v1/code/record/export-data",
                headers=self._headers,
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
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post("/user-server/v1/user/oauth/check", headers=self._headers) as resp:
                data = await resp.json()
                return Response.from_dict(data)

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

    async def get_stream_subscription(self, iot_id: str) -> Response[StreamSubscriptionResponse]:
        """Get agora.io data for view camera stream"""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/device-server/v1/stream/subscription",
                json={"deviceId": iot_id},
                headers={
                    "Authorization": f"{self._headers.get('Authorization', "")}",
                    "Content-Type": "application/json",
                    "User-Agent": "okhttp/3.14.9",
                },
            ) as resp:
                data = await resp.json()
                # TODO catch errors from mismatch like token expire etc
                # Assuming the data format matches the expected structure
                return Response[StreamSubscriptionResponse].from_dict(data)

    async def login(self, username: str, password: str) -> Response[LoginResponseData]:
        async with ClientSession(MAMMOTION_DOMAIN) as session:
            async with session.post(
                "/oauth/token",
                headers={
                    "User-Agent": "okhttp/3.14.9",
                    "App-Version": "google Pixel 2 XL taimen-Android 11,1.11.332",
                    "Encrypt-Key": self.encryption_utils.encrypt_by_public_key(),
                    "Decrypt-Type": "3",
                    "Ec-Version": "v1",
                },
                params=dict(
                    username=self.encryption_utils.encryption_by_aes(username),
                    password=self.encryption_utils.encryption_by_aes(password),
                    client_id=self.encryption_utils.encryption_by_aes(MAMMOTION_CLIENT_ID),
                    client_secret=self.encryption_utils.encryption_by_aes(MAMMOTION_CLIENT_SECRET),
                    grant_type=self.encryption_utils.encryption_by_aes("password"),
                ),
            ) as resp:
                if resp.status != 200:
                    print(resp.json())
                    return Response.from_dict({"status": resp.status, "msg": "Login failed"})
                data = await resp.json()
                login_response = Response[LoginResponseData].from_dict(data)
                if login_response.data is None:
                    print(login_response)
                    return Response.from_dict({"status": resp.status, "msg": "Login failed"})
                self.login_info = LoginResponseData.from_dict(login_response.data)
                self._headers["Authorization"] = (
                    f"Bearer {self.login_info.access_token}" if login_response.data else None
                )
                self.response = login_response
                self.msg = login_response.msg
                self.code = login_response.code
                # TODO catch errors from mismatch user / password elsewhere
                # Assuming the data format matches the expected structure
                return login_response
