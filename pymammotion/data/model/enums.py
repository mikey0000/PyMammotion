from enum import Enum, IntEnum


class ConnectionPreference(Enum):
    """Enum for connection preference."""

    ANY = 0
    WIFI = 1
    BLUETOOTH = 2
    PREFER_WIFI = 3
    PREFER_BLUETOOTH = 4


class PositionMode(Enum):
    FIX = 0
    SINGLE = 1
    FLOAT = 2
    NONE = 3
    UNKNOWN = 4

    @staticmethod
    def from_value(value: int) -> "PositionMode":
        """Return the PositionMode enum member corresponding to the given integer value."""
        if value == 0:
            return PositionMode.FIX
        elif value == 1:
            return PositionMode.SINGLE
        elif value == 2:
            return PositionMode.FLOAT
        elif value == 3:
            return PositionMode.NONE
        else:
            return PositionMode.UNKNOWN

    def __str__(self) -> str:
        if self == PositionMode.FIX:
            return "Fix"
        elif self == PositionMode.SINGLE:
            return "Single"
        elif self == PositionMode.FLOAT:
            return "Float"
        elif self == PositionMode.NONE:
            return "None"
        else:
            return "-"


class RTKStatus(Enum):
    NONE = 0
    SINGLE = 1
    FIX = 4
    FLOAT = 5
    UNKNOWN = 6

    @staticmethod
    def from_value(value: int) -> "RTKStatus":
        """Return the RTKStatus enum member corresponding to the given integer value."""
        if value == 0:
            return RTKStatus.NONE
        elif value == 1 or value == 2:
            return RTKStatus.SINGLE
        elif value == 4:
            return RTKStatus.FIX
        elif value == 5:
            return RTKStatus.FLOAT
        else:
            return RTKStatus.UNKNOWN

    def __str__(self) -> str:
        if self == RTKStatus.NONE:
            return "None"
        elif self == RTKStatus.SINGLE:
            return "Single"
        elif self == RTKStatus.FIX:
            return "Fix"
        elif self == RTKStatus.FLOAT:
            return "Float"
        else:
            return "Unknown"


class RtkSwitchMode(IntEnum):
    """RTK correction delivery channel.

    Source: proto rtk_used_type enum / APK NetRtkChannelBean.rtkSwitch.
    Stored in rpt_rtk.mqtt_rtk_info.rtk_switch.
    """

    LORA = 0  # LoRa radio link directly to a paired base station
    INTERNET = 1  # Internet NTRIP stream
    NRTK = 2  # Network RTK (virtual reference station)


class SimCardStatus(IntEnum):
    """SIM card state.

    Source: proto sim_card_sta enum / APK Net4GRspBean.simCardSta.
    """

    SIM_NONE = 0  # No SIM slot / module absent
    SIM_NO_CARD = 1  # SIM slot present but no card inserted
    SIM_INVALID = 2  # Card inserted but not readable
    SIM_INPUT_PIN = 3  # Waiting for PIN entry
    SIM_INPUT_PUK = 4  # Waiting for PUK entry (PIN locked)
    SIM_OK = 5  # SIM ready and registered


class MnetLinkType(IntEnum):
    """Cellular network generation.

    Source: proto mnet_link_type enum.
    """

    NONE = 0
    LINK_2G = 1
    LINK_3G = 2
    LINK_4G = 3
    LINK_5G = 4


class FuseLocalizationStatus(IntEnum):
    """IMU + vision fusion localisation state.

    Extracted from rapid_state_data[16] bits [8:15].
    Source: APK DeviceConstant.java fused localisation constants.
    """

    NO_POSE = 0  # No localisation
    RTK_FIXED = 1  # Pure RTK fixed — normal operation
    RTK_EXTENDED_VISION = 2  # RTK extended by visual odometry (kRTkExtended)
    VISION_EXTENDED = 3  # Vision-only extension active
    VISION_EXTENDED_FAILED = 4  # Vision extension attempted but failed


class WorkInterruptType(IntEnum):
    """Work task interrupt / stop reason.

    Source: APK DeviceConstant.java TaskInterruptType interface.
    Sent in WorkReportInfoAck.interrupt_flag (stored as int).
    """

    INITIAL = -1
    NONE = 0
    PAUSING_BY_MANUAL = 1
    CHASSIS_LOCKED_BY_MANUAL = 2
    BLADE_STUCK_BY_MANUAL = 3
    STUCK_BY_MANUAL = 4
    OUT_OF_BOUNDARY_BY_MANUAL = 5
    CHARGE_OR_DOCK_BY_MANUAL = 6
    BAD_LOCALIZATION_AUTO = 7
    LOW_BATTERY_AUTO = 8
    BUMPER_DISCONNECT = 9
    PAUSE_LOW_BATTERY_AUTO = 10
    ASSIGNED_PERCENTAGE_COMPLETE = 11
    FORECAST_POWER_OFF_MANUALLY = 12
    FORECAST_POSITIONING_AUTO = 13
    FORECAST_LOW_BATTERY_MANUALLY = 14
    FORECAST_PAUSING_MANUALLY = 15
    FORECAST_POSITIONING_AUTO_16 = 16
    FORECAST_CONTINUE_TIME = 18
    FORECAST_CONTINUE_TIME_BY_MANUAL = 19
    BLADE_STUCK_BY_MANUAL_NEW = 20
    STUCK_BY_MANUAL_NEW = 21


class IotConnectionStatus(IntEnum):
    """IoT cloud connection state.

    Source: proto rpt_connect_status.iot_con_status field.
    """

    OFFLINE = 0
    ONLINE = 1
    RESET = 2
