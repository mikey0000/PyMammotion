from typing import Dict

from google.protobuf.message import DecodeError

from pyluba.data.model import HashList, RegionData
from pyluba.proto import luba_msg_pb2

# until we have a proper store or send messages somewhere
device_charge_map: Dict[str, int] = {}
deviceRtkStatusMap: Dict[str, int] = {}
deviceSelfCheckFlagMap: Dict[str, bool] = {}
devicePileMap: Dict[str, int] = {}
devicePosTypeMap: Dict[str, int] = {}
device_state_map: Dict[str, int] = {}
deviceBreakPointMap: Dict[str, int] = {}
chargeStateTemp = -1


'''Parse data packets back into their protobuf types.

TODO allow for registering events to individual messages
as trying to register for all would be a mess
'''
def parse_custom_data(data: bytes):
    luba_msg = luba_msg_pb2.LubaMsg()
    try:
        luba_msg.ParseFromString(data)
        # print(luba_msg)
        # luba_message = luba_msg_p2p.LubaMsg(net=luba_msg.net)

        # print(luba_message)

        # toappGetHashAck = luba_msg.nav.toapp_get_commondata_ack
        # print(toappGetHashAck.Hash)

        if luba_msg.HasField('sys'):
            store_sys_data(luba_msg.sys)
        elif luba_msg.HasField('net'):
            if luba_msg.net.HasField('todev_ble_sync'):
                pass
                # await asyncio.sleep(1.5)
                # await bleClient.send_todev_ble_sync(1)


            store_net_data(luba_msg.net)
        elif luba_msg.HasField('nav'):
            store_nav_data(luba_msg.nav)
        elif luba_msg.HasField('driver'):
            pass
        else:
            pass

        return luba_msg

    except DecodeError as err:
        print(err)


def store_sys_data(sys):
    if(sys.HasField("systemTardStateTunnel")):
        tard_state_data_list = sys.systemTardStateTunnel.tard_state_data
        longValue8 = tard_state_data_list[0]
        longValue9 = tard_state_data_list[1]
        print("Device status report,deviceState:", longValue8, ",deviceName:", "Luba...")
        chargeStateTemp = longValue9
        longValue10 = tard_state_data_list[6]
        longValue11 = tard_state_data_list[7]

        #device_state_map
    if sys.HasField("systemRapidStateTunnel"):
        rapid_state_data_list = sys.systemRapidStateTunnel.rapid_state_data
        print(rapid_state_data_list)

    if sys.HasField("toapp_batinfo"):
        battery_info = sys.toapp_batinfo
        print(battery_info)


def store_nav_data(nav):
    if(nav.HasField('toapp_get_commondata_ack')):
        """has data about paths and zones"""
        toapp_get_commondata_ack = nav.toapp_get_commondata_ack
        region_data = RegionData()
        region_data.result = toapp_get_commondata_ack.result
        region_data.action = toapp_get_commondata_ack.action
        region_data.type = toapp_get_commondata_ack.type
        region_data.Hash = toapp_get_commondata_ack.Hash
        region_data.pHashA = int(toapp_get_commondata_ack.paternalHashA)
        region_data.pHashB = int(toapp_get_commondata_ack.paternalHashB)
        region_data.path = toapp_get_commondata_ack.dataCouple
        region_data.subCmd = toapp_get_commondata_ack.subCmd
        region_data.totalFrame = toapp_get_commondata_ack.totalFrame
        region_data.currentFrame = toapp_get_commondata_ack.currentFrame
        region_data.dataHash = toapp_get_commondata_ack.dataHash
        region_data.dataLen = toapp_get_commondata_ack.dataLen
        region_data.pver = toapp_get_commondata_ack.pver
        print(region_data)


    if(nav.HasField('toapp_gethash_ack')):
        toapp_gethash_ack = nav.toapp_gethash_ack
        hash_list = HashList()

        data_couple_list = toapp_gethash_ack.dataCouple
        hash_list.pver = toapp_gethash_ack.pver
        hash_list.subCmd = toapp_gethash_ack.subCmd
        hash_list.currentFrame = toapp_gethash_ack.currentFrame
        hash_list.totalFrame = toapp_gethash_ack.totalFrame
        hash_list.dataHash = int(toapp_gethash_ack.dataHash)
        hash_list.path = data_couple_list
        print(hash_list)
        # use callback to provide hash list

def store_net_data(net):
    if net.toapp_wifi_iot_status:
        iot_status = net.toapp_wifi_iot_status
        print(iot_status.devicename)
    if net.todev_ble_sync:
        pass
        # send event to reply with sync
