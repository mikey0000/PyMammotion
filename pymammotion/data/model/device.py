"""MowingDevice class to wrap around the betterproto dataclasses."""

from dataclasses import dataclass

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
