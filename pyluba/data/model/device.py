"""MowingDevice class to wrap around the betterproto dataclasses."""

from dataclasses import dataclass

from pyluba.proto.dev_net import DevNet
from pyluba.proto.luba_msg import LubaMsg
from pyluba.proto.luba_mul import SocMul
from pyluba.proto.mctrl_driver import MctlDriver
from pyluba.proto.mctrl_nav import MctlNav
from pyluba.proto.mctrl_ota import MctlOta
from pyluba.proto.mctrl_pept import MctlPept
from pyluba.proto.mctrl_sys import MctlSys


@dataclass
class MowingDevice:
    """Wraps the betterproto dataclasses so we can bypass the groups for keeping all data."""

    device: LubaMsg

    @classmethod
    def from_raw(cls, raw: dict) -> "MowingDevice":
        """Take in raw data to hold in the betterproto dataclass."""
        return MowingDevice(device=LubaMsg(**raw))

    @property
    def net(self):
        """Will return a wrapped betterproto of net."""
        return DevNetData(net=self.device.net)

    @property
    def sys(self):
        """Will return a wrapped betterproto of sys."""
        return SysData(sys=self.device.sys)

    @property
    def nav(self):
        """Will return a wrapped betterproto of nav."""
        return NavData(nav=self.device.nav)

    @property
    def driver(self):
        """Will return a wrapped betterproto of driver."""
        return DriverData(driver=self.device.driver)

    @property
    def mul(self):
        """Will return a wrapped betterproto of mul."""
        return MulData(mul=self.device.mul)

    @property
    def ota(self):
        """Will return a wrapped betterproto of ota."""
        return OtaData(ota=self.device.ota)

    @property
    def pept(self):
        """Will return a wrapped betterproto of pept."""
        return PeptData(pept=self.device.pept)


@dataclass
class DevNetData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    net: DevNet

    def __getattr__(self, item):
        """Intercept call to get net in dict and return a betterproto dataclass."""
        if not isinstance(self.net[item], dict):
            return self.net[item]

        return DevNet().__getattribute__(item).from_dict(value=self.net[item])


@dataclass
class SysData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    sys: MctlSys

    def __getattr__(self, item):
        """Intercept call to get net in dict and return a betterproto dataclass."""
        if not isinstance(self.sys[item], dict):
            return self.sys[item]

        return MctlSys().__getattribute__(item).from_dict(value=self.sys[item])


@dataclass
class NavData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    nav: MctlNav

    def __getattr__(self, item):
        """Intercept call to get nav in dict and return a betterproto dataclass."""
        if not isinstance(self.nav[item], dict):
            return self.nav[item]

        return MctlNav().__getattribute__(item).from_dict(value=self.nav[item])


@dataclass
class DriverData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    driver: MctlDriver

    def __getattr__(self, item):
        """Intercept call to get driver in dict and return a betterproto dataclass."""
        if not isinstance(self.driver[item], dict):
            return self.driver[item]

        return MctlDriver().__getattribute__(item).from_dict(value=self.driver[item])


@dataclass
class MulData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    mul: SocMul

    def __getattr__(self, item):
        """Intercept call to get mul in dict and return a betterproto dataclass."""
        if not isinstance(self.mul[item], dict):
            return self.mul[item]

        return SocMul().__getattribute__(item).from_dict(value=self.mul[item])


@dataclass
class OtaData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    ota: MctlOta

    def __getattr__(self, item):
        """Intercept call to get ota in dict and return a betterproto dataclass."""
        if not isinstance(self.ota[item], dict):
            return self.ota[item]

        return MctlOta().__getattribute__(item).from_dict(value=self.ota[item])


@dataclass
class PeptData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    pept: MctlPept

    def __getattr__(self, item):
        """Intercept call to get pept in dict and return a betterproto dataclass."""
        if not isinstance(self.pept[item], dict):
            return self.pept[item]

        return MctlPept().__getattribute__(item).from_dict(value=self.pept[item])
