from dataclasses import dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class SessionOauthToken(DataClassORJSONMixin):
    """Aliyun IoT OAuth token bundle including identity ID and expiry information."""

    identityId: str
    refreshTokenExpire: int
    iotToken: str
    iotTokenExpire: int
    refreshToken: str


@dataclass
class SessionByAuthCodeResponse(DataClassORJSONMixin):
    """Top-level response from the session-by-auth-code API."""

    code: int
    data: SessionOauthToken | None = None
    token_issued_at: int | None = None
