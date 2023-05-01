

from google.protobuf.message import DecodeError
from luba_desktop.proto import mctrl_driver_pb2, luba_msg_pb2, esp_driver_pb2, mctrl_nav_pb2, mctrl_sys_pb2

def parseCustomData(data: bytearray):
    # pass
    # print(data)
    # setReceiveDeviceData
    lubaMsg = luba_msg_pb2.LubaMsg()
    try:
        lubaMsg.ParseFromString(data)
        print(lubaMsg)
        
        if(lubaMsg.sys):
            pass
        elif(lubaMsg.esp):
            pass  
        elif(lubaMsg.nav):
            pass  
        elif(lubaMsg.driver):
            pass
        else:
            pass
        
    except DecodeError as err:
        print(err)
        
        
    