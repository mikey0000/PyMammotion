from pyluba.mammotion.commands.messages.navigation import MessageNavigation
from pyluba.mammotion.commands.messages.network import MessageNetwork
from pyluba.mammotion.commands.messages.ota import MessageOta
from pyluba.mammotion.commands.messages.system import MessageSystem
from pyluba.mammotion.commands.messages.video import MessageVideo
from pyluba.proto import dev_net_pb2, luba_msg_pb2, mctrl_nav_pb2, mctrl_sys_pb2
from pyluba.proto.mctrl_sys import RptInfoType


class MammotionCommand(MessageSystem, MessageNavigation, MessageNetwork, MessageOta, MessageVideo):
    """MQTT commands for Luba."""

    def __init__(self, device_name: str) -> None:
        self._device_name = device_name

    def get_device_name(self) -> str:
        """Get device name."""
        return self._device_name

    def get_device_base_info(self):
        net = dev_net_pb2.DevNet(
            todev_devinfo_req=dev_net_pb2.DrvDevInfoReq()
        )
        net.todev_devinfo_req.req_ids.add(
            id=1,
            type=6
        )

        return self.send_order_msg_net(net)

    def read_plan(self, id: int):
        """Read jobs off luba."""
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_planjob_set=mctrl_nav_pb2.NavPlanJobSet(
                    subCmd=id,
                )
            )
        )
        return luba_msg.SerializeToString()

    def send_order_msg_net(self, build) -> bytes:
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_ESP,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_COMM_ESP,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            net=build)

        return luba_msg.SerializeToString()

    def start_work_job(self):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_taskctrl=mctrl_nav_pb2.NavTaskCtrl(
                    type=1,
                    action=1,
                    result=0
                )
            )
        )
        return luba_msg.SerializeToString()

    def pause_execute_task(self):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_taskctrl=mctrl_nav_pb2.NavTaskCtrl(
                    type=1,
                    action=2,
                    result=0
                )
            )
        )

        return luba_msg.SerializeToString()

    def resume_execute_task(self):
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=mctrl_nav_pb2.MctlNav(
                todev_taskctrl=mctrl_nav_pb2.NavTaskCtrl(
                    type=1,
                    action=3,
                    result=0
                )
            )
        )

        return luba_msg.SerializeToString()

    def return_to_dock(self):
        mctrlNav = mctrl_nav_pb2.MctlNav()
        navTaskCtrl = mctrl_nav_pb2.NavTaskCtrl()
        navTaskCtrl.type = 1
        navTaskCtrl.action = 5
        navTaskCtrl.result = 0
        mctrlNav.todev_taskctrl.CopyFrom(navTaskCtrl)

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV
        lubaMsg.sender = luba_msg_pb2.MsgDevice.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.MsgDevice.DEV_MAINCTL
        lubaMsg.msgattr = luba_msg_pb2.MsgAttr.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.nav.CopyFrom(mctrlNav)
        return lubaMsg.SerializeToString()
    
        """BLE commands for Luba."""

    def send_todev_ble_sync(self, sync_type: int) -> bytes:
        commEsp = dev_net_pb2.DevNet(
            todev_ble_sync=sync_type
        )

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_ESP
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.net.CopyFrom(commEsp)
        return lubaMsg.SerializeToString()
