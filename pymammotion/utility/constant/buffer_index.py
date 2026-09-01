"""Byte-buffer index constants for the legacy packed device-state buffers.

Decoding of these buffers lives in ``pymammotion/device/state_reducer.py``
(``_update_system_update_buf``) and ``pymammotion/data/model/device.py``
(``buffer`` / ``run_state_update``).
"""

from __future__ import annotations

from enum import IntEnum


class SystemUpdateBuf(IntEnum):
    """Byte-buffer index constants for parsing legacy system status update packets."""

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
    """Byte-buffer index constants for parsing rapid (high-frequency) device state tunnel packets."""

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


class SystemTardStateTunnel(IntEnum):
    """Byte-buffer index constants for parsing slow (low-frequency) device state tunnel packets."""

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
