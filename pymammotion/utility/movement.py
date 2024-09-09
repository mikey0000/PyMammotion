from .rocker_util import RockerControlUtil


def transform_both_speeds(linear: float, angular: float, linear_percent: float, angular_percent: float):
    transfrom3 = RockerControlUtil.getInstance().transfrom3(linear, linear_percent)
    transform4 = RockerControlUtil.getInstance().transfrom3(angular, angular_percent)

    if transfrom3 is not None and len(transfrom3) > 0:
        linear_speed = transfrom3[0] * 10
        angular_speed = int(transform4[1] * 4.5)
        return linear_speed, angular_speed


def get_percent(percent: float):
    if percent <= 15.0:
        return 0.0

    return percent - 15.0
