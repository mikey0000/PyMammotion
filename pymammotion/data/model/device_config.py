from dataclasses import dataclass

from pymammotion.utility.device_type import DeviceType


@dataclass
class DeviceLimits:
    blade_height_min: int
    blade_height_max: int
    working_speed_min: float
    working_speed_max: float


@dataclass
class OperationSettings:
    """Operation settings for a device."""

    is_mow: bool = True
    is_dump: bool = True
    is_edge: bool = False
    collect_grass_frequency: int = 10
    job_mode: int = 0  # taskMode
    job_version: int = 0
    job_id: int = 0
    speed: float = 0.3
    ultra_wave: int = 2  # touch no touch etc
    channel_mode: int = 0  # line mode is grid single double or single2
    channel_width: int = 25
    rain_tactics: int = 0
    blade_height: int = 0
    path_order: str = ""
    toward: int = 0  # is just angle
    toward_included_angle: int = 0
    toward_mode: int = 0  # angle type relative etc
    border_mode: int = 1  # border laps
    obstacle_laps: int = 1
    start_progress: int = 0


def create_path_order(operation_mode: OperationSettings, device_name: str) -> str:
    i = 8
    bArr = bytearray(8)
    bArr[0] = operation_mode.border_mode
    bArr[1] = operation_mode.obstacle_laps
    bArr[3] = operation_mode.start_progress
    bArr[2] = 0

    if not DeviceType.is_luba1(device_name):
        bArr[4] = 0
        if DeviceType.is_yuka(device_name):
            i = calculate_yuka_mode(operation_mode)
        elif not DeviceType.is_luba_2(device_name):
            i = 0
        bArr[5] = i
        if operation_mode.is_dump:
            b = operation_mode.collect_grass_frequency
        else:
            b = 10
        bArr[6] = b
    if DeviceType.is_luba1(device_name):
        bArr[4] = operation_mode.toward_mode
    return str(bArr, "UTF-8")


def calculate_yuka_mode(operation_mode: OperationSettings) -> int:
    if operation_mode.is_mow and operation_mode.is_dump and operation_mode.is_edge:
        return 14
    if operation_mode.is_mow and operation_mode.is_dump and not operation_mode.is_edge:
        return 12
    if operation_mode.is_mow and not operation_mode.is_dump and operation_mode.is_edge:
        return 10
    if operation_mode.is_mow and not operation_mode.is_dump and not operation_mode.is_edge:
        return 8
    if not operation_mode.is_mow and operation_mode.is_dump and operation_mode.is_edge:
        return 6
    if not operation_mode.is_mow and not operation_mode.is_dump and operation_mode.is_edge:
        return 2
    if not operation_mode.is_mow and operation_mode.is_dump and not operation_mode.is_edge:
        return 4
    return 0
