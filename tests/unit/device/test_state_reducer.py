"""Verifies the sub-tree sharing contract in MowerStateReducer (#125).

Each nav sub-message's ``apply()`` case only deep-copies the sub-trees its
handler actually mutates.  Fields that are not copied must be shared by
identity between ``current`` and the returned snapshot; copied fields must
be distinct instances so mutations through one do not leak to the other.
"""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import AreaHashNameList
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import (
    LubaMsg,
    MctlNav,
    NavGetAllPlanTask,
    NavReqCoverPath,
    NavSysParamMsg,
    NavUnableTimeSet,
)

_ALL_FIELDS = ("map", "work", "mower_state", "non_work_hours", "work_session_result")


def _make_device() -> MowerDevice:
    device = MowerDevice(name="Luba-Test")
    device.map.area_name = [AreaHashNameList(name="zone-1", hash=111)]
    return device


def _assert_sharing(
    current: MowerDevice, updated: MowerDevice, copied_fields: tuple[str, ...]
) -> None:
    """Fields in copied_fields must be distinct; others must share identity."""
    for name in _ALL_FIELDS:
        current_val = getattr(current, name)
        updated_val = getattr(updated, name)
        if name in copied_fields:
            assert updated_val is not current_val, (
                f"{name} was declared as copied but still shares identity with current"
            )
        else:
            assert updated_val is current_val, (
                f"{name} was not declared as copied but was deep-copied anyway"
            )


def test_nav_sys_param_cmd_only_copies_mower_state() -> None:
    reducer = MowerStateReducer()
    current = _make_device()
    msg = LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=3, context=1)))
    updated = reducer.apply(current, msg)
    _assert_sharing(current, updated, copied_fields=("mower_state",))
    assert updated.mower_state.rain_detection is True
    assert current.mower_state.rain_detection is False


def test_unable_time_set_only_copies_non_work_hours() -> None:
    reducer = MowerStateReducer()
    current = _make_device()
    msg = LubaMsg(
        nav=MctlNav(
            todev_unable_time_set=NavUnableTimeSet(
                sub_cmd=1, unable_start_time="22:00", unable_end_time="06:00"
            )
        )
    )
    updated = reducer.apply(current, msg)
    _assert_sharing(current, updated, copied_fields=("non_work_hours",))
    assert updated.non_work_hours.start_time == "22:00"
    assert current.non_work_hours.start_time == ""


def test_all_plan_task_only_copies_map() -> None:
    reducer = MowerStateReducer()
    current = _make_device()
    msg = LubaMsg(nav=MctlNav(all_plan_task=NavGetAllPlanTask(tasks=[])))
    updated = reducer.apply(current, msg)
    _assert_sharing(current, updated, copied_fields=("map",))


def test_bidire_reqconver_path_copies_nothing_but_rebinds_work() -> None:
    """bidire_reqconver_path wholesale-rebinds device.work — no prior deep-copy needed."""
    reducer = MowerStateReducer()
    current = _make_device()
    original_work = current.work
    msg = LubaMsg(nav=MctlNav(bidire_reqconver_path=NavReqCoverPath(job_mode=1)))
    updated = reducer.apply(current, msg)
    # Nothing was deep-copied (work was rebuilt by the handler, not pre-copied)
    assert updated.map is current.map
    assert updated.mower_state is current.mower_state
    assert updated.non_work_hours is current.non_work_hours
    assert updated.work_session_result is current.work_session_result
    # But device.work was rebuilt by the handler and current.work is untouched
    assert updated.work is not original_work
    assert current.work is original_work




# ===========================================================================
# Demonstrates the memory allocation growth bug from #125.
# ===========================================================================
import gc
import tracemalloc

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import CommDataCouple, NavGetCommData
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import LubaMsg, MctlNav, NavSysParamMsg


def _make_device_with_large_map(points_per_frame: int = 500) -> MowerDevice:
    """Build a device with a realistic-size HashList."""
    device = MowerDevice(name="Luba-Test")
    frame = NavGetCommData(
        pver=0,
        sub_cmd=0,
        action=0,
        type=0,
        hash=123,
        total_frame=1,
        current_frame=1,
        data_hash=0,
        data_len=points_per_frame,
        data_couple=[CommDataCouple(x=float(i), y=float(i)) for i in range(points_per_frame)],
    )
    device.map.area[123] = [frame]
    return device


def test_retained_snapshots_do_not_balloon_on_nav_sys_param() -> None:
    """nav_sys_param_cmd writes only mower_state; retained snapshots must share the map.

    When subscribers retain snapshots (debounce bus, state machine history,
    HA coordinator .data), the deep-copy cost per message is paid per-snapshot.
    A correct reducer shares the HashList across snapshots, so holding N
    snapshots costs O(1) map memory, not O(N).
    """
    points = 500
    iterations = 200
    reducer = MowerStateReducer()
    current = _make_device_with_large_map(points_per_frame=points)
    msg = LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=3, context=1)))

    # Warm up: process a few messages to let any one-time allocations settle.
    for _ in range(3):
        current = reducer.apply(current, msg)

    gc.collect()
    tracemalloc.start()
    baseline_bytes, _ = tracemalloc.get_traced_memory()

    retained: list[MowerDevice] = []
    for _ in range(iterations):
        current = reducer.apply(current, msg)
        retained.append(current)

    final_bytes, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    growth_bytes = final_bytes - baseline_bytes

    # Leaky implementation: each retained snapshot has its own CommDataCouple
    # list (500 points * ~100-200 bytes) — 200 snapshots * 500 * 150 ≈ 15 MiB.
    # Correct implementation: map is shared across all retained snapshots — a
    # per-snapshot overhead of just mower_state (small) is all that accrues.
    max_allowed_growth_bytes = 2 * 1024 * 1024  # 2 MiB budget for 200 snapshots
    assert growth_bytes < max_allowed_growth_bytes, (
        f"Heap grew {growth_bytes / 1024 / 1024:.1f} MiB across {iterations} "
        f"retained snapshots of nav_sys_param_cmd with a {points}-point map — "
        f"HashList is being deep-copied into every snapshot (#125)"
    )


# ===========================================================================
# Tests that ReportData.update() only mutates fields present in the proto message.
# ===========================================================================
from pymammotion.data.model.report_info import (
    ConnectData,
    DeviceData,
    Maintain,
    RTKData,
    ReportData,
    VisionInfo,
    WorkData,
)
from pymammotion.proto import ReportInfoData, RptConnectStatus, RptDevStatus, RptMaintain, RptRtk, RptWork, VioToAppInfoMsg


def _make_report_data_with_values() -> ReportData:
    rd = ReportData()
    rd.connect = ConnectData(wifi_rssi=-60, iot_con_status=1)
    rd.dev = DeviceData(sys_status=5, battery_val=50)
    rd.rtk = RTKData(status=3, gps_stars=10)
    rd.maintenance = Maintain(mileage=100000, work_time=9999)
    rd.vision_info = VisionInfo(x=1.0, y=2.0)
    rd.work = WorkData(area=1234, progress=5678)
    return rd


def test_partial_update_only_touches_present_fields() -> None:
    """When ReportInfoData contains only dev+rtk, other fields must stay unchanged."""
    rd = _make_report_data_with_values()

    msg = ReportInfoData(
        dev=RptDevStatus(sys_status=13, battery_val=82),
        rtk=RptRtk(status=4, gps_stars=25),
    )

    rd.update(msg)

    # Updated fields
    assert rd.dev.sys_status == 13
    assert rd.dev.battery_val == 82
    assert rd.rtk.status == 4
    assert rd.rtk.gps_stars == 25

    # Unchanged fields — must retain their original values
    assert rd.connect.wifi_rssi == -60
    assert rd.connect.iot_con_status == 1
    assert rd.maintenance.mileage == 100000
    assert rd.maintenance.work_time == 9999
    assert rd.vision_info.x == 1.0
    assert rd.vision_info.y == 2.0
    assert rd.work.area == 1234
    assert rd.work.progress == 5678


def test_connect_only_update() -> None:
    """Only connect present — all other fields stay unchanged."""
    rd = _make_report_data_with_values()

    msg = ReportInfoData(connect=RptConnectStatus(wifi_rssi=-53, iot_con_status=1))
    rd.update(msg)

    assert rd.connect.wifi_rssi == -53
    # dev still has original value
    assert rd.dev.sys_status == 5


def test_work_only_update() -> None:
    """Only work present — all other fields stay unchanged."""
    rd = _make_report_data_with_values()

    msg = ReportInfoData(work=RptWork(area=99999, progress=11111))
    rd.update(msg)

    assert rd.work.area == 99999
    assert rd.work.progress == 11111
    assert rd.dev.sys_status == 5
    assert rd.connect.wifi_rssi == -60


def test_full_update_touches_all_present_fields() -> None:
    """When all sub-messages are present, all fields are updated."""
    rd = _make_report_data_with_values()

    msg = ReportInfoData(
        connect=RptConnectStatus(wifi_rssi=-40),
        dev=RptDevStatus(sys_status=0, battery_val=100),
        rtk=RptRtk(status=2, gps_stars=15),
        maintain=RptMaintain(mileage=500000, work_time=123456),
        vio_to_app_info=VioToAppInfoMsg(x=3.0, y=4.0),
        work=RptWork(area=8888, progress=7777),
    )
    rd.update(msg)

    assert rd.connect.wifi_rssi == -40
    assert rd.dev.sys_status == 0
    assert rd.dev.battery_val == 100
    assert rd.rtk.status == 2
    assert rd.rtk.gps_stars == 15
    assert rd.maintenance.mileage == 500000
    assert rd.maintenance.work_time == 123456
    assert rd.vision_info.x == 3.0
    assert rd.vision_info.y == 4.0
    assert rd.work.area == 8888
    assert rd.work.progress == 7777


def test_empty_message_leaves_everything_unchanged() -> None:
    """An empty ReportInfoData must not modify any existing field."""
    rd = _make_report_data_with_values()

    rd.update(ReportInfoData())

    assert rd.dev.sys_status == 5
    assert rd.dev.battery_val == 50
    assert rd.connect.wifi_rssi == -60
    assert rd.rtk.status == 3
    assert rd.maintenance.mileage == 100000
    assert rd.vision_info.x == 1.0
    assert rd.work.area == 1234


# ===========================================================================
# Regression test for the Luba 2 AWD 3000 ``networkInfo`` property parse failure.
# ===========================================================================
import json

from pymammotion.data.mqtt.mammotion_properties import NetworkInfo

LUBA2_AWD_NETWORK_INFO = json.dumps(
    {
        "ssid": "REDACTED",
        "ip": "192.168.1.1",
        "wifi_sta_mac": "aa:bb:cc:dd:ee:01",
        "wifi_rssi": -44,
        "bt_mac": "aa:bb:cc:dd:ee:02",
        "mnet_model": "L716-EU",
        "imei": "000000000000000",
        "fw_ver": "17016.1000.00.38.02.17",
        "sim": "Ready",
        "imsi": "000000000000000",
        "mnet_rssi": -73,
        "signal": 3,
        "mnet_link": 1,
        "mnet_option": "REDACTED",
        "mnet_ip": "10.0.0.1",
        "used_net": 1,
        "hub_reset": 0,
        "mnet_dis": 0,
        "airplane_times": 0,
        "lsusb_num": 7,
        "mnet_rx": "181.47MB",
        "mnet_tx": "177.76MB",
        "mnet_uniot": 0,
        "mnet_un_getiot": 1,
        "apn_num": 1,
        "apn_info": "REDACTED",
        "apn_cid": 1,
        "ssh_flag": "0",
        "mileage": "272.64 km",
        "work_time": "324 h 3 min 42 s",
        "bat_cycles": "120 times",
    }
)


def test_luba2_awd_network_info_parses() -> None:
    """A Luba 2 AWD 3000 networkInfo payload decodes instead of being dropped."""
    ni = NetworkInfo.from_json(LUBA2_AWD_NETWORK_INFO)

    assert ni.wifi_rssi == -44
    assert ni.mnet_rssi == -73
    assert ni.mnet_model == "L716-EU"
    assert ni.mileage == "272.64 km"
    assert ni.work_time == "324 h 3 min 42 s"
    assert ni.bat_cycles == "120 times"

    assert ni.wifi_available == 0
    assert ni.iccid == ""
    assert ni.sim_source == ""
    assert ni.mnet_reg == ""
    assert ni.mnet_rsrp == ""
    assert ni.mnet_snr == ""
    assert ni.mnet_enable == 0
    assert ni.wt_sec == 0
    assert ni.b_tra is None
    assert ni.bw_tra is None
    assert ni.m_tra is None


# ===========================================================================
# Tests for PoolStateReducer applying SysCommCmd (allpowerfullRW) pool toggles.
# ===========================================================================
import pytest

from pymammotion.data.model.device import PoolCleanerDevice
from pymammotion.data.model.pool_state import SpinoToggle
from pymammotion.device.state_reducer import PoolStateReducer
from pymammotion.proto import LubaMsg, MctlSys, SysCommCmd


def _apply(device: PoolCleanerDevice, *, toggle_id: int, value: int) -> PoolCleanerDevice:
    msg = LubaMsg(sys=MctlSys(bidire_comm_cmd=SysCommCmd(id=toggle_id, context=value, rw=0)))
    return PoolStateReducer().apply(device, msg)


@pytest.mark.parametrize(
    ("toggle", "field"),
    [
        (SpinoToggle.buzzer, "buzzer"),
        (SpinoToggle.turbo_clean, "turbo_clean"),
        (SpinoToggle.platform_cleaning, "platform_cleaning"),
        (SpinoToggle.waterline_parking, "waterline_parking"),
    ],
)
def test_toggle_on(toggle: SpinoToggle, field: str) -> None:
    result = _apply(PoolCleanerDevice(name="Spino-E1abc"), toggle_id=int(toggle), value=1)
    assert getattr(result.pool_state, field) is True


def test_toggle_off_clears_previous_value() -> None:
    device = PoolCleanerDevice(name="Spino-E1abc")
    device.pool_state.turbo_clean = True
    result = _apply(device, toggle_id=int(SpinoToggle.turbo_clean), value=0)
    assert result.pool_state.turbo_clean is False


def test_member_names_match_pool_state_fields() -> None:
    # The reducer relies on SpinoToggle.name == the PoolState field name.
    state = PoolCleanerDevice().pool_state
    for toggle in SpinoToggle:
        assert hasattr(state, toggle.name), f"PoolState missing field for {toggle.name}"


def test_unknown_sys_comm_id_ignored() -> None:
    # A generic/mower SysCommCmd id we don't model must not raise or alter state.
    device = PoolCleanerDevice(name="Spino-E1abc")
    result = _apply(device, toggle_id=6, value=1)  # 6 = a Luba-Pro RW id, not a pool toggle
    assert result.pool_state.buzzer is False
    assert result.pool_state.turbo_clean is False


# ===========================================================================
# PoolStateReducer tests for the ``LubaMsg.ctrl.plan_job_set`` path.
# ===========================================================================
import pytest

from pymammotion.data.model.device import PoolCleanerDevice
from pymammotion.device.state_reducer import PoolStateReducer
from pymammotion.proto import LubaMsg, PlanJobSet, SpinoCtrl


def _frame(**kwargs) -> LubaMsg:
    """Build a LubaMsg envelope wrapping a single PlanJobSet."""
    return LubaMsg(ctrl=SpinoCtrl(plan_job_set=PlanJobSet(**kwargs)))


class TestPlanJobSetReducer:
    def test_upserts_plan_keyed_by_jobid(self) -> None:
        reducer = PoolStateReducer()
        msg = _frame(cmd=4, jobid=0xABCDEF12, jobname="Daily", work_mode=1, enable=0)
        device = reducer.apply(PoolCleanerDevice(name="Spino-Test"), msg)

        assert 0xABCDEF12 in device.plans
        plan = device.plans[0xABCDEF12]
        assert plan.jobname == "Daily"
        assert plan.work_mode == 1

    def test_enable_field_is_inverted_at_the_boundary(self) -> None:
        reducer = PoolStateReducer()
        # ``enable=0`` on the wire ⇒ ``enabled=True`` in Python
        enabled_msg = _frame(cmd=4, jobid=1, enable=0)
        device = reducer.apply(PoolCleanerDevice(name="x"), enabled_msg)
        assert device.plans[1].enabled is True

        # ``enable=1`` ⇒ ``enabled=False``
        disabled_msg = _frame(cmd=4, jobid=2, enable=1)
        device = reducer.apply(device, disabled_msg)
        assert device.plans[2].enabled is False

    def test_weeks_and_submode_lists_are_copied(self) -> None:
        reducer = PoolStateReducer()
        msg = _frame(
            cmd=4, jobid=42, weeks=[1, 2, 3, 4, 5], sub_mode=[2, 3], enable=0
        )
        device = reducer.apply(PoolCleanerDevice(name="x"), msg)
        plan = device.plans[42]
        assert plan.weeks == [1, 2, 3, 4, 5]
        assert plan.sub_mode == [2, 3]

    def test_plans_stale_set_when_total_exceeds_known(self) -> None:
        reducer = PoolStateReducer()
        msg = _frame(cmd=4, jobid=1, totalplannum=3, enable=0)
        device = reducer.apply(PoolCleanerDevice(name="x"), msg)
        # one plan stored, device says three exist → stale
        assert device.plans_stale is True

    def test_plans_stale_clears_when_counts_match(self) -> None:
        reducer = PoolStateReducer()
        device = PoolCleanerDevice(name="x")
        device = reducer.apply(device, _frame(cmd=4, jobid=1, totalplannum=2, enable=0))
        assert device.plans_stale is True
        device = reducer.apply(device, _frame(cmd=4, jobid=2, totalplannum=2, enable=0))
        assert device.plans_stale is False

    def test_zero_jobid_frame_is_ignored(self) -> None:
        # DELETE_ALL echoes / error responses can arrive with jobid=0 —
        # storing those would clutter the plans dict.
        reducer = PoolStateReducer()
        msg = _frame(cmd=5, jobid=0, totalplannum=0)
        device = reducer.apply(PoolCleanerDevice(name="x"), msg)
        assert device.plans == {}

    def test_returns_a_copy_not_a_mutation(self) -> None:
        """Reducers MUST return a new dataclass to keep snapshot semantics."""
        reducer = PoolStateReducer()
        original = PoolCleanerDevice(name="x")
        updated = reducer.apply(original, _frame(cmd=4, jobid=99, enable=0))
        assert updated is not original
        assert 99 not in original.plans  # original untouched


class TestNonCtrlEnvelopes:
    """Non-ctrl frames must not accidentally route into the plan path."""

    def test_sys_frame_with_no_recognised_subtype_is_a_noop(self) -> None:
        # Mower-style nav frame; the pool reducer ignores nav entirely.
        from pymammotion.proto import MctlNav

        reducer = PoolStateReducer()
        device = PoolCleanerDevice(name="x")
        # An empty MctlNav has no SubNavMsg set; reducer should not crash.
        result = reducer.apply(device, LubaMsg(nav=MctlNav()))
        assert result.plans == {}


# Smoke test that PoolPlan helpers work as the reducer expects.
def test_pool_plan_with_enabled_round_trip() -> None:
    from pymammotion.data.model.pool_state import PoolPlan

    plan = PoolPlan(jobid=1, enabled=True)
    assert plan.with_enabled(False).enabled is False
    assert plan.with_renamed("foo").jobname == "foo"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])


# ===========================================================================
# Regression tests for partial ``thing.event.property.post`` payloads.
# ===========================================================================
import json

from pymammotion.data.mqtt.mammotion_properties import DeviceProperties
from pymammotion.data.mqtt.properties import MammotionPropertiesMessage


SPINO_MODEL_ONLY = json.dumps(
    {
        "id": "14846",
        "version": "1.0",
        "sys": {"ack": 1},
        "params": {"intMod": "SPINO E1", "extMod": "SPINO E1"},
        "method": "thing.event.property.post",
    }
)

SPINO_FW_ONLY = json.dumps(
    {
        "id": "14848",
        "version": "1.0",
        "sys": {"ack": 1},
        "params": {
            "deviceVersion": "1.15.2.1039",
            "deviceVersionInfo": json.dumps(
                {
                    "devVer": "1.15.2.1039",
                    "whole": 1,
                    "fwInfo": [
                        {"t": "63", "c": "63-PAWG4", "v": "1.2.0.275"},
                        {"t": "65", "c": "65-PACG4", "v": "1.2.0.279"},
                    ],
                }
            ),
        },
        "method": "thing.event.property.post",
    }
)


def test_partial_property_post_model_fields_only() -> None:
    """A property/post carrying only ``intMod`` / ``extMod`` decodes successfully."""
    msg = MammotionPropertiesMessage.from_json(SPINO_MODEL_ONLY)
    p = msg.params

    assert p.int_mod == "SPINO E1"
    assert p.ext_mod == "SPINO E1"

    # Absent fields default rather than raising; absent nested objects are None.
    assert p.device_state == 0
    assert p.battery_percentage == 0
    assert p.device_version == ""
    assert p.network_info is None
    assert p.coordinate is None
    assert p.device_other_info is None
    assert p.device_version_info is None
    assert p.check_data is None


def test_partial_property_post_firmware_only() -> None:
    """A property/post carrying only ``deviceVersion`` / ``deviceVersionInfo`` decodes successfully."""
    msg = MammotionPropertiesMessage.from_json(SPINO_FW_ONLY)
    p = msg.params

    assert p.device_version == "1.15.2.1039"
    assert p.device_version_info is not None
    assert p.device_version_info.dev_ver == "1.15.2.1039"
    assert [fw.c for fw in p.device_version_info.fw_info] == ["63-PAWG4", "65-PACG4"]

    # Everything else defaults / is None.
    assert p.battery_percentage == 0
    assert p.network_info is None
    assert p.coordinate is None


def test_device_properties_accepts_empty_params() -> None:
    """A property/post with no params at all still decodes (every field optional)."""
    p = DeviceProperties.from_dict({})
    assert p.device_state == 0
    assert p.network_info is None


# ===========================================================================
# Regression test for the Yuka Mini 2 ``thing.event.property.post`` parse failure.
# ===========================================================================
import json
from pathlib import Path

from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

# tests/unit/device/ → repo tests/ is parents[2].
FIXTURE = Path(__file__).parents[2] / "fixtures" / "yuka_mini2_property_post.json"


def test_yuka_mini2_property_post_parses() -> None:
    """The full property message decodes instead of being dropped on a missing field."""
    raw = FIXTURE.read_bytes()
    msg = MammotionPropertiesMessage.from_json(raw)
    p = msg.params

    # Core status that HA depends on — the data that was being thrown away.
    assert p.battery_percentage == 31
    assert p.device_state == 13
    assert p.knife_height == 60
    assert "YUKA mini 2" in p.ext_mod
    assert p.device_version == "2.3.23.19"

    # Fields this device class does not report must default, not raise.
    assert p.left_motor_version == ""
    assert p.right_motor_version == ""
    assert p.rtk_version == ""
    assert p.bms_version == ""
    assert p.network_info.ip == ""
    assert p.network_info.apn_num == 0
    assert p.device_other_info.tilt_degree == ""

    # Fields the device *does* report still populate (incl. the previously typo'd alias).
    assert p.network_info.wifi_rssi == -65
    assert p.device_other_info.iot_con_fail_min == "0"
    assert [fw.c for fw in p.device_version_info.fw_info][:2] == [
        "202-MNWheelfG4BT",
        "201-MNWheelfG4",
    ]


def test_missing_optional_fields_does_not_raise() -> None:
    """Stripping every now-optional key must still yield a usable message."""
    obj = json.loads(FIXTURE.read_bytes())
    for key in ("leftMotorVersion", "rightMotorVersion", "rtkVersion", "bmsVersion"):
        obj["params"].pop(key, None)  # already absent for this device, asserted explicit
    msg = MammotionPropertiesMessage.from_json(json.dumps(obj))
    assert msg.params.battery_percentage == 31


# ===========================================================================
# Area-name fallback — name_time.name priority over numbered fallbacks
# ===========================================================================

from pymammotion.data.model.hash_list import (  # noqa: E402
    AreaHashNameList as _AHN,
    CommDataCouple as _CDC,
    FrameList as _FL,
    NavGetCommData as _NGCD,
    NavNameTime as _NNT,
)
from pymammotion.proto import (  # noqa: E402
    AppGetAllAreaHashName as _AGAHN,
    AreaHashName as _AHName,
)


def _area_frame_named(hash_val: int, name: str) -> _NGCD:
    return _NGCD(
        hash=hash_val, total_frame=1, current_frame=1,
        name_time=_NNT(name=name, create_time=1, modify_time=1),
        data_couple=[_CDC(x=0.0, y=0.0)],
    )


def _device_with_named_areas(areas: dict[int, str]) -> MowerDevice:
    device = MowerDevice(name="Test-Mower")
    for hash_val, name in areas.items():
        device.map.area[hash_val] = _FL(data=[_area_frame_named(hash_val, name)])
    return device


class TestStateReducerAreaNameFallback:
    def _apply_empty(self, device: MowerDevice) -> MowerDevice:
        return MowerStateReducer().apply(device, LubaMsg(nav=MctlNav(toapp_all_hash_name=_AGAHN(hashnames=[]))))

    def test_uses_name_time_name_when_hashnames_empty(self) -> None:
        result = self._apply_empty(_device_with_named_areas({111: "Voor", 222: "Achter"}))
        by_hash = {a.hash: a.name for a in result.map.area_name}
        assert by_hash == {111: "Voor", 222: "Achter"}

    def test_falls_back_to_numbered_when_name_time_empty(self) -> None:
        result = self._apply_empty(_device_with_named_areas({111: "", 222: ""}))
        by_hash = {a.hash: a.name for a in result.map.area_name}
        assert by_hash == {111: "area 1", 222: "area 2"}

    def test_mixed_named_and_unnamed_areas(self) -> None:
        result = self._apply_empty(_device_with_named_areas({111: "Voor", 222: ""}))
        by_hash = {a.hash: a.name for a in result.map.area_name}
        assert by_hash == {111: "Voor", 222: "area 2"}

    def test_explicit_hashnames_win_over_name_time(self) -> None:
        device = _device_with_named_areas({111: "Voor"})
        result = MowerStateReducer().apply(
            device, LubaMsg(nav=MctlNav(toapp_all_hash_name=_AGAHN(hashnames=[_AHName(hash=111, name="Front Lawn")])))
        )
        assert {a.hash: a.name for a in result.map.area_name}[111] == "Front Lawn"

    def test_name_does_not_flip_on_repeated_empty_hash_name(self) -> None:
        device = _device_with_named_areas({111: "Voor", 222: "Achter"})
        reducer = MowerStateReducer()
        msg = LubaMsg(nav=MctlNav(toapp_all_hash_name=_AGAHN(hashnames=[])))
        for _ in range(5):
            device = reducer.apply(device, msg)
        assert {a.hash: a.name for a in device.map.area_name} == {111: "Voor", 222: "Achter"}


# ===========================================================================
# Device GPS coordinate (radians) is stored on device.location.device in degrees.
#
# The Mammotion property push delivers coordinate.lat/lon in RADIANS, but
# device.location.device is consumed as degrees (HA device_tracker adds metre
# offsets ÷ 111111 and never converts).  RTK stays radians (sensor.py * 180/pi).
# ===========================================================================


def test_mammotion_coordinate_stored_in_degrees() -> None:
    """apply_mammotion_properties must convert coordinate.lat/lon (radians) to degrees."""
    import math

    from pymammotion.data.mqtt.mammotion_properties import Coordinate, DeviceProperties
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

    reducer = MowerStateReducer()
    device = _make_device()

    lat_rad, lon_rad = 0.5, 0.2  # ~28.6479°, ~11.4592° — both within ~28° of the equator
    props = MammotionPropertiesMessage(
        id="1",
        version="1.0",
        sys={},
        params=DeviceProperties(coordinate=Coordinate(lon=lon_rad, lat=lat_rad)),
    )

    updated = reducer.apply_mammotion_properties(device, props)

    assert updated.location.device.latitude == pytest.approx(math.degrees(lat_rad))
    assert updated.location.device.longitude == pytest.approx(math.degrees(lon_rad))
    # Sanity: the stored value is real degrees, not the raw radians.
    assert updated.location.device.latitude != pytest.approx(lat_rad)


def test_mammotion_coordinate_zero_is_left_unset() -> None:
    """A 0.0 coordinate component (unset) must not overwrite the stored location."""
    from pymammotion.data.mqtt.mammotion_properties import Coordinate, DeviceProperties
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

    reducer = MowerStateReducer()
    device = _make_device()
    device.location.device.latitude = 12.0
    device.location.device.longitude = 34.0

    props = MammotionPropertiesMessage(
        id="1",
        version="1.0",
        sys={},
        params=DeviceProperties(coordinate=Coordinate(lon=0.0, lat=0.0)),
    )

    updated = reducer.apply_mammotion_properties(device, props)

    assert updated.location.device.latitude == 12.0
    assert updated.location.device.longitude == 34.0
