from dataclasses import dataclass
from typing import Generic, Literal, TypeVar, Optional

from mashumaro import DataClassDictMixin
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