from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from aiohttp import ClientSession
from mashumaro import DataClassDictMixin
from mashumaro.mixins.orjson import DataClassORJSONMixin

from pyluba.const import MAMMOTION_DOMAIN, MAMMOTION_CLIENT_ID, MAMMOTION_CLIENT_SECRET

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
    async def login(cls, session: ClientSession, username: str, password: str) -> Response[LoginResponseData]:
        async with session.post(
                "/user-server/v1/user/oauth/token",
                params=dict(
                    username=username,
                    password=password,
                    client_id=MAMMOTION_CLIENT_ID,
                    client_secret=MAMMOTION_CLIENT_SECRET,
                    grant_type="password"
                )
        ) as resp:
            data = await resp.json()
            print(data)
            # TODO catch errors from mismatch user / password
            # Assuming the data format matches the expected structure
            login_response_data = LoginResponseData.from_dict(data["data"])
            return Response(data=login_response_data, code=data["code"], msg=data["msg"])

async def connect_http(username: str, password: str) -> LubaHTTP:
    async with ClientSession(MAMMOTION_DOMAIN) as session:
        login_response = await LubaHTTP.login(session, username, password)
        return LubaHTTP(session, login_response.data)