from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Any

import betterproto2

from pymammotion.aliyun.model.dev_by_account_response import Device
from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.raw_data import RawMowerData
from pymammotion.data.mower_state_manager import MowerStateManager
from pymammotion.proto import LubaMsg

_LOGGER = logging.getLogger(__name__)


class MammotionBaseDevice(ABC):
    """Base class for Mammotion devices."""

    def __init__(self, state_manager: MowerStateManager, cloud_device: Device) -> None:
        """Initialize MammotionBaseDevice."""
        self.loop = asyncio.get_event_loop()
        self._state_manager = state_manager
        self._raw_data = dict()
        self._raw_mower_data: RawMowerData = RawMowerData()
        self._notify_future: asyncio.Future[bytes] | None = None
        self._cloud_device = cloud_device

    def _update_raw_data(self, data: bytes) -> None:
        """Update raw and model data from notifications."""
        tmp_msg = LubaMsg().parse(data)
        res = betterproto2.which_one_of(tmp_msg, "LubaSubMsg")
        match res[0]:
            case "nav":
                self._update_nav_data(tmp_msg)
            case "sys":
                self._update_sys_data(tmp_msg)
            case "driver":
                self._update_driver_data(tmp_msg)
            case "net":
                self._update_net_data(tmp_msg)
            case "mul":
                self._update_mul_data(tmp_msg)
            case "ota":
                self._update_ota_data(tmp_msg)

        self._raw_mower_data.update_raw(self._raw_data)

    def _update_nav_data(self, tmp_msg) -> None:
        """Update navigation data."""
        nav_sub_msg = betterproto2.which_one_of(tmp_msg.nav, "SubNavMsg")
        if nav_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", nav_sub_msg[0])
            return
        nav = self._raw_data.get("nav", {})
        if isinstance(nav_sub_msg[1], int):
            nav[nav_sub_msg[0]] = nav_sub_msg[1]
        else:
            nav[nav_sub_msg[0]] = nav_sub_msg[1].to_dict(casing=betterproto2.Casing.SNAKE)
        self._raw_data["nav"] = nav

    def _update_sys_data(self, tmp_msg: LubaMsg) -> None:
        """Update system data."""
        sys_sub_msg = betterproto2.which_one_of(tmp_msg.sys, "SubSysMsg")
        if sys_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", sys_sub_msg[0])
            return
        sys = self._raw_data.get("sys", {})
        sys[sys_sub_msg[0]] = sys_sub_msg[1].to_dict(casing=betterproto2.Casing.SNAKE)
        self._raw_data["sys"] = sys

    def _update_driver_data(self, tmp_msg: LubaMsg) -> None:
        """Update driver data."""
        drv_sub_msg = betterproto2.which_one_of(tmp_msg.driver, "SubDrvMsg")
        if drv_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", drv_sub_msg[0])
            return
        drv = self._raw_data.get("driver", {})
        drv[drv_sub_msg[0]] = drv_sub_msg[1].to_dict(casing=betterproto2.Casing.SNAKE)
        self._raw_data["driver"] = drv

    def _update_net_data(self, tmp_msg: LubaMsg) -> None:
        """Update network data."""
        net_sub_msg = betterproto2.which_one_of(tmp_msg.net, "NetSubType")
        if net_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", net_sub_msg[0])
            return
        net = self._raw_data.get("net", {})
        if isinstance(net_sub_msg[1], int):
            net[net_sub_msg[0]] = net_sub_msg[1]
        else:
            net[net_sub_msg[0]] = net_sub_msg[1].to_dict(casing=betterproto2.Casing.SNAKE)
        self._raw_data["net"] = net

    def _update_mul_data(self, tmp_msg: LubaMsg) -> None:
        """Update mul data."""
        mul_sub_msg = betterproto2.which_one_of(tmp_msg.mul, "SubMul")
        if mul_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", mul_sub_msg[0])
            return
        mul = self._raw_data.get("mul", {})
        mul[mul_sub_msg[0]] = mul_sub_msg[1].to_dict(casing=betterproto2.Casing.SNAKE)
        self._raw_data["mul"] = mul

    def _update_ota_data(self, tmp_msg: LubaMsg) -> None:
        """Update OTA data."""
        ota_sub_msg = betterproto2.which_one_of(tmp_msg.ota, "SubOtaMsg")
        if ota_sub_msg[1] is None:
            _LOGGER.debug("Sub message was NoneType %s", ota_sub_msg[0])
            return
        ota = self._raw_data.get("ota", {})
        ota[ota_sub_msg[0]] = ota_sub_msg[1].to_dict(casing=betterproto2.Casing.SNAKE)
        self._raw_data["ota"] = ota

    @property
    def raw_data(self) -> dict[str, Any]:
        """Get the raw data of the device."""
        return self._raw_data

    @property
    def mower(self) -> MowingDevice:
        """Get the LubaMsg of the device."""
        return self._state_manager.get_device()

    @abstractmethod
    async def queue_command(self, key: str, **kwargs: Any) -> None:
        """Queue commands to mower."""

    @abstractmethod
    async def _ble_sync(self) -> None:
        """Send ble sync command every 3 seconds or sooner."""

    @abstractmethod
    def stop(self) -> None:
        """Stop everything ready for destroying."""

    async def async_read_settings(self) -> None:
        """Read settings from device."""
        # no cutting in rain nav_sys_param_cmd (id 3 context 1/0)
        await self.queue_command("read_write_device", rw_id=3, context=1, rw=0)
        # ??
        await self.queue_command("read_write_device", rw_id=4, context=1, rw=0)
        # turning mode nav_sys_param_cmd (id 6, context 1/0)
        await self.queue_command("read_write_device", rw_id=6, context=1, rw=0)
        # traversal mode
        await self.queue_command("read_write_device", rw_id=7, context=1, rw=0)

        await self.queue_command("read_and_set_sidelight", is_sidelight=True, operate=1)

        await self.queue_command("read_and_set_rtk_pairing_code", op=1, cfg="")

    async def async_get_errors(self) -> None:
        """Error codes."""
        await self.queue_command("read_write_device", rw_id=5, rw=1, context=2)
        await self.queue_command("read_write_device", rw_id=5, rw=1, context=3)

    async def command(self, key: str, **kwargs: Any) -> None:
        """Send a command to the device."""
        await self.queue_command(key, **kwargs)

    @property
    def state_manager(self) -> MowerStateManager:
        return self._state_manager
