"""MowingDevice class to wrap around the betterproto dataclasses."""

from dataclasses import dataclass

import betterproto

from pymammotion.data.model import HashList
from pymammotion.data.model.location import Location
from pymammotion.proto.dev_net import DevNet
from pymammotion.proto.luba_msg import LubaMsg
from pymammotion.proto.luba_mul import SocMul
from pymammotion.proto.mctrl_driver import MctlDriver
from pymammotion.proto.mctrl_nav import MctlNav
from pymammotion.proto.mctrl_ota import MctlOta
from pymammotion.proto.mctrl_pept import MctlPept
from pymammotion.proto.mctrl_sys import MctlSys, SystemUpdateBufMsg


@dataclass
class MowingDevice:
    """Wraps the betterproto dataclasses, so we can bypass the groups for keeping all data."""

    device: LubaMsg
    map: HashList
    location: Location

    def __init__(self):
        self.device = LubaMsg()
        self.map = HashList(area={}, path={}, obstacle={})
        self.location = Location()
        self.err_code_list = []
        self.err_code_list_time = []

    @classmethod
    def from_raw(cls, raw: dict) -> "MowingDevice":
        """Take in raw data to hold in the betterproto dataclass."""
        mowing_device = MowingDevice()
        mowing_device.device = LubaMsg(**raw)
        return mowing_device

    def update_raw(self, raw: dict) -> None:
        """Update the raw LubaMsg data."""
        self.device = LubaMsg(**raw)

    def buffer(self, buffer_list: SystemUpdateBufMsg):
        """Update the device based on which buffer we are reading from."""
        match buffer_list.update_buf_data[0]:
            case 1:
                # 4 speed
                self.location.RTK.latitude = buffer_list.update_buf_data[5]
                self.location.RTK.longitude = buffer_list.update_buf_data[6]
                self.location.dock.latitude = buffer_list.update_buf_data[7]
                self.location.dock.longitude = buffer_list.update_buf_data[8]
                self.location.dock.rotation = buffer_list.update_buf_data[3] + 180
            case 2:
                self.err_code_list.clear()
                self.err_code_list_time.clear()
                self.err_code_list.extend(
                    [
                        buffer_list.update_buf_data[3],
                        buffer_list.update_buf_data[5],
                        buffer_list.update_buf_data[7],
                        buffer_list.update_buf_data[9],
                        buffer_list.update_buf_data[11],
                        buffer_list.update_buf_data[13],
                        buffer_list.update_buf_data[15],
                        buffer_list.update_buf_data[17],
                        buffer_list.update_buf_data[19],
                        buffer_list.update_buf_data[21],
                    ]
                )
                self.err_code_list_time.extend(
                    [
                        buffer_list.update_buf_data[4],
                        buffer_list.update_buf_data[6],
                        buffer_list.update_buf_data[8],
                        buffer_list.update_buf_data[10],
                        buffer_list.update_buf_data[12],
                        buffer_list.update_buf_data[14],
                        buffer_list.update_buf_data[16],
                        buffer_list.update_buf_data[18],
                        buffer_list.update_buf_data[20],
                        buffer_list.update_buf_data[22],
                    ]
                )

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

    net: dict

    def __init__(self, net: DevNet):
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
class SysData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    sys: dict

    def __init__(self, sys: MctlSys):
        if isinstance(sys, dict):
            self.sys = sys
        else:
            self.sys = sys.to_dict()

    def __getattr__(self, item):
        """Intercept call to get sys in dict and return a betterproto dataclass."""
        if self.sys.get(item) is None:
            return MctlSys().__getattribute__(item)

        if not isinstance(self.sys.get(item), dict):
            return self.sys.get(item)

        return MctlSys().__getattribute__(item).from_dict(value=self.sys.get(item))


@dataclass
class NavData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    nav: dict

    def __init__(self, nav: MctlNav):
        if isinstance(nav, dict):
            self.nav = nav
        else:
            self.nav = nav.to_dict()

    def __getattr__(self, item):
        """Intercept call to get nav in dict and return a betterproto dataclass."""
        if self.nav.get(item) is None:
            return MctlNav().__getattribute__(item)

        if not isinstance(self.nav.get(item), dict):
            return self.nav.get(item)

        return MctlNav().__getattribute__(item).from_dict(value=self.nav.get(item))


@dataclass
class DriverData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    driver: dict

    def __init__(self, driver: MctlDriver):
        if isinstance(driver, dict):
            self.driver = driver
        else:
            self.driver = driver.to_dict()

    def __getattr__(self, item):
        """Intercept call to get driver in dict and return a betterproto dataclass."""
        if self.driver.get(item) is None:
            return MctlDriver().__getattribute__(item)

        if not isinstance(self.driver.get(item), dict):
            return self.driver.get(item)

        return MctlDriver().__getattribute__(item).from_dict(value=self.driver.get(item))


@dataclass
class MulData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    mul: dict

    def __init__(self, mul: SocMul):
        if isinstance(mul, dict):
            self.mul = mul
        else:
            self.mul = mul.to_dict()

    def __getattr__(self, item):
        """Intercept call to get mul in dict and return a betterproto dataclass."""
        if self.mul.get(item) is None:
            return SocMul().__getattribute__(item)

        if not isinstance(self.mul.get(item), dict):
            return self.mul.get(item)

        return SocMul().__getattribute__(item).from_dict(value=self.mul.get(item))


@dataclass
class OtaData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    ota: dict

    def __init__(self, ota: MctlOta):
        if isinstance(ota, dict):
            self.ota = ota
        else:
            self.ota = ota.to_dict()

    def __getattr__(self, item):
        """Intercept call to get ota in dict and return a betterproto dataclass."""
        if self.ota.get(item) is None:
            return MctlOta().__getattribute__(item)

        if not isinstance(self.ota.get(item), dict):
            return self.ota.get(item)

        return MctlOta().__getattribute__(item).from_dict(value=self.ota.get(item))


@dataclass
class PeptData:
    """Wrapping class around LubaMsg to return a dataclass from the raw dict."""

    pept: dict

    def __init__(self, pept: MctlPept):
        if isinstance(pept, dict):
            self.pept = pept
        else:
            self.pept = pept.to_dict()

    def __getattr__(self, item):
        """Intercept call to get pept in dict and return a betterproto dataclass."""
        if self.pept.get(item) is None:
            return MctlPept().__getattribute__(item)

        if not isinstance(self.pept.get(item), dict):
            return self.pept.get(item)

        return MctlPept().__getattribute__(item).from_dict(value=self.pept.get(item))
