
import esp_driver_pb2
import luba_msg_pb2

commEsp = esp_driver_pb2.CommEsp()

reqIdReq = commEsp.todev_devinfo_req.req_ids.add()
reqIdReq.id = 1
reqIdReq.type = 6
print(reqIdReq)
commEsp.todev_devinfo_req.req_ids
# commEsp.DrvDevInfoReq = infoReq
# drvDevInfoReq.addReqIds(drvDevInfoReqId);
# EspDriver.DrvDevInfoReq devInfoReq = drvDevInfoReq.build();
lubaMsg = luba_msg_pb2.LubaMsg()
lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_ESP
lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
lubaMsg.rcver = luba_msg_pb2.DEV_COMM_ESP
lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_REQ
lubaMsg.seqs = 1
lubaMsg.version = 1
lubaMsg.subtype = 1
lubaMsg.esp.CopyFrom(commEsp)
print(lubaMsg)
bytes = lubaMsg.SerializeToString()
