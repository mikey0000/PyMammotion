# === sendOrderMsg_Driver ===
from abc import ABC
from logging import getLogger
import time

from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import (
    DrvKnifeHeight,
    DrvMotionCtrl,
    DrvMowCtrlByHand,
    DrvSrSpeed,
    LubaMsg,
    MctlDriver,
    MsgAttr,
    MsgCmdType,
    MsgDevice,
    RtkCfgReqT,
    RtkSysMaskQueryT,
)

logger = getLogger(__name__)


class MessageDriver(AbstractMessage, ABC):
    def send_order_msg_driver(self, driver) -> bytes:
        return LubaMsg(
            msgtype=MsgCmdType.EMBED_DRIVER,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.EMBED_DRIVER, MsgDevice.DEV_MAINCTL),
            msgattr=MsgAttr.REQ,
            timestamp=round(time.time() * 1000),
            seqs=1,
            version=1,
            subtype=1,
            driver=driver,
        ).SerializeToString()

    def set_blade_height(self, height: int):
        logger.debug(f"Send knife height height={height}")
        build = MctlDriver(todev_knife_height_set=DrvKnifeHeight(knife_height=height))
        logger.debug(f"Send command--Knife motor height setting height={height}")
        return self.send_order_msg_driver(build)

    def set_speed(self, speed: float):
        logger.debug(f"{self.get_device_name()} set speed, {speed}")
        build = MctlDriver(bidire_speed_read_set=DrvSrSpeed(speed=speed, rw=1))
        logger.debug(f"Send command--Speed setting speed={speed}")
        return self.send_order_msg_driver(build)

    def syn_nav_star_point_data(self, sat_system: int):
        build = MctlDriver(rtk_sys_mask_query=RtkSysMaskQueryT(sat_system=sat_system))
        logger.debug(f"Send command--Navigation satellite frequency point synchronization={sat_system}")
        return self.send_order_msg_driver(build)

    def set_nav_star_point(self, cmd_req: str):
        build = MctlDriver(rtk_cfg_req=RtkCfgReqT(cmd_req=cmd_req, cmd_length=len(cmd_req) - 1))
        logger.debug(f"Send command--Navigation satellite frequency point setting={cmd_req}")
        logger.debug(
            f"Navigation satellite setting, Send command--Navigation satellite frequency point setting={cmd_req}"
        )
        return self.send_order_msg_driver(build)

    def get_speed(self):
        build = MctlDriver(bidire_speed_read_set=DrvSrSpeed(rw=0))
        logger.debug("Send command--Get speed value")
        return self.send_order_msg_driver(build)

    def operate_on_device(
        self,
        main_ctrl: int,
        cut_knife_ctrl: int,
        cut_knife_height: int,
        max_run_speed: float,
    ):
        build = MctlDriver(
            mow_ctrl_by_hand=DrvMowCtrlByHand(
                main_ctrl=main_ctrl,
                cut_knife_ctrl=cut_knife_ctrl,
                cut_knife_height=cut_knife_height,
                max_run_speed=max_run_speed,
            )
        )
        logger.debug(
            f"Send command--Manual mowing command, main_ctrl:{main_ctrl}, cut_knife_ctrl:{cut_knife_ctrl}, "
            f"cut_knife_height:{cut_knife_height}, max_run_speed:{max_run_speed}"
        )

        return self.send_order_msg_driver(build)

    def send_movement(self, linear_speed: int, angular_speed: int) -> bytes:
        logger.debug(f"Control command print, linearSpeed={
        linear_speed} // angularSpeed={angular_speed}")
        return self.send_order_msg_driver(
            MctlDriver(
                todev_devmotion_ctrl=DrvMotionCtrl(set_linear_speed=linear_speed, set_angular_speed=angular_speed)
            )
        )
