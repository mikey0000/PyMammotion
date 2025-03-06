from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.proto import DevNet, LubaMsg, MctlDriver, MctlNav, MctlOta, MctlPept, MctlSys, SocMul


@dataclass
class RawMowerData:
    raw: LubaMsg | None = field(default_factory=LubaMsg)

    @classmethod
    def from_raw(cls, raw: dict) -> "RawMowerData":
        """Take in raw data to hold in the betterproto dataclass."""
        return RawMowerData(raw=LubaMsg(**raw))

    def update_raw(self, raw: dict) -> None:
        """Update the raw LubaMsg data."""
        self.raw = LubaMsg(**raw)

    @property
    def net(self):
        """Will return a wrapped betterproto of net."""
        return DevNetData(net=self.raw.net)

    @property
    def sys(self):
        """Will return a wrapped betterproto of sys."""
        return SysData(sys=self.raw.sys)

    @property
    def nav(self):
        """Will return a wrapped betterproto of nav."""
        return NavData(nav=self.raw.nav)

    @property
    def driver(self):
        """Will return a wrapped betterproto of driver."""
        return DriverData(driver=self.raw.driver)

    @property
    def mul(self):
        """Will return a wrapped betterproto of mul."""
        return MulData(mul=self.raw.mul)

    @property
    def ota(self):
        """Will return a wrapped betterproto of ota."""
        return OtaData(ota=self.raw.ota)

    @property
    def pept(self):
        """Will return a wrapped betterproto of pept."""
        return PeptData(pept=self.raw.pept)


@dataclass
class DevNetData(DataClassORJSONMixin):
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    net: dict

    def __init__(self, net: DevNet) -> None:
        if isinstance(net, dict):
            self.net = net
        else:
            self.net = net.to_dict()

    def __getattr__(self, item):
        """Intercept call to get net in dict and return a betterproto dataclass."""
        if self.net.get(item) is None:
            return DevNet().__getattribute__(item)

        if not isinstance(self.net.get(item), dict):
            return self.net.get(item)

        return DevNet().__getattribute__(item).from_dict(value=self.net.get(item))


@dataclass
class SysData(DataClassORJSONMixin):
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    sys: dict

    def __init__(self, sys: MctlSys) -> None:
        if isinstance(sys, dict):
            self.sys = sys
        else:
            self.sys = sys.to_dict()

    def __getattr__(self, item: str):
        """Intercept call to get sys in dict and return a betterproto dataclass."""
        if self.sys.get(item) is None:
            return MctlSys().__getattribute__(item)

        if not isinstance(self.sys.get(item), dict):
            return self.sys.get(item)

        return MctlSys().__getattribute__(item).from_dict(value=self.sys.get(item))


@dataclass
class NavData(DataClassORJSONMixin):
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    nav: dict

    def __init__(self, nav: MctlNav) -> None:
        if isinstance(nav, dict):
            self.nav = nav
        else:
            self.nav = nav.to_dict()

    def __getattr__(self, item: str):
        """Intercept call to get nav in dict and return a betterproto dataclass."""
        if self.nav.get(item) is None:
            return MctlNav().__getattribute__(item)

        if not isinstance(self.nav.get(item), dict):
            return self.nav.get(item)

        return MctlNav().__getattribute__(item).from_dict(value=self.nav.get(item))


@dataclass
class DriverData(DataClassORJSONMixin):
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    driver: dict

    def __init__(self, driver: MctlDriver) -> None:
        if isinstance(driver, dict):
            self.driver = driver
        else:
            self.driver = driver.to_dict()

    def __getattr__(self, item: str):
        """Intercept call to get driver in dict and return a betterproto dataclass."""
        if self.driver.get(item) is None:
            return MctlDriver().__getattribute__(item)

        if not isinstance(self.driver.get(item), dict):
            return self.driver.get(item)

        return MctlDriver().__getattribute__(item).from_dict(value=self.driver.get(item))


@dataclass
class MulData(DataClassORJSONMixin):
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    mul: dict

    def __init__(self, mul: SocMul) -> None:
        if isinstance(mul, dict):
            self.mul = mul
        else:
            self.mul = mul.to_dict()

    def __getattr__(self, item: str):
        """Intercept call to get mul in dict and return a betterproto dataclass."""
        if self.mul.get(item) is None:
            return SocMul().__getattribute__(item)

        if not isinstance(self.mul.get(item), dict):
            return self.mul.get(item)

        return SocMul().__getattribute__(item).from_dict(value=self.mul.get(item))


@dataclass
class OtaData(DataClassORJSONMixin):
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    ota: dict

    def __init__(self, ota: MctlOta) -> None:
        if isinstance(ota, dict):
            self.ota = ota
        else:
            self.ota = ota.to_dict()

    def __getattr__(self, item: str):
        """Intercept call to get ota in dict and return a betterproto dataclass."""
        if self.ota.get(item) is None:
            return MctlOta().__getattribute__(item)

        if not isinstance(self.ota.get(item), dict):
            return self.ota.get(item)

        return MctlOta().__getattribute__(item).from_dict(value=self.ota.get(item))


@dataclass
class PeptData(DataClassORJSONMixin):
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    pept: dict

    def __init__(self, pept: MctlPept) -> None:
        if isinstance(pept, dict):
            self.pept = pept
        else:
            self.pept = pept.to_dict()

    def __getattr__(self, item: str):
        """Intercept call to get pept in dict and return a betterproto dataclass."""
        if self.pept.get(item) is None:
            return MctlPept().__getattribute__(item)

        if not isinstance(self.pept.get(item), dict):
            return self.pept.get(item)

        return MctlPept().__getattribute__(item).from_dict(value=self.pept.get(item))
