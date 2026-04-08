from dataclasses import dataclass

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class OpenAccount(DataClassORJSONMixin):
    """Open account profile returned after OAuth login."""

    displayName: str
    openId: str
    hasPassword: str
    subAccount: str
    pwdVersion: int
    mobileConflictAccount: str
    id: int
    mobileLocationCode: str
    avatarUrl: str
    domainId: int
    enableDevice: str
    status: int
    country: str | None = None


@dataclass
class OauthOtherInfo(DataClassORJSONMixin):
    """Additional OAuth metadata including session ID expiry."""

    SidExpiredTime: int


@dataclass
class LoginSuccessResult(DataClassORJSONMixin):
    """Successful login result containing tokens and account information."""

    reTokenExpireIn: int
    uidToken: str
    openAccount: OpenAccount
    initPwd: str
    sidExpireIn: int
    oauthOtherInfo: OauthOtherInfo
    refreshToken: str
    sid: str
    token: str


@dataclass
class InnerDataContent(DataClassORJSONMixin):
    """Inner data payload of an OAuth login response."""

    loginSuccessResult: LoginSuccessResult
    mobileBindRequired: str


@dataclass
class InnerData(DataClassORJSONMixin):
    """Inner envelope of the OAuth login response with trace and status fields."""

    traceId: str
    vid: str
    code: int
    data: InnerDataContent
    subCode: int
    message: str
    successful: str
    deviceId: str | None = None


@dataclass
class LoginByOAuthResponse(DataClassORJSONMixin):
    """Top-level response from the login-by-OAuth API."""

    data: InnerData
    success: str
    api: str
    errorMsg: str
