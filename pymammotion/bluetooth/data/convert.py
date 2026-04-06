import logging

from google.protobuf.message import DecodeError

from pymammotion.proto import luba_msg_pb2

_logger = logging.getLogger(__name__)


def parse_custom_data(data: bytes):
    """Convert data into protobuf message."""
    luba_msg = luba_msg_pb2.LubaMsg()
    try:
        luba_msg.ParseFromString(data)
        return luba_msg

    except DecodeError as err:
        _logger.debug("Failed to decode protobuf message: %s", err)


def store_sys_data(sys) -> None:
    if sys.HasField("systemTardStateTunnel"):
        tard_state_data_list = sys.systemTardStateTunnel.tard_state_data
        longValue8 = tard_state_data_list[0]
        longValue9 = tard_state_data_list[1]
        _logger.debug("Device status report, deviceState: %s, deviceName: Luba...", longValue8)
        chargeStateTemp = longValue9
        longValue10 = tard_state_data_list[6]
        longValue11 = tard_state_data_list[7]
