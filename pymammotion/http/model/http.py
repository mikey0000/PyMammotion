from dataclasses import dataclass
from typing import Generic, Literal, Optional, TypeVar

from mashumaro import DataClassDictMixin
from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin

DataT = TypeVar("DataT")


@dataclass
class ErrorInfo:
    code: str
    platform: str
    module: str
    variant: str
    level: str
    description: str
    en_implication: str
    en_solution: str
    zh_implication: str
    zh_solution: str
    de_implication: str
    de_solution: str
    fr_implication: str
    fr_solution: str
    it_implication: str
    it_solution: str
    es_implication: str
    es_solution: str
    cs_implication: str
    cs_solution: str
    sk_implication: str
    sk_solution: str
    pl_implication: str
    pl_solution: str
    nl_implication: str
    nl_solution: str
    da_implication: str
    da_solution: str
    sv_implication: str
    sv_solution: str
    sl_implication: str
    sl_solution: str
    pt_implication: str
    pt_solution: str


@dataclass
class Response(DataClassDictMixin, Generic[DataT]):
    code: int
    msg: str
    data: DataT | None = None

    class Config(BaseConfig):
        omit_default = True


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
