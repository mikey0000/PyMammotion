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
    data: DataT
    code: int
    msg: str


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
    def __init__(self, login: LoginResponseData):
        self._headers = dict()
        self._headers["Authorization"] = f"Bearer {login.access_token}"
        self.login_info = login

    @classmethod
    async def login(cls, session: ClientSession, username: str, password: str) -> Response[LoginResponseData]:
        async with session.post(
            "/user-server/v1/user/oauth/token",
            params=dict(
                username=username,
                password=password,
                client_id=MAMMOTION_CLIENT_ID,
                client_secret=MAMMOTION_CLIENT_SECRET,
                grant_type="password",
            ),
        ) as resp:
            data = await resp.json()
            # TODO catch errors from mismatch user / password
            # Assuming the data format matches the expected structure
            login_response_data = LoginResponseData.from_dict(data["data"])
            return Response(data=login_response_data, code=data["code"], msg=data["msg"])


async def connect_http(username: str, password: str) -> MammotionHTTP:
    async with ClientSession(MAMMOTION_DOMAIN) as session:
        login_response = await MammotionHTTP.login(session, username, password)
        return MammotionHTTP(login_response.data)
