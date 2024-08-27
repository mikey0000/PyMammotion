from dataclasses import asdict, dataclass, field


@dataclass
class ConnectData:
    connect_type: int = 0
    ble_rssi: int = 0
    wifi_rssi: int = 0

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            connect_type=data.get("connect_type", 0),
            ble_rssi=data.get("ble_rssi", 0),
            wifi_rssi=data.get("wifi_rssi", 0),
        )


@dataclass
class DeviceData:
    sys_status: int = 0
    charge_state: int = 0
    battery_val: int = 0
    sensor_status: int = 0
    last_status: int = 0
    sys_time_stamp: str = ""

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            sys_status=data.get("sys_status", 0),
            charge_state=data.get("charge_state", 0),
            battery_val=data.get("battery_val", 0),
            sensor_status=data.get("sensor_status", 0),
            last_status=data.get("last_status", 0),
            sys_time_stamp=data.get("sys_time_stamp", ""),
        )


@dataclass
class RTKData:
    status: int = 0
    pos_level: int = 0
    gps_stars: int = 0
    dis_status: str = ""
    co_view_stars: int = 0

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            status=data.get("status", 0),
            pos_level=data.get("pos_level", 0),
            gps_stars=data.get("gps_stars", 0),
            dis_status=data.get("dis_status", ""),
            co_view_stars=data.get("co_view_stars", 0),
        )


@dataclass
class LocationData:
    real_pos_x: int = 0
    real_pos_y: int = 0
    real_toward: int = 0
    pos_type: int = 0
    bol_hash: str = ""

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            real_pos_x=data.get("real_pos_x", 0),
            real_pos_y=data.get("real_pos_y", 0),
            real_toward=data.get("real_toward", 0),
            pos_type=data.get("pos_type", 0),
            bol_hash=data.get("bol_hash", ""),
        )


@dataclass
class WorkData:
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

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            path=data.get("path", 0),
            path_hash=data.get("path_hash", ""),
            progress=data.get("progress", 0),
            area=data.get("area", 0),
            bp_info=data.get("bp_info", 0),
            bp_hash=data.get("bp_hash", ""),
            bp_pos_x=data.get("bp_pos_x", 0),
            bp_pos_y=data.get("bp_pos_y", 0),
            real_path_num=data.get("real_path_num", ""),
            path_pos_x=data.get("path_pos_x", 0),
            path_pos_y=data.get("path_pos_y", 0),
            ub_zone_hash=data.get("ub_zone_hash", ""),
            ub_path_hash=data.get("ub_path_hash", ""),
            init_cfg_hash=data.get("init_cfg_hash", ""),
            ub_ecode_hash=data.get("ub_ecode_hash", ""),
            nav_run_mode=data.get("nav_run_mode", 0),
            test_mode_status=data.get("test_mode_status", 0),
            man_run_speed=data.get("man_run_speed", 0),
            nav_edit_status=data.get("nav_edit_status", 0),
            knife_height=data.get("knife_height", 0),
        )


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
