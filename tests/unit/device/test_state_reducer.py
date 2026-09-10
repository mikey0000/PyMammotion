"""MowerStateReducer behavior — sub-tree sharing, report-data application, area names.

The first group verifies the sub-tree sharing contract in MowerStateReducer (#125):
each nav sub-message's ``apply()`` case only deep-copies the sub-trees its
handler actually mutates.  Fields that are not copied must be shared by
identity between ``current`` and the returned snapshot; copied fields must
be distinct instances so mutations through one do not leak to the other.

Also covered: ``ReportData.update()`` partial-field semantics, the area-name
fallback (``name_time.name`` over numbered labels), and how the reducer applies
Mammotion flat-property pushes.
"""

from __future__ import annotations

import gc
import tracemalloc

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import CommDataCouple, FrameList as _FL, NavGetCommData
from pymammotion.data.model.report_info import (
    ConnectData,
    DeviceData,
    Maintain,
    ReportData,
    RTKData,
    VisionInfo,
    WorkData,
)
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import (
    AppGetAllAreaHashName as _AGAHN,
    AreaHashName as _AHName,
    LubaMsg,
    MctlNav,
    MulSetVideoAck,
    MulVideoErrorCode,
    NavGetAllPlanTask,
    NavReqCoverPath,
    NavSysParamMsg,
    NavUnableTimeSet,
    ReportInfoData,
    RptConnectStatus,
    RptDevStatus,
    RptMaintain,
    RptRtk,
    RptWork,
    SocMul,
    VioToAppInfoMsg,
)
from tests.unit.device._helpers import make_reducer_device as _make_device
from tests.unit.messaging._helpers import area_frame_named as _area_frame_named

_ALL_FIELDS = ("map", "work", "mower_state", "non_work_hours", "work_session_result")


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


# Demonstrates the memory allocation growth bug from #125.


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


# Tests that ReportData.update() only mutates fields present in the proto message.


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


# Area-name fallback — name_time.name priority over numbered fallbacks


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
        """A real name reserves no number, so the unnamed area takes the lowest free
        one — matching HashList.computed_areas' gap-fill rather than numbering by
        position, which would make the label depend on how many areas precede it.
        """
        result = self._apply_empty(_device_with_named_areas({111: "Voor", 222: ""}))
        by_hash = {a.hash: a.name for a in result.map.area_name}
        assert by_hash == {111: "Voor", 222: "area 1"}

    def test_explicit_hashnames_win_over_name_time(self) -> None:
        device = _device_with_named_areas({111: "Voor"})
        result = MowerStateReducer().apply(
            device, LubaMsg(nav=MctlNav(toapp_all_hash_name=_AGAHN(hashnames=[_AHName(hash=111, name="Front Lawn")])))
        )
        assert {a.hash: a.name for a in result.map.area_name}[111] == "Front Lawn"

    def test_existing_numbers_survive_a_new_area_arriving(self) -> None:
        """A fallback label is baked into the HA entity_id at registration, so an
        area that already has one must keep it.  Numbering by position in
        sorted(map.area) renumbers every area above a newly-arrived hash.
        """
        device = _device_with_named_areas({111: "", 222: ""})
        device = self._apply_empty(device)
        assert {a.hash: a.name for a in device.map.area_name} == {111: "area 1", 222: "area 2"}

        # A third area arrives whose hash sorts BELOW the other two.
        device.map.area[10] = _FL(data=[_area_frame_named(10, "")])
        device = self._apply_empty(device)
        by_hash = {a.hash: a.name for a in device.map.area_name}
        assert by_hash[111] == "area 1", "existing area was renumbered"
        assert by_hash[222] == "area 2", "existing area was renumbered"
        assert by_hash[10] == "area 3", "new area must take the lowest free number"

    def test_transient_areas_do_not_shift_the_real_ones(self) -> None:
        """Real hashes from a Luba 3 that displayed as area 4/5/6: three extra
        hashes arrived mid-fetch, were numbered ahead of the real areas, then
        pruned — leaving the real areas permanently labelled from 4.
        """
        real = [507072516911571140, 1231479802544112924, 2094378125895869177]
        device = _device_with_named_areas(dict.fromkeys(real, ""))
        device = self._apply_empty(device)
        assert [a.name for a in device.map.area_name] == ["area 1", "area 2", "area 3"]

        for extra in (101, 202, 303):  # sort below every real hash
            device.map.area[extra] = _FL(data=[_area_frame_named(extra, "")])
        device = self._apply_empty(device)
        by_hash = {a.hash: a.name for a in device.map.area_name}
        assert [by_hash[h] for h in real] == ["area 1", "area 2", "area 3"]

    def test_name_does_not_flip_on_repeated_empty_hash_name(self) -> None:
        device = _device_with_named_areas({111: "Voor", 222: "Achter"})
        reducer = MowerStateReducer()
        msg = LubaMsg(nav=MctlNav(toapp_all_hash_name=_AGAHN(hashnames=[])))
        for _ in range(5):
            device = reducer.apply(device, msg)
        assert {a.hash: a.name for a in device.map.area_name} == {111: "Voor", 222: "Achter"}


# Device GPS coordinate (radians) is stored on device.location.device in degrees.
#
# The Mammotion property push delivers coordinate.lat/lon in RADIANS, but
# device.location.device is consumed as degrees (HA device_tracker adds metre
# offsets ÷ 111111 and never converts).  RTK stays radians (sensor.py * 180/pi).

#
# def test_mammotion_coordinate_stored_in_degrees() -> None:
#     """apply_mammotion_properties must convert coordinate.lat/lon (radians) to degrees."""
#     import math
#
#     from pymammotion.data.mqtt.mammotion_properties import Coordinate, DeviceProperties
#     from pymammotion.data.mqtt.properties import MammotionPropertiesMessage
#
#     reducer = MowerStateReducer()
#     device = _make_device()
#
#     lat_rad, lon_rad = 0.5, 0.2  # ~28.6479°, ~11.4592° — both within ~28° of the equator
#     props = MammotionPropertiesMessage(
#         id="1",
#         version="1.0",
#         sys={},
#         params=DeviceProperties(coordinate=Coordinate(lon=lon_rad, lat=lat_rad)),
#     )
#
#     updated = reducer.apply_mammotion_properties(device, props)
#
#     assert updated.location.device.latitude == pytest.approx(math.degrees(lat_rad))
#     assert updated.location.device.longitude == pytest.approx(math.degrees(lon_rad))
#     # Sanity: the stored value is real degrees, not the raw radians.
#     assert updated.location.device.latitude != pytest.approx(lat_rad)


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


def test_mammotion_partial_push_uses_presence_not_truthiness() -> None:
    """A partial flat-property push must key on field PRESENCE (None == absent),
    not truthiness — an omitted field is left untouched, but a genuine 0 is applied.

    Post-2025 "Mammotion" devices interleave the flat-property push with the
    protobuf report; without this an omitted field arrives as 0 and blanks out
    sys_status / battery / blade height every other update. Using truthiness would
    fix that but wrongly drop a real 0 (e.g. 0% battery), so the fields are Optional
    and guarded with ``is not None``.
    """
    from pymammotion.data.mqtt.mammotion_properties import DeviceProperties
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

    reducer = MowerStateReducer()
    device = _make_device()
    device.report_data.dev.sys_status = 13   # MODE_WORKING
    device.report_data.dev.battery_val = 82
    device.report_data.work.knife_height = 50

    # Absent fields (None) must be left untouched.
    empty = MammotionPropertiesMessage(id="1", version="1.0", sys={}, params=DeviceProperties())
    updated = reducer.apply_mammotion_properties(device, empty)
    assert updated.report_data.dev.sys_status == 13
    assert updated.report_data.dev.battery_val == 82
    assert updated.report_data.work.knife_height == 50

    # A genuine 0% battery IS present and must be applied (not treated as absent).
    zero = MammotionPropertiesMessage(
        id="2", version="1.0", sys={}, params=DeviceProperties(battery_percentage=0)
    )
    updated = reducer.apply_mammotion_properties(device, zero)
    assert updated.report_data.dev.battery_val == 0
    assert updated.report_data.dev.sys_status == 13  # still untouched (absent)

    # Non-zero values still update.
    real = MammotionPropertiesMessage(
        id="3", version="1.0", sys={},
        params=DeviceProperties(device_state=14, battery_percentage=79, knife_height=60),
    )
    updated = reducer.apply_mammotion_properties(device, real)
    assert updated.report_data.dev.sys_status == 14
    assert updated.report_data.dev.battery_val == 79
    assert updated.report_data.work.knife_height == 60


def test_set_video_ack_error_is_logged_and_changes_nothing(caplog) -> None:
    """A rejected Agora video command is surfaced in the log, not silently dropped."""
    reducer = MowerStateReducer()
    current = _make_device()
    msg = LubaMsg(mul=SocMul(set_video_ack=MulSetVideoAck(error_code=MulVideoErrorCode.CREATE_CHANNEL_FAILED)))

    with caplog.at_level("WARNING", logger="pymammotion.device.state_reducer"):
        updated = reducer.apply(current, msg)

    assert "CREATE_CHANNEL_FAILED" in caplog.text
    _assert_sharing(current, updated, copied_fields=("mower_state",))


def test_set_video_ack_success_is_quiet(caplog) -> None:
    """A successful ack must not produce a warning."""
    reducer = MowerStateReducer()
    msg = LubaMsg(mul=SocMul(set_video_ack=MulSetVideoAck(error_code=MulVideoErrorCode.SUCCESS)))

    with caplog.at_level("WARNING", logger="pymammotion.device.state_reducer"):
        reducer.apply(_make_device(), msg)

    assert caplog.text == ""

# otaProgress on the Mammotion flat property push drives update_check


def _ota_props(progress: int, result: int, version: str = "1.16.0.1101"):
    import json

    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

    return MammotionPropertiesMessage.from_json(
        json.dumps(
            {
                "id": "1",
                "version": "1.0",
                "sys": {"ack": 1},
                "method": "thing.event.property.post",
                "params": {"otaProgress": {"progress": progress, "result": result, "version": version}},
            }
        )
    )


def test_mammotion_ota_progress_marks_upgrade_in_progress() -> None:
    reducer = MowerStateReducer()
    device = _make_device()

    updated = reducer.apply_mammotion_properties(device, _ota_props(progress=37, result=2))

    assert updated.update_check.isupgrading is True
    assert updated.update_check.progress == 37
    assert updated.ota_progress_at > 0
    # A live push must survive the stale cloud version poll that follows it.
    assert updated.has_live_ota_push()


def test_mammotion_ota_result_zero_completes_and_installs_version() -> None:
    reducer = MowerStateReducer()
    device = _make_device()
    device.update_check.upgradeable = True

    updated = reducer.apply_mammotion_properties(device, _ota_props(progress=98, result=0))

    assert updated.update_check.isupgrading is False
    assert updated.update_check.progress == 100
    assert updated.update_check.upgradeable is False
    assert updated.device_firmwares.device_version == "1.16.0.1101"


def test_mammotion_ota_failure_stops_upgrading_and_keeps_progress() -> None:
    reducer = MowerStateReducer()
    device = _make_device()

    updated = reducer.apply_mammotion_properties(device, _ota_props(progress=61, result=1))

    assert updated.update_check.isupgrading is False
    assert updated.update_check.progress == 61
    assert updated.device_firmwares.device_version != "1.16.0.1101"
