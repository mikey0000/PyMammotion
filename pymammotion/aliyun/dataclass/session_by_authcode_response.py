from dataclasses import dataclass, field
from datetime import time

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
    data: SessionOauthToken
