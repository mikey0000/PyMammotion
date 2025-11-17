from dataclasses import dataclass, field
from typing import Annotated, Generic, Literal, TypeVar

from mashumaro import DataClassDictMixin
from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


class UnauthorizedException(Exception):
    pass


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
class SettingVo(DataClassORJSONMixin):
    """Device setting configuration."""

    type: int = 0
    is_switch: Annotated[int, Alias("isSwitch")] = 0


@dataclass
class LocationVo(DataClassORJSONMixin):
    """Device location information."""

    date_time: Annotated[str, Alias("dateTime")] = ""
    date_timestamp: Annotated[int, Alias("dateTimestamp")] = 0
    location: list[float] = field(default_factory=lambda: [0.0, 0.0])


@dataclass
class DeviceInfo:
    """Complete device information."""

    iot_id: Annotated[str, Alias("iotId")] = ""
    device_id: Annotated[str, Alias("deviceId")] = ""
    device_name: Annotated[str, Alias("deviceName")] = ""
    device_type: Annotated[str, Alias("deviceType")] = ""
    series: str = ""
    product_series: Annotated[str, Alias("productSeries")] = ""
    icon_code: Annotated[str, Alias("iconCode")] = ""
    generation: int = 0
    status: int = 0
    is_subscribe: Annotated[int, Alias("isSubscribe")] = 0
    setting_vos: Annotated[list[SettingVo], Alias("settingVos")] = field(default_factory=list)
    active_time: Annotated[str, Alias("activeTime")] = ""
    active_timestamp: Annotated[int, Alias("activeTimestamp")] = 0
    location_vo: Annotated[LocationVo | None, Alias("locationVo")] = None

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class DeviceRecord(DataClassORJSONMixin):
    identity_id: Annotated[str, Alias("identityId")]
    iot_id: Annotated[str, Alias("iotId")]
    product_key: Annotated[str, Alias("productKey")]
    device_name: Annotated[str, Alias("deviceName")]
    owned: int
    status: int
    bind_time: Annotated[int, Alias("bindTime")]
    create_time: Annotated[str, Alias("createTime")]

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class DeviceRecords(DataClassORJSONMixin):
    records: list[DeviceRecord]
    total: int
    size: int
    current: int
    pages: int


@dataclass
class MQTTConnection(DataClassORJSONMixin):
    host: str
    jwt: str
    client_id: Annotated[str, Alias("clientId")]
    username: str


@dataclass
class Response(DataClassORJSONMixin, Generic[DataT]):
    code: int
    msg: str
    request_id: Annotated[str, Alias("requestId")] | None = None
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
class JWTTokenInfo(DataClassORJSONMixin):
    """specifically for newer devices and mqtt"""

    iot: str  # iot domain e.g api-iot-business-eu-dcdn.mammotion.com
    robot: str  # e.g api-robot-eu.mammotion.com


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


@dataclass
class FirmwareVersions(DataClassORJSONMixin):
    firmware_version: Annotated[str, Alias("firmwareVersion")] = ""
    firmware_code: Annotated[str, Alias("firmwareCode")] = ""
    firmware_latest_version: Annotated[str, Alias("firmwareLatestVersion")] = ""
    firmware_type: Annotated[str, Alias("firmwareType")] = ""

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class ProductVersionInfo(DataClassORJSONMixin):
    release_note: Annotated[str, Alias("releaseNote")] = ""
    release_version: Annotated[str, Alias("releaseVersion")] = ""
    data_location: str | None = None

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class CheckDeviceVersion(DataClassORJSONMixin):
    cause_code: Annotated[int, Alias("causeCode")] = 0
    product_version_info_vo: Annotated[ProductVersionInfo | None, Alias("productVersionInfoVo")] = None
    progress: int | None = 0
    upgradeable: bool = False
    device_id: Annotated[str, Alias("deviceId")] = ""
    device_name: Annotated[str | None, Alias("deviceName")] = ""
    current_version: Annotated[str, Alias("currentVersion")] = ""
    isupgrading: bool | None = False
    cause_msg: Annotated[str, Alias("causeMsg")] = ""

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True

    def __eq__(self, other):
        if not isinstance(other, CheckDeviceVersion):
            return NotImplemented

        if self.device_id != other.device_id or self.current_version != other.current_version:
            return False

        if self.product_version_info_vo and other.product_version_info_vo:
            if self.product_version_info_vo.release_version != other.product_version_info_vo.release_version:
                return False
            return True
        elif self.product_version_info_vo is None and other.product_version_info_vo is None:
            return False
        else:
            return True
