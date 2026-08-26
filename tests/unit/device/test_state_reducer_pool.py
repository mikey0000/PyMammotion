"""PoolStateReducer behavior for the Spino pool cleaner.

Covers the SysCommCmd (allpowerfullRW) pool toggles, the
``LubaMsg.ctrl.plan_job_set`` plan path, and the fw-info / net-envelope /
devStatus / error-clamp message handling.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.device import PoolCleanerDevice
from pymammotion.data.model.pool_state import SpinoSysStatus, SpinoToggle, SpinoWorkMode
from pymammotion.device.state_reducer import PoolStateReducer
from pymammotion.proto import (
    DeviceFwInfo,
    DevNet,
    DevStatueT,
    DrvWifiMsg,
    LubaMsg,
    MctlSys,
    ModFwInfo,
    PlanJobSet,
    ReportInfoT,
    ResponseSetModeT,
    SpinoCtrl,
    SysCommCmd,
    SysSetDateTime,
    SystemUpdateBufMsg,
    WifiIotStatusReport,
)


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


# ===========================================================================
# PoolStateReducer — fw info, net envelope, devStatus extras, error clamp.
# ===========================================================================


def test_pool_fw_info_populates_device_firmwares() -> None:
    msg = LubaMsg(
        sys=MctlSys(
            toapp_dev_fw_info=DeviceFwInfo(
                result=1,
                version="1.15.2.1047",
                mod=[
                    ModFwInfo(type=63, identify="63-PAWG4", version="1.2.0.281"),
                    ModFwInfo(type=65, identify="65-PACG4", version="1.2.0.273"),
                    ModFwInfo(type=67, identify="67-PESP", version="0.0.0.299"),
                    ModFwInfo(type=61, identify="61-PAMH5", version="5.1.2.2159"),
                    ModFwInfo(type=62, identify="62-PMH5BT", version="5.1.2.2131"),
                ],
            )
        )
    )
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    fw = result.device_firmwares
    assert fw.device_version == "1.15.2.1047"
    assert fw.wheel_hub_motor == "1.2.0.281"
    assert fw.water_pump == "1.2.0.273"
    assert fw.communication == "0.0.0.299"
    assert fw.main_controller == "5.1.2.2159"
    assert fw.main_controller_bt == "5.1.2.2131"


def test_pool_fw_info_result_zero_ignored() -> None:
    msg = LubaMsg(sys=MctlSys(toapp_dev_fw_info=DeviceFwInfo(result=0, version="9.9.9")))
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    assert result.device_firmwares.device_version == ""


def test_pool_wifi_iot_status_updates_connectivity() -> None:
    msg = LubaMsg(
        net=DevNet(
            toapp_wifi_iot_status=WifiIotStatusReport(
                wifi_connected=True, iot_connected=True, productkey="a15Cq8FbCh1", devicename="Spino-E1abc"
            )
        )
    )
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    assert result.pool_state.wifi_connected is True
    assert result.pool_state.iot_connected is True
    assert result.product_key == "a15Cq8FbCh1"


def test_pool_wifi_iot_status_empty_productkey_not_clobbered() -> None:
    device = PoolCleanerDevice(name="Spino-E1abc", product_key="seeded")
    msg = LubaMsg(net=DevNet(toapp_wifi_iot_status=WifiIotStatusReport(wifi_connected=True, iot_connected=False)))
    result = PoolStateReducer().apply(device, msg)
    assert result.product_key == "seeded"
    assert result.pool_state.iot_connected is False


def test_pool_wifi_msg_updates_network_info_but_never_password() -> None:
    msg = LubaMsg(
        net=DevNet(
            toapp_WifiMsg=DrvWifiMsg(
                status1=True,
                status2=True,
                ip="192.168.20.174",
                msgssid="IOT",
                password="battery-easeful-dental",
                rssi=-38,
                wifi_enable=True,
            )
        )
    )
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    assert result.wifi_ssid == "IOT"
    assert result.ip == "192.168.20.174"
    assert result.wifi_enabled is True
    assert result.pool_state.wifi_rssi == -38
    assert "battery-easeful-dental" not in str(result.to_dict())


def test_pool_dev_status_captures_rssi_and_connectivity() -> None:
    msg = LubaMsg(
        sys=MctlSys(
            report_info=ReportInfoT(
                dev_status=DevStatueT(
                    sys_status=1,
                    bat_val=70,
                    model=100,
                    ble_rssi=-48,
                    wifi_rssi=-43,
                    wifi_connect_status=1,
                    iot_connect_status=1,
                )
            )
        )
    )
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    assert result.pool_state.battery == 70
    assert result.pool_state.wifi_rssi == -43
    assert result.pool_state.ble_rssi == -48
    assert result.pool_state.wifi_connected is True
    assert result.pool_state.iot_connected is True
    assert result.pool_state.charging is False


def test_pool_dev_status_charge_status_sets_charging() -> None:
    # A docked Spino reports chargeStatus=1 while sys_status is still PREPARE (1),
    # so charging is not derivable from sys_status alone.
    msg = LubaMsg(sys=MctlSys(report_info=ReportInfoT(dev_status=DevStatueT(sys_status=1, charge_status=1))))
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    assert result.pool_state.charging is True
    assert result.pool_state.sys_status is SpinoSysStatus.PREPARE


def test_pool_dev_status_omitted_work_mode_reports_off() -> None:
    # Heartbeat frames leave work_mode unset (proto3 default 0) once no job is
    # running — that is "no mode active", not the RECHARGE command value.
    device = PoolCleanerDevice(name="Spino-E1abc")
    device.pool_state.work_mode = SpinoWorkMode.ECO
    msg = LubaMsg(sys=MctlSys(report_info=ReportInfoT(dev_status=DevStatueT(sys_status=1, bat_val=68))))
    result = PoolStateReducer().apply(device, msg)
    assert result.pool_state.work_mode is SpinoWorkMode.OFF
    assert result.pool_state.work_mode.name == "OFF"


def test_pool_error_count_negative_clamped_to_zero() -> None:
    data = [2, 43, -1] + [0] * 40
    msg = LubaMsg(sys=MctlSys(system_update_buf=SystemUpdateBufMsg(update_buf_data=data)))
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    assert result.pool_state.error_count == 0
    assert result.pool_state.error_log == []


def test_pool_response_set_mode_applies_mode_and_session_times() -> None:
    # Frame captured from a Spino-E1 mode switch (WALL) over the cloud transport.
    msg = LubaMsg(
        sys=MctlSys(
            response_set_mode=ResponseSetModeT(
                set_work_mode=3,
                cur_work_mode=3,
                start_work_time=1786694053,
                end_work_time=1786694153,
                cur_work_time=1,
            )
        )
    )
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    assert result.pool_state.work_mode is SpinoWorkMode.WALL
    assert result.pool_state.start_work_time == 1786694053
    assert result.pool_state.end_work_time == 1786694153


def test_pool_response_set_mode_history_request_echo_ignored() -> None:
    # statue=2 is the job-history request form, not a mode ack — it must not
    # reset the work mode or the session times.
    device = PoolCleanerDevice(name="Spino-E1abc")
    device.pool_state.work_mode = SpinoWorkMode.WALL
    device.pool_state.start_work_time = 1786694053
    msg = LubaMsg(sys=MctlSys(response_set_mode=ResponseSetModeT(statue=2)))
    result = PoolStateReducer().apply(device, msg)
    assert result.pool_state.work_mode is SpinoWorkMode.WALL
    assert result.pool_state.start_work_time == 1786694053


def test_pool_response_set_mode_unknown_mode_tolerated() -> None:
    msg = LubaMsg(sys=MctlSys(response_set_mode=ResponseSetModeT(set_work_mode=99, cur_work_mode=99)))
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    assert result.pool_state.work_mode is SpinoWorkMode.UNKNOWN


def test_pool_todev_data_time_is_silent_noop() -> None:
    msg = LubaMsg(sys=MctlSys(todev_data_time=SysSetDateTime(year=234, month=7, date=20)))
    result = PoolStateReducer().apply(PoolCleanerDevice(name="Spino-E1abc"), msg)
    assert result.online is True


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
