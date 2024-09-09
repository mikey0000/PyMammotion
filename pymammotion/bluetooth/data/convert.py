from google.protobuf.message import DecodeError

from pymammotion.proto import luba_msg_pb2


def parse_custom_data(data: bytes):
    """Convert data into protobuf message."""
    luba_msg = luba_msg_pb2.LubaMsg()
    try:
        luba_msg.ParseFromString(data)
        return luba_msg

    except DecodeError as err:
        print(err)


def store_sys_data(sys) -> None:
    if sys.HasField("systemTardStateTunnel"):
        tard_state_data_list = sys.systemTardStateTunnel.tard_state_data
        longValue8 = tard_state_data_list[0]
        longValue9 = tard_state_data_list[1]
        print("Device status report,deviceState:", longValue8, ",deviceName:", "Luba...")
        chargeStateTemp = longValue9
        longValue10 = tard_state_data_list[6]
        longValue11 = tard_state_data_list[7]
