# === sendOrderMsg_Nav ===
from pyluba.proto import luba_msg_pb2, mctrl_nav_pb2


def send_order_msg_nav(self, build):
    luba_msg = luba_msg_pb2.LubaMsg(
        msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_NAV,
        sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
        rcver=luba_msg_pb2.MsgDevice.DEV_MAINCTL,
        msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
        seqs=1,
        version=1,
        subtype=1,
        net=build)

    return luba_msg.SerializeToString()


def allpowerfull_rw_adapter_x3(self, id: int, context: int, rw: int) -> None:
    build = mctrl_nav_pb2.MctlNav(
        nav_sys_param_cmd=mctrl_nav_pb2.nav_sys_param_msg(
            id=id, context=context, rw=rw
        )
    )
    print(
        f"Send command--9 general read and write command id={id}, context={context}, rw={rw}")
    return self.send_order_msg_nav(build)
