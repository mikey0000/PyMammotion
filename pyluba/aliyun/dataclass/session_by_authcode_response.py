from dataclasses import dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class TokenData(DataClassORJSONMixin):
    identityId: str
    refreshTokenExpire: int
    iotToken: str
    iotTokenExpire: int
    refreshToken: str


@dataclass
class SessionByAuthCodeResponse(DataClassORJSONMixin):
    code: int
    data: TokenData
