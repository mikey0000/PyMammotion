from dataclasses import dataclass
from typing import Optional

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class SessionOauthToken(DataClassORJSONMixin):
    identityId: str
    refreshTokenExpire: int
    iotToken: str
    iotTokenExpire: int
    refreshToken: str


@dataclass
class SessionByAuthCodeResponse(DataClassORJSONMixin):
    code: int
    data: Optional[SessionOauthToken] = None
