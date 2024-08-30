from dataclasses import dataclass
from typing import Generic, Literal, Optional, TypeVar

from aiohttp import ClientSession
from aiohttp.hdrs import AUTHORIZATION
from mashumaro import DataClassDictMixin
from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.aliyun.dataclass.connect_response import Device
from pymammotion.const import (
    MAMMOTION_CLIENT_ID,
    MAMMOTION_CLIENT_SECRET,
    MAMMOTION_DOMAIN,
)

DataT = TypeVar("DataT")


@dataclass
class Response(DataClassDictMixin, Generic[DataT]):
    code: int
    msg: str
    data: DataT | None = None


@dataclass
class LoginResponseUserInformation(DataClassORJSONMixin):
    areaCode: str
    domainAbbreviation: str
    email: Optional[str]
    userId: str
    userAccount: str
    authType: str


@dataclass
class LoginResponseData(DataClassORJSONMixin):
    access_token: str
    token_type: Literal["bearer"]
    refresh_token: str
    expires_in: int
    scope: Literal["read"]
    grant_type: Literal["password"]
    authorization_code: str
    userInformation: LoginResponseUserInformation
    jti: str


class MammotionHTTP:
    def __init__(self, response: Response):
        self._headers = dict()
        self.login_info = LoginResponseData.from_dict(response.data) if response.data else None
        self._headers["Authorization"] = f"Bearer {self.login_info.access_token}" if response.data else None
        self.msg = response.msg
        self.code = response.code

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
            if resp.status == 200:
                data = await resp.json()
                response = Response.from_dict(data)
                # TODO catch errors from mismatch user / password elsewhere
                # Assuming the data format matches the expected structure
                return response


async def connect_http(username: str, password: str) -> MammotionHTTP:
    async with ClientSession(MAMMOTION_DOMAIN) as session:
        login_response = await MammotionHTTP.login(session, username, password)
        return MammotionHTTP(login_response)
