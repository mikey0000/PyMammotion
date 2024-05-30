from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from aiohttp import ClientSession
from mashumaro import DataClassDictMixin
from mashumaro.mixins.orjson import DataClassORJSONMixin

DataT = TypeVar("DataT")


class Response(DataClassDictMixin, Generic[DataT]):
    data: DataT
    code: int
    msg: str

@dataclass
class LoginResponseUserInformation(DataClassORJSONMixin):
    areaCode: str
    domainAbbreviation: str
    email: str
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


class LubaHTTP:
    def __init__(self, session: ClientSession, login: LoginResponseData):
        self._session = session
        self._session.headers["Authorization"] = f"Bearer {login.access_token}"
        self._login = login

    @classmethod
    async def login(self, session: ClientSession, username: str, password: str) -> Response[LoginResponseData]:
        async with session.post(
                "/user-server/v1/user/oauth/token",
                params=dict(
                    username=username,
                    password=password,
                    client_id="MADKALUBAS",
                    client_secret="GshzGRZJjuMUgd2sYHM7",
                    grant_type="password"
                )
        ) as resp:
            data = await resp.json()
            print(data)
            return Response[LoginResponseData](**data)


async def connect_http(username: str, password: str) -> LubaHTTP:
    async with ClientSession("https://domestic.mammotion.com") as session:
        login = await LubaHTTP.login(session, username, password)
        yield LubaHTTP(session, login.data)
