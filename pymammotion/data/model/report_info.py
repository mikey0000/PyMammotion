from dataclasses import asdict, dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class ConnectData(DataClassORJSONMixin):
    connect_type: int = 0
    ble_rssi: int = 0
    wifi_rssi: int = 0


@dataclass
class DeviceData(DataClassORJSONMixin):
    sys_status: int = 0
    charge_state: int = 0
    battery_val: int = 0
    sensor_status: int = 0
    last_status: int = 0
    sys_time_stamp: str = ""


@dataclass
class RTKData(DataClassORJSONMixin):
    status: int = 0
    pos_level: int = 0
    gps_stars: int = 0
    dis_status: str = ""
    co_view_stars: int = 0


@dataclass
class LocationData(DataClassORJSONMixin):
    real_pos_x: int = 0
    real_pos_y: int = 0
    real_toward: int = 0
    pos_type: int = 0
    bol_hash: str = ""


@dataclass
class WorkData(DataClassORJSONMixin):
    path: int = 0
    path_hash: str = ""
    progress: int = 0
    area: int = 0
    bp_info: int = 0
    bp_hash: str = ""
    bp_pos_x: int = 0
    bp_pos_y: int = 0
    real_path_num: str = ""
    path_pos_x: int = 0
    path_pos_y: int = 0
    ub_zone_hash: str = ""
    ub_path_hash: str = ""
    init_cfg_hash: str = ""
    ub_ecode_hash: str = ""
    nav_run_mode: int = 0
    test_mode_status: int = 0
    man_run_speed: int = 0
    nav_edit_status: int = 0
    knife_height: int = 0


@dataclass
class ReportData:
    connect: ConnectData = field(default_factory=ConnectData)
    dev: DeviceData = field(default_factory=DeviceData)
    rtk: RTKData = field(default_factory=RTKData)
    locations: list[LocationData] = field(default_factory=list)
    work: WorkData = field(default_factory=WorkData)

    def from_dict(self, data: dict):
        locations = self.locations
        if data.get("locations") is not None:
            locations = [LocationData.from_dict(loc) for loc in data.get("locations", [])]

        return ReportData(
            connect=ConnectData.from_dict(data.get("connect", asdict(self.connect))),
            dev=DeviceData.from_dict(data.get("dev", asdict(self.dev))),
            rtk=RTKData.from_dict(data.get("rtk", asdict(self.rtk))),
            locations=locations,
            work=WorkData.from_dict(data.get("work", asdict(self.work))),
        )
