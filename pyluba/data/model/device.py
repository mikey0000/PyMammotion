from dataclasses import dataclass

from pyluba.proto.dev_net import DevNet
from pyluba.proto.luba_msg import LubaMsg
from pyluba.proto.mctrl_nav import MctlNav
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
        return DevNetDevice(net=self.device.net)

    @property
    def sys(self):
        """Will return a wrapped betterproto of sys."""
        return SysDevice(sys=self.device.sys)

    @property
    def nav(self):
        """Will return a wrapped betterproto of nav."""
        return NavDevice(nav=self.device.nav)


@dataclass
class DevNetDevice:
    net: DevNet

    def __getattr__(self, item):
        if (not isinstance(self.net[item], dict)):
            return self.net[item]

        return DevNet().__getattribute__(item).from_dict(value=self.net[item])


@dataclass
class SysDevice:
    sys: MctlSys

    def __getattr__(self, item):
        if (not isinstance(self.sys[item], dict)):
            return self.sys[item]

        return MctlSys().__getattribute__(item).from_dict(value=self.sys[item])


@dataclass
class NavDevice:
    nav: MctlNav

    def __getattr__(self, item):
        if (not isinstance(self.nav[item], dict)):
            return self.nav[item]

        return MctlNav().__getattribute__(item).from_dict(value=self.nav[item])
