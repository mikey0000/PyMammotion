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
