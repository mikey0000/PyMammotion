# === sendOrderMsg_Driver ===
from pyluba.mammotion.commands.abstract_message import AbstractMessage
from pyluba.proto import luba_msg_pb2, mctrl_driver_pb2


class MessageDriver(AbstractMessage):
    def send_order_msg_driver(self, driver):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MSG_CMD_TYPE_EMBED_DRIVER,
            sender=luba_msg_pb2.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            driver=driver)

        return luba_msg.SerializeToString()

    def set_knife_height(self, height: int):
        print(f"Send knife height height={height}")
        build = mctrl_driver_pb2.MctlDriver(
            todev_knife_hight_set=mctrl_driver_pb2.DrvKnifeHeight(knife_height=height))
        print(f"Send command--Knife motor height setting height={height}")
        return self.send_order_msg_driver(build)

    def set_speed(self, speed: float):
        print(f"{self.get_device_name()} set speed, {speed}")
        build = mctrl_driver_pb2.MctlDriver(
            bidire_speed_read_set=mctrl_driver_pb2.DrvSrSpeed(speed=speed, rw=1))
        print(f"Send command--Speed setting speed={speed}")
        return self.send_order_msg_driver(build)

    def syn_nav_star_point_data(self, sat_system: int):
        build = mctrl_driver_pb2.MctlDriver(
            rtk_sys_mask_query=mctrl_driver_pb2.rtk_sys_mask_query_t(sat_system=sat_system))
        print(
            f"Send command--Navigation satellite frequency point synchronization={sat_system}")
        return self.send_order_msg_driver(build)

    def set_nav_star_point(self, cmd_req: str):
        build = mctrl_driver_pb2.MctlDriver(rtk_cfg_req=mctrl_driver_pb2.rtk_cfg_req_t(
            cmd_req=cmd_req, cmd_length=len(cmd_req) - 1))
        print(
            f"Send command--Navigation satellite frequency point setting={cmd_req}")
        print(
            f"Navigation satellite setting, Send command--Navigation satellite frequency point setting={cmd_req}")
        return self.send_order_msg_driver(build)

    def get_speed(self):
        build = mctrl_driver_pb2.MctlDriver(
            bidire_speed_read_set=mctrl_driver_pb2.DrvSrSpeed(rw=0))
        print("Send command--Get speed value")
        return self.send_order_msg_driver(build)

    def operate_on_device(self, main_ctrl: int, cut_knife_ctrl: int, cut_knife_height: int, max_run_speed: float):
        build = mctrl_driver_pb2.MctlDriver(mow_ctrl_by_hand=mctrl_driver_pb2.DrvMowCtrlByHand(
            main_ctrl=main_ctrl, cut_knife_ctrl=cut_knife_ctrl, cut_knife_height=cut_knife_height, max_run_speed=max_run_speed))
        print(f"Send command--Manual mowing command, main_ctrl:{main_ctrl}, cut_knife_ctrl:{
              cut_knife_ctrl}, cut_knife_height:{cut_knife_height}, max_run_speed:{max_run_speed}")
        return self.send_order_msg_driver(build)

    def send_control(self, linear_speed: int, angular_speed: int):
        print(f"Control command print, linearSpeed={
            linear_speed} // angularSpeed={angular_speed}")
        return self.send_order_msg_driver(mctrl_driver_pb2.MctlDriver(todev_devmotion_ctrl=mctrl_driver_pb2.DrvMotionCtrl(set_linear_speed=linear_speed, set_angular_speed=angular_speed)))
