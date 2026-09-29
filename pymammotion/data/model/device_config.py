from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model.generate_route_information import GenerateRouteInformation
from pymammotion.utility.device_type import DeviceType


@dataclass
class OperationSettings(DataClassORJSONMixin):
    """Operation settings for a device."""

    is_mow: bool = True
    is_dump: bool = True
    is_edge: bool = False
    collect_grass_frequency: int = 10
    job_mode: int = 4  # taskMode
    job_version: int = 0
    job_id: int = 0
    speed: float = 0.3
    ultra_wave: int = 2  # touch no touch etc
    channel_mode: int = 0  # grid or border first
    channel_width: int = 25
    blade_height: int = 0
    path_order: str = ""
    toward: int = 0  # is just angle
    toward_included_angle: int = 90
    toward_mode: int = 0  # angle type relative etc
    border_mode: int = 0
    obstacle_laps: int = 1
    mowing_laps: int = 1  # border laps
    start_progress: int = 0
    auto_change_direction: int = 0  # flip mowing direction between tasks (anti-matting)
    ride_boundary_distance: float = 0.0  # "Edge Coverage" distance; 0.0 is off, any value passes through
    areas: list[int] = field(default_factory=list)


def create_path_order(operation_mode: OperationSettings, device_name: str) -> str:
    """Encode the operation settings into the 8-byte ``path_order`` string the device expects."""
    # TODO add scheduling logic from getReserved() WorkSettingViewModel.java
    bArr = bytearray(8)
    bArr[0] = operation_mode.border_mode
    bArr[1] = operation_mode.obstacle_laps
    bArr[3] = int(operation_mode.start_progress)
    bArr[2] = 0  # plan enable flag, 0 = enabled
    bArr[5] = 0
    if not DeviceType.is_luba1(device_name):
        bArr[4] = 0
        if (
            DeviceType.is_yuka(device_name)
            and not DeviceType.is_yuka_mini(device_name)
            and not DeviceType.is_yuka_ml(device_name)
        ):
            bArr[5] = calculate_yuka_mode(operation_mode)
        else:
            bArr[5] = 8 if DeviceType.is_luba_pro(device_name) else 0

        bArr[6] = int(operation_mode.collect_grass_frequency) if operation_mode.is_dump else 10
    if DeviceType.is_luba1(device_name):
        bArr[4] = operation_mode.toward_mode
    return bArr.decode()


def build_route_information(
    device_name: str, device: object, operation_settings: OperationSettings
) -> GenerateRouteInformation:
    """Build the route a plan or modify sends, gated on the model and on *device*'s own state.

    *device* is normally a ``MowerDevice``; ``None`` or any other object is read as having no
    collector or firmware.  Mutates *operation_settings*: ``is_dump`` is cleared without a
    collector and a Yuka's ``blade_height`` is forced to -10.
    """
    dev = getattr(getattr(device, "report_data", None), "dev", None)
    if dev and dev.collector_status.collector_installation_status == 0:
        operation_settings.is_dump = False

    if DeviceType.is_yuka(device_name):
        operation_settings.blade_height = -10

    route_information = GenerateRouteInformation(
        one_hashs=list(operation_settings.areas),
        speed=operation_settings.speed,
        ultra_wave=operation_settings.ultra_wave,
        toward=operation_settings.toward,
        toward_included_angle=operation_settings.toward_included_angle if operation_settings.channel_mode == 1 else 0,
        toward_mode=operation_settings.toward_mode,
        blade_height=operation_settings.blade_height,
        channel_mode=operation_settings.channel_mode,
        channel_width=operation_settings.channel_width,
        job_mode=operation_settings.job_mode,
        edge_mode=operation_settings.mowing_laps,
        path_order=create_path_order(operation_settings, device_name),
        obstacle_laps=operation_settings.obstacle_laps,
        auto_change_direction=operation_settings.auto_change_direction,
        ride_boundary_distance=operation_settings.ride_boundary_distance,
    )

    if DeviceType.is_luba1(device_name):
        route_information.toward_mode = 0
        route_information.toward_included_angle = 0
    firmware = getattr(getattr(device, "device_firmwares", None), "device_version", "") or ""
    if not DeviceType.supports_auto_change_direction(device_name, firmware):
        # The app gates this row on a capability list and firmware; match it.
        route_information.auto_change_direction = 0
    route_information.ride_boundary_distance = DeviceType.ride_boundary_distance_to_send(
        device_name, route_information.edge_mode, route_information.ride_boundary_distance
    )
    return route_information


def calculate_yuka_mode(operation_mode: OperationSettings) -> int:
    """Map the mow/dump/edge toggles onto the single Yuka job-mode code."""
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
