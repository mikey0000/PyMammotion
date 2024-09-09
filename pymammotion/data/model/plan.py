from typing import List


class Plan:
    def __init__(self) -> None:
        self.pver: int = 0
        self.sub_cmd: int = 0
        self.area: int = 0
        self.work_time: int = 0
        self.version: str = ""
        self.id: str = ""
        self.user_id: str = ""
        self.device_id: str = ""
        self.plan_id: str = ""
        self.task_id: str = ""
        self.job_id: str = ""
        self.start_time: str = ""
        self.end_time: str = ""
        self.week: int = 0
        self.knife_height: int = 0
        self.model: int = 0
        self.edge_mode: int = 0
        self.required_time: int = 0
        self.route_angle: int = 0
        self.route_model: int = 0
        self.route_spacing: int = 0
        self.ultrasonic_barrier: int = 0
        self.total_plan_num: int = 0
        self.plan_index: int = 0
        self.result: int = 0
        self.speed: float = 0.0
        self.task_name: str = ""
        self.job_name: str = ""
        self.zone_hashs: list[int] = []
        self.reserved: str = ""
        self.weeks: list[int] = []
        self.start_date: str = ""
        self.end_date: str = ""
        self.job_type: int = 0
        self.interval_days: int = 0
        self.count_down: int = 0
        self.is_enable: bool = True
        self.is_mow_work: bool = True
        self.is_sweeping_work: bool = True
        self.mowing_laps: int = 0
        self.path_order: int = 0
        self.demond_angle: int = 90

    def __str__(self) -> str:
        return f"Plan(pver={self.pver}, sub_cmd={self.sub_cmd}, area={self.area}, work_time={self.work_time}, version='{self.version}', id='{self.id}', user_id='{self.user_id}', device_id='{self.device_id}', plan_id='{self.plan_id}', task_id='{self.task_id}', job_id='{self.job_id}', start_time='{self.start_time}', end_time='{self.end_time}', week={self.week}, knife_height={self.knife_height}, model={self.model}, edge_mode={self.edge_mode}, required_time={self.required_time}, route_angle={self.route_angle}, route_model={self.route_model}, route_spacing={self.route_spacing}, ultrasonic_barrier={self.ultrasonic_barrier}, total_plan_num={self.total_plan_num}, plan_index={self.plan_index}, result={self.result}, speed={self.speed}, task_name='{self.task_name}', job_name='{self.job_name}', zone_hashs={self.zone_hashs}, reserved='{self.reserved}', weeks={self.weeks}, start_date='{self.start_date}', end_date='{self.end_date}', job_type={self.job_type}, interval_days={self.interval_days}, count_down={self.count_down}, is_enable={self.is_enable}, mowing_laps={self.mowing_laps}, path_order={self.path_order}, demond_angle={self.demond_angle}, is_mow_work={self.is_mow_work}, is_sweeping_work={self.is_sweeping_work})"

    def __eq__(self, other):
        if isinstance(other, Plan):
            return self.plan_id == other.plan_id
        return False

    def __hash__(self):
        return hash(self.plan_id)
