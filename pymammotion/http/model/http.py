from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from mashumaro import DataClassDictMixin
from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin

DataT = TypeVar("DataT")


@dataclass
class ErrorInfo(DataClassDictMixin):
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
    sr_implication: str
    sr_solution: str
    sv_implication: str
    sv_solution: str
    sl_implication: str
    sl_solution: str
    pt_implication: str
    pt_solution: str
    hu_implication: str
    hu_solution: str
    hr_implication: str
    hr_solution: str
    no_implication: str
    no_solution: str
    fi_implication: str
    fi_solution: str
    ro_implication: str
    ro_solution: str
    bg_implication: str
    bg_solution: str
    et_implication: str
    et_solution: str
    lv_implication: str
    lv_solution: str
    lt_implication: str
    lt_solution: str


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
    userId: str
    userAccount: str
    authType: str
    email: str | None = None

    class Config(BaseConfig):
        omit_none = True


@dataclass
class LoginResponseData(DataClassORJSONMixin):
    access_token: str
    token_type: Literal["bearer", "Bearer"]
    refresh_token: str
    expires_in: int
    authorization_code: str
    userInformation: LoginResponseUserInformation
    jti: str = None
    grant_type: Literal["password", "Password"] = None
    scope: Literal["read", "Read"] = None

    class Config(BaseConfig):
        omit_none = True
