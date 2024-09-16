import csv
from typing import cast

from aiohttp import ClientSession

from pymammotion.aliyun.model.stream_subscription_response import StreamSubscriptionResponse
from pymammotion.const import (
    MAMMOTION_API_DOMAIN,
    MAMMOTION_CLIENT_ID,
    MAMMOTION_CLIENT_SECRET,
    MAMMOTION_DOMAIN,
)
from pymammotion.http.model.http import ErrorInfo, LoginResponseData, Response


class MammotionHTTP:
    def __init__(self, response: Response) -> None:
        self._headers = dict()
        self.login_info = LoginResponseData.from_dict(response.data) if response.data else None
        self._headers["Authorization"] = f"Bearer {self.login_info.access_token}" if response.data else None
        self.msg = response.msg
        self.code = response.code

    async def get_all_error_codes(self) -> list[ErrorInfo]:
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/user-server/v1/code/record/export-data",
                headers=self._headers,
            ) as resp:
                data = await resp.json()
                reader = csv.DictReader(data.get("data", "").split("\n"), delimiter=",")
                codes = []
                for row in reader:
                    codes.append(ErrorInfo(**cast(row, dict)))
                return codes

    async def oauth_check(self) -> None:
        """Check if token is valid.

        Returns 401 if token is invalid. We then need to re-authenticate, can try to refresh token first
        """
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post("/user-server/v1/user/oauth/check") as resp:
                data = await resp.json()
                response = Response.from_dict(data)

    async def get_stream_subscription(self, iot_id: str) -> Response[StreamSubscriptionResponse]:
        """Get agora.io data for view camera stream"""
        async with ClientSession(MAMMOTION_API_DOMAIN) as session:
            async with session.post(
                "/device-server/v1/stream/subscription",
                json={"deviceId": iot_id},
                headers={
                    "Authorization": f"{self._headers.get('Authorization', "")}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                data = await resp.json()
                # TODO catch errors from mismatch like token expire etc
                # Assuming the data format matches the expected structure
                return Response[StreamSubscriptionResponse].from_dict(data)

    @classmethod
    async def login(cls, session: ClientSession, username: str, password: str) -> Response[LoginResponseData]:
        async with session.post(
            "/oauth/token",
            params=dict(
                username=username,
                password=password,
                client_id=MAMMOTION_CLIENT_ID,
                client_secret=MAMMOTION_CLIENT_SECRET,
                grant_type="password",
            ),
        ) as resp:
            data = await resp.json()
            response = Response.from_dict(data)
            # TODO catch errors from mismatch user / password elsewhere
            # Assuming the data format matches the expected structure
            return response


async def connect_http(username: str, password: str) -> MammotionHTTP:
    async with ClientSession(MAMMOTION_DOMAIN) as session:
        login_response = await MammotionHTTP.login(session, username, password)
        return MammotionHTTP(login_response)
