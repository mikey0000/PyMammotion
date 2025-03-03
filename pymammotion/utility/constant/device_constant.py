from enum import IntEnum

from pymammotion.data.model.report_info import ConnectData


class bleOrderCmd:
    allpowerfullRW = 67
    alongBorder = 9
    areaAndTimeAndPathUpdate = 27
    autoUnderPile = 65
    batteryValueUpdate = 5
    bleAlive = 59
    cancelCurrentRecord = 62
    cancelLogUpdate = 45
    cancelPauseExecuteTask = 47
    checkFramwareVersion = 41
    checkFramwareVersionCallBack = 42
    checkSoftVersion = 35
    checkSoftVersionCallBack = 36
    closeKinfe = 50
    close_clear_connect_current_wifi = 77
    deletingConnectionPath = 22
    deviceOrderResponse = 46
    deviceStatusUpdate = 31
    endChannelLine = 15
    endDrawBarrier = 13
    endDrawBorder = 11
    errorCodeUpdate = 34
    framwarePackageCallBack = 40
    framwareSuccessUpdate = 48
    framwareUpdateCallBack = 38
    generateRouteInformation = 210
    getAreaData = 209
    getDeiveBorderState = 64
    getDeviceInfo = 63
    getDeviceLogInfo = 43
    getHashList = 208
    getrecordwifi = 69
    initPointUpdate = 3
    job_plan_setting_read_delete = 78
    job_plan_setting_read_delete_unable_time = 79
    kinfeState = 51
    knifeHightUpdate = 29
    logProgressUpdate = 44
    openKinfe = 49
    optimizationBorderUpadate = 17
    optimizationChannalLineUpdate = 19
    optimizationObstacleUpdate = 18
    originLagLog = 52
    pauseExecuteTask = 7
    removeObstaclesOrObstructions = 21
    replyOptimizationPackage = 20
    resetBaseStation = 61
    responseDevice = 52
    retrunGenerateRouteInformation = 211
    returnCharge = 8
    rtloactionUpdate = 4
    saveTask = 16
    sendBorderPackage = 21
    sendBorderPackageCallBack = 22
    sendChannalLinePackage = 25
    sendChannalLinePackageCallBack = 26
    sendContrlCallBack = 2
    sendControl = 1
    sendExecuteTask = 6
    sendFramwarePackage = 39
    sendFramwareUpdate = 37
    sendObstaclePackage = 23
    sendObstaclePackageCallBack = 24
    sendPlan = 32
    setKnifeHight = 28
    setMaxSpeed = 33
    startChannelLine = 14
    startDrawBarrier = 12
    startDrawBorder = 10
    startWorkOrder = 60
    startjob = 212
    synTime = 57
    task = 213
    taskProgressUpdate = 30
    testPW = 52
    wificonnectinfoupdate = 68
    wirteReadSpeed = 66


class SystemUpdateBuf:
    BATTERY_STATE_INDEX = 2
    CHARGE_POS_VAILD_INDEX = 9
    CHARGE_POS_X_F_INDEX = 7
    CHARGE_POS_Y_F_INDEX = 8
    CHARGE_TOWARD_INDEX = 3
    ERR_CODE_10_INDEX = 21
    ERR_CODE_1_INDEX = 3
    ERR_CODE_2_INDEX = 5
    ERR_CODE_3_INDEX = 7
    ERR_CODE_4_INDEX = 9
    ERR_CODE_5_INDEX = 11
    ERR_CODE_6_INDEX = 13
    ERR_CODE_7_INDEX = 15
    ERR_CODE_8_INDEX = 17
    ERR_CODE_9_INDEX = 19
    ERR_CODE_CNT_INDEX = 2
    ERR_CODE_ID_INDEX = 0
    ERR_CODE_LEN_INDEX = 1
    ERR_CODE_STAMP_10_INDEX = 22
    ERR_CODE_STAMP_1_INDEX = 4
    ERR_CODE_STAMP_2_INDEX = 6
    ERR_CODE_STAMP_3_INDEX = 8
    ERR_CODE_STAMP_4_INDEX = 10
    ERR_CODE_STAMP_5_INDEX = 12
    ERR_CODE_STAMP_6_INDEX = 14
    ERR_CODE_STAMP_7_INDEX = 16
    ERR_CODE_STAMP_8_INDEX = 18
    ERR_CODE_STAMP_9_INDEX = 20
    SU_LAT_D_INDEX = 5
    SU_LON_D_INDEX = 6
    SU_SPEED_F_INDEX = 4
    SYSTEM_ERR_CODE_INDEX_END = 23
    SYSTEM_INIT_CONFIG_ID_INDEX = 0
    SYSTEM_INIT_CONFIG_INDEX_END = 10
    SYSTEM_INIT_CONFIG_LEN_INDEX = 1
    SYSTEM_ZONE_STATE_INDEX_END = 22
    ZONE_STATE_1_INDEX = 2
    ZONE_STATE_ID_INDEX = 0
    ZONE_STATE_LEN_INDEX = 1


class SystemRapidStateTunnelIndex(IntEnum):
    DIS_CAR_RTK_STARS_INDEX = 15
    DIS_RTK_STATUS_INDEX = 13
    L1_SATS_INDEX = 2
    L2_SATS_INDEX = 6
    POS_LEVEL_INDEX = 1
    POS_TYPE_INDEX = 10
    RAPID_WORK_STATE_VER_INDEX = 12
    REAL_POS_X_F_INDEX = 7
    REAL_POS_Y_F_INDEX = 8
    REAL_TOWARD_F_INDEX = 9
    RTK_AGE_F_INDEX = 3
    SIGNAL_QUALITY_INDEX = 0
    TOP4_TOTAL_MEAN_INDEX = 14
    VEL_MEAN_F_INDEX = 5
    VEL_TOP_F_INDEX = 4
    VSIAM_STATE_INDEX = 16
    ZONE_HASH_INDEX = 11


class SystemTardStateTunnel:
    APP_CONNECTED_INFO = 27
    BATTERY_VAL_INDEX = 2
    BOL_HASH_INDEX = 6
    BREAK_POINT_HASH_INDEX = 11
    BREAK_POINT_INFO_INDEX = 10
    BREAK_POINT_X_F_INDEX = 12
    BREAK_POINT_Y_F_INDEX = 13
    CHARGE_STATE_INDEX = 1
    CUT_HEIGHT_INDEX = 3
    DEVICE_OLD_STATUS_INDEX = 25
    DEVICE_STATE_INDEX = 0
    DRAWING_RTK_BAD_OLD_STATE_INDEX = 29
    MAINTAIN_TOTAL_BATTERY_CYCLES_INDEX = 32
    MAINTAIN_TOTAL_MILEAGE_INDEX = 30
    MAINTAIN_TOTAL_MOWING_TIME_INDEX = 31
    MOW_RUN_SPEED_INDEX = 24
    PATH_HASH_INDEX = 7
    PATH_POS_X_F_INDEX = 15
    PATH_POS_Y_F_INDEX = 16
    PLAN_STATE_INDEX = 5
    REAL_PATH_INDEX = 14
    RTK_LORA_NUM_CHANNEL = 35
    RTK_LORA_NUM_LOC_ID = 36
    RTK_LORA_NUM_NET_ID = 37
    RTK_LORA_NUM_SCAN = 34
    RTK_RESTARTING_INDEX = 28
    RTK_STARS_NUM = 33
    RTK_STATUS = 38
    SENSOR_STATE_INDEX = 4
    SYSTEM_TIME_STAMP = 26
    TARD_WORK_STATE_END = 21
    TARD_WORK_STATE_VER_INDEX = 22
    TASK_AREA_INDEX = 9
    TASK_PROGRESS_INDEX = 8
    TEST_SWITCH_STATE_INDEX = 23
    UB_ERR_CODE_HASH_INDEX = 20
    UB_INIT_CONFIG_HASH_INDEX = 19
    UB_REAL_PATH_HASH_INDEX = 18
    UB_ZONE_STATE_HASH_INDEX = 17


class WorkMode:
    MODE_NOT_ACTIVE = 0
    MODE_ONLINE = 1
    MODE_OFFLINE = 2
    MODE_DISABLE = 8
    MODE_INITIALIZATION = 10
    MODE_READY = 11
    MODE_WORKING = 13
    MODE_RETURNING = 14
    MODE_CHARGING = 15
    MODE_UPDATING = 16
    MODE_LOCK = 17
    MODE_PAUSE = 19
    MODE_MANUAL_MOWING = 20
    MODE_UPDATE_SUCCESS = 22
    MODE_OTA_UPGRADE_FAIL = 23
    MODE_JOB_DRAW = 31
    MODE_OBSTACLE_DRAW = 32
    MODE_CHANNEL_DRAW = 34
    MODE_ERASER_DRAW = 35
    MODE_EDIT_BOUNDARY = 36
    MODE_LOCATION_ERROR = 37
    MODE_BOUNDARY_JUMP = 38
    MODE_CHARGING_PAUSE = 39


def device_connection(connect: ConnectData) -> str:
    """Return string representation of device connection."""

    if connect.wifi_rssi != 0 and connect.ble_rssi != 0:
        return "WIFI/BLE"

    if connect.connect_type == 2 or connect.used_net == "NET_USED_TYPE_WIFI" or connect.wifi_rssi != 0:
        return "WIFI"

    if connect.connect_type == 1 or connect.used_net == "NET_USED_TYPE_MNET":
        return "3G/4G"

    if connect.ble_rssi != 0:
        return "BLE"

    return "None"


def device_mode(value: int) -> str:
    """Return the mode corresponding to the given value.

    This function takes a value and returns the corresponding mode from a
    predefined dictionary.

    Args:
        value (int): The value for which mode needs to be determined.

    Returns:
        str: The mode corresponding to the input value. Returns "Invalid mode" if no
            mode is found.

    """

    modes = {
        0: "MODE_NOT_ACTIVE",
        1: "MODE_ONLINE",
        2: "MODE_OFFLINE",
        8: "MODE_DISABLE",
        10: "MODE_INITIALIZATION",
        11: "MODE_READY",
        12: "MODE_UNCONNECTED",
        13: "MODE_WORKING",
        14: "MODE_RETURNING",
        15: "MODE_CHARGING",
        16: "MODE_UPDATING",
        17: "MODE_LOCK",
        19: "MODE_PAUSE",
        20: "MODE_MANUAL_MOWING",
        22: "MODE_UPDATE_SUCCESS",
        23: "MODE_OTA_UPGRADE_FAIL",
        31: "MODE_JOB_DRAW",
        32: "MODE_OBSTACLE_DRAW",
        34: "MODE_CHANNEL_DRAW",
        35: "MODE_ERASER_DRAW",
        36: "MODE_EDIT_BOUNDARY",
        37: "MODE_LOCATION_ERROR",
        38: "MODE_BOUNDARY_JUMP",
        39: "MODE_CHARGING_PAUSE",
    }
    return modes.get(value, "Invalid mode")


class PosType(IntEnum):
    """Position of the robot."""

    AREA_BORDER_ON = 7
    AREA_INSIDE = 1
    AREA_OUT = 0
    CHANNEL_AREA_OVERLAP = 9
    CHANNEL_ON = 3
    CHARGE_ON = 5
    DUMPING_AREA_INSIDE = 8
    DUMPING_OUTSIDE = 10
    OBS_ON = 2
    TURN_AREA_INSIDE = 4
    VIRTUAL_INSIDE = 6


def camera_brightness(value: int) -> str:
    """Return the brightness corresponding to the given value."""
    modes = {
        0: "Dark",
        1: "Light",
    }
    return modes.get(value, "Invalid mode")
