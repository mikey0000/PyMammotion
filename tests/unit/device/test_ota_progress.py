"""OTA upgrade progress folded from ``net.toapp_upgrade_report`` into ``update_check``.

Consumers read ``update_check.isupgrading`` / ``.progress`` — a model fed by the cloud's
slow ``checkDeviceVersion`` poll, which reports ``isupgrading=False, progress=0`` for the
whole of an upgrade the device is meanwhile streaming live progress for.  These tests pin
the mapping from the device-pushed frames to that model.

Frames are taken from a real Yuka-MNTXVHBE OTA capture (2026-08-15), which streams
``result=2`` throughout with ``progress`` climbing 18 → 27.
"""

from __future__ import annotations

import copy
import time

from pymammotion.data.model.device import _OTA_PUSH_STALE_AFTER, MowerDevice, RTKBaseStationDevice
from pymammotion.device.state_reducer import MowerStateReducer, RTKStateReducer
from pymammotion.http.model.http import CheckDeviceVersion
from pymammotion.proto import DevNet, DrvUpgradeReport, LubaMsg


def _report(
    *,
    progress: int,
    result: int,
    version: str = "1.30.29.8",
    otaid: str = "920582167925358592",
    message: str = "dl fw:SocMidware, 54651495/14861",
) -> LubaMsg:
    return LubaMsg(
        net=DevNet(
            toapp_upgrade_report=DrvUpgradeReport(
                devname="Yuka-MNTXVHBE",
                otaid=otaid,
                version=version,
                progress=progress,
                result=result,
                message=message,
            )
        )
    )


def test_in_progress_frame_drives_update_check() -> None:
    """result=2 is an in-flight tick: isupgrading True and the live percentage."""
    device = MowerDevice(name="Yuka-MNTXVHBE")
    updated = MowerStateReducer().apply(device, _report(progress=18, result=2))

    assert updated.update_check.isupgrading is True
    assert updated.update_check.progress == 18
    # The full frame is still available for consumers that want the stage detail.
    assert updated.events.ota_progress.message == "dl fw:SocMidware, 54651495/14861"
    assert updated.events.ota_progress.otaid == "920582167925358592"


def test_progress_climbs_across_frames() -> None:
    """Successive frames advance the percentage, as in the captured upgrade."""
    device = MowerDevice(name="Yuka-MNTXVHBE")
    reducer = MowerStateReducer()

    for pct in (18, 19, 20, 21, 27):
        device = reducer.apply(device, _report(progress=pct, result=2))

    assert device.update_check.progress == 27
    assert device.update_check.isupgrading is True


def test_success_frame_pins_100_and_installs_version() -> None:
    """result=0 means *finished*, not "no progress" — the APK's completion branch.

    The completion frame carries the last sub-component's counter rather than 100, so a
    display would otherwise rest at whatever it happened to be.
    """
    device = MowerDevice(name="Yuka-MNTXVHBE")
    reducer = MowerStateReducer()
    device = reducer.apply(device, _report(progress=27, result=2))
    device = reducer.apply(device, _report(progress=27, result=0))

    assert device.update_check.isupgrading is False
    assert device.update_check.progress == 100
    assert device.update_check.upgradeable is False
    assert device.update_check.current_version == "1.30.29.8"
    assert device.device_firmwares.device_version == "1.30.29.8"


def test_failure_frames_stop_the_upgrade() -> None:
    """result=1 and negative codes both route to the APK's failure branch."""
    for result in (1, -23):
        device = MowerDevice(name="Yuka-MNTXVHBE")
        reducer = MowerStateReducer()
        device = reducer.apply(device, _report(progress=40, result=2))
        device = reducer.apply(device, _report(progress=40, result=result))

        assert device.update_check.isupgrading is False, f"result={result} should end the upgrade"
        assert device.update_check.progress == 40
        # Not a success — the target version must not be recorded as installed.
        assert device.device_firmwares.device_version != "1.30.29.8"


def test_out_of_order_frame_does_not_rewind_progress() -> None:
    """The device interleaves report copies; a late duplicate must not walk the bar back."""
    device = MowerDevice(name="Yuka-MNTXVHBE")
    reducer = MowerStateReducer()
    device = reducer.apply(device, _report(progress=27, result=2))
    device = reducer.apply(device, _report(progress=19, result=2))

    assert device.update_check.progress == 27


def test_new_otaid_resets_the_progress_floor() -> None:
    """A different upgrade job is not bound by the previous run's high-water mark."""
    device = MowerDevice(name="Yuka-MNTXVHBE")
    reducer = MowerStateReducer()
    device = reducer.apply(device, _report(progress=90, result=2, otaid="job-1"))
    device = reducer.apply(device, _report(progress=5, result=2, otaid="job-2"))

    assert device.update_check.progress == 5


def test_apply_does_not_mutate_previous_snapshot() -> None:
    """The reducer is pure: the frame must not write through to the caller's device."""
    device = MowerDevice(name="Yuka-MNTXVHBE")
    reducer = MowerStateReducer()
    device = reducer.apply(device, _report(progress=18, result=2))

    before = copy.deepcopy(device)
    updated = reducer.apply(device, _report(progress=42, result=2))

    assert updated.update_check.progress == 42
    assert device.update_check.progress == before.update_check.progress == 18
    assert device.events.ota_progress.progress == 18


def test_rtk_base_station_tracks_progress_without_events() -> None:
    """RTKBaseStationDevice has no `events`; update_check must still track the upgrade."""
    device = RTKBaseStationDevice(name="RTK-Test")
    updated = RTKStateReducer().apply(device, _report(progress=33, result=2))

    assert updated.update_check.isupgrading is True
    assert updated.update_check.progress == 33
    assert not hasattr(updated, "events")


def test_rtk_apply_does_not_mutate_previous_snapshot() -> None:
    """RTKStateReducer.apply uses a shallow dataclasses.replace — nested models must be copied."""
    device = RTKBaseStationDevice(name="RTK-Test")
    reducer = RTKStateReducer()
    device = reducer.apply(device, _report(progress=33, result=2))

    updated = reducer.apply(device, _report(progress=55, result=2))

    assert updated.update_check.progress == 55
    assert device.update_check.progress == 33


# ---------------------------------------------------------------------------
# Cloud poll vs. BLE push precedence.
#
# OTA progress arrives from the cloud's checkDeviceVersion poll normally, and from the
# device's own toapp_upgrade_report stream while BLE is connected.  Both write
# update_check, so the precedence between them has to be pinned.
#
# Staleness is exercised by offsetting ota_progress_at from real time.monotonic(),
# matching the approach in test_ble_loop.py.
# ---------------------------------------------------------------------------


def _cloud_check(*, isupgrading: bool, progress: int, current_version: str = "1.30.25.11") -> CheckDeviceVersion:
    return CheckDeviceVersion(
        device_id="UTpbwGC7vxd4DpNvbFGL000000",
        device_name="Yuka-MNTXVHBE",
        current_version=current_version,
        upgradeable=True,
        isupgrading=isupgrading,
        progress=progress,
    )


def test_stale_cloud_poll_does_not_erase_live_ble_progress() -> None:
    """The captured regression: mid-upgrade the poll returns progress=0/isupgrading=False.

    Taken verbatim it would blank a progress display that BLE had just driven to 25%.
    """
    device = MowerDevice(name="Yuka-MNTXVHBE")
    device = MowerStateReducer().apply(device, _report(progress=25, result=2))

    device.apply_version_check(_cloud_check(isupgrading=False, progress=0))

    assert device.update_check.isupgrading is True
    assert device.update_check.progress == 25
    # Everything the cloud is authoritative for still comes through.
    assert device.update_check.upgradeable is True
    assert device.update_check.device_id == "UTpbwGC7vxd4DpNvbFGL000000"


def test_cloud_poll_wins_when_it_agrees_an_upgrade_is_running() -> None:
    """A poll that reports its own progress is taken as-is — it isn't stale."""
    device = MowerDevice(name="Yuka-MNTXVHBE")
    device = MowerStateReducer().apply(device, _report(progress=25, result=2))

    device.apply_version_check(_cloud_check(isupgrading=True, progress=40))

    assert device.update_check.isupgrading is True
    assert device.update_check.progress == 40


def test_cloud_poll_reclaims_control_once_the_push_goes_stale() -> None:
    """BLE stops dead when the device reboots to install; the cloud must take back over.

    Without the staleness bound the entity would sit at "upgrading" forever.
    """
    device = MowerDevice(name="Yuka-MNTXVHBE")
    device = MowerStateReducer().apply(device, _report(progress=25, result=2))
    device.ota_progress_at = time.monotonic() - (_OTA_PUSH_STALE_AFTER + 5.0)

    device.apply_version_check(_cloud_check(isupgrading=False, progress=0, current_version="1.30.29.8"))

    assert device.update_check.isupgrading is False
    assert device.update_check.progress == 0
    assert device.device_firmwares.device_version == "1.30.29.8"


def test_stamp_from_a_previous_process_is_treated_as_stale() -> None:
    """ota_progress_at round-trips through HA's store, but monotonic resets on restart.

    A future-looking stamp must not be read as fresh, or the restored state would pin
    the entity to "upgrading" with no way out.
    """
    device = MowerDevice(name="Yuka-MNTXVHBE")
    device = MowerStateReducer().apply(device, _report(progress=25, result=2))
    device.ota_progress_at = time.monotonic() + 10_000.0

    device.apply_version_check(_cloud_check(isupgrading=False, progress=0))

    assert device.update_check.isupgrading is False


def test_cloud_poll_applies_normally_with_no_push_at_all() -> None:
    """Cloud-only devices (no BLE) are unaffected by any of the above."""
    device = MowerDevice(name="Luba-Test")

    device.apply_version_check(_cloud_check(isupgrading=True, progress=60))
    assert device.update_check.isupgrading is True
    assert device.update_check.progress == 60

    device.apply_version_check(_cloud_check(isupgrading=False, progress=0))
    assert device.update_check.isupgrading is False
    assert device.update_check.progress == 0


def test_apply_version_check_does_not_mutate_the_caller_s_object() -> None:
    """The defended path must not write back into the CheckDeviceVersion it was handed."""
    device = MowerDevice(name="Yuka-MNTXVHBE")
    device = MowerStateReducer().apply(device, _report(progress=25, result=2))

    check = _cloud_check(isupgrading=False, progress=0)
    device.apply_version_check(check)

    assert check.isupgrading is False
    assert check.progress == 0
