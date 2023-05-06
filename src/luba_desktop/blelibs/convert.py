from typing import Dict

from google.protobuf.message import DecodeError
from luba_desktop.proto import mctrl_driver_pb2, luba_msg_pb2, esp_driver_pb2, mctrl_nav_pb2, mctrl_sys_pb2
from luba_desktop.data.model import HashList

# until we have a proper store or send messages somewhere
device_charge_map: Dict[str, int] = {}
deviceRtkStatusMap: Dict[str, int] = {}
deviceSelfCheckFlagMap: Dict[str, bool] = {}
devicePileMap: Dict[str, int] = {}
devicePosTypeMap: Dict[str, int] = {}
device_state_map: Dict[str, int] = {}
deviceBreakPointMap: Dict[str, int] = {}
chargeStateTemp = -1

def parseCustomData(data: bytearray):
    # pass
    # print(data)
    # setReceiveDeviceData
    
    
    lubaMsg = luba_msg_pb2.LubaMsg()
    try:
        lubaMsg.ParseFromString(data)
        print(lubaMsg)
        
        toappGetHashAck = lubaMsg.nav.toapp_get_commondata_ack
        print(toappGetHashAck.Hash)
        
        if(lubaMsg.sys):
            store_sys_data(lubaMsg.sys)
        elif(lubaMsg.esp):
            store_esp_data(lubaMsg.esp)
        elif(lubaMsg.nav):
            store_nav_data(lubaMsg.nav)
        elif(lubaMsg.driver):
            pass
        else:
            pass
        
    except DecodeError as err:
        print(err)
        
        
def store_sys_data(sys):
    if(sys.HasField("system_tard_state_tunnel")):
        tardStateDataList = sys.system_tard_state_tunnel.tard_state_data
        longValue8 = tardStateDataList[0]
        longValue9 = tardStateDataList[1]
        print("Device status report,deviceState:", longValue8, ",deviceName:", "Luba...")
        chargeStateTemp = longValue9
        longValue10 = tardStateDataList[6]
        longValue11 = tardStateDataList[7]

        #device_state_map        

        
        
def store_nav_data(nav):
    if(nav.toappGethashAck):    
        toappGetHashAck = nav.toapp_get_commondata_ack
        hashList = HashList()
        print(toappGetHashAck.dataLen)
        # hashList.pver toappGethashAck.pver
        # int subCmd2 = toappGethashAck.getSubCmd();
        # int totalFrame3 = toappGethashAck.getTotalFrame();
        # int currentFrame3 = toappGethashAck.getCurrentFrame();
        # long dataHash3 = toappGethashAck.getDataHash();
        # List<Long> dataCoupleList = toappGethashAck.getDataCoupleList();
        # HashListBean hashListBean = new HashListBean();
        # hashListBean.setPver(pver3);
        # hashListBean.setSubCmd(subCmd2);
        # hashListBean.setCurrentFrame(currentFrame3);
        # hashListBean.setTotalFrame(totalFrame3);
        # hashListBean.setDataHash(dataHash3);
        # hashListBean.setPath(dataCoupleList);
    
def store_esp_data(esp):
    if(esp.toapp_wifi_iot_status):
        iot_status = esp.toapp_wifi_iot_status
        print(iot_status.devicename)