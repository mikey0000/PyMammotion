"""Schedule (``NavPlanJobSet``) builders: Edge Coverage and the path-angle fields on create, edit and echo.

The app sends ``ride_boundary_distance`` (field 39, a float), ``toward_mode`` (37) and
``toward_included_angle`` (38) on every full plan write (``MACommandApiHelper.sendSchedule``),
ungated by model.  On a Luba 1 it also carries ``toward_mode`` in ``reserved[4]`` and ``week``
as ``weeks[0]``.  Auto-reverse mowing direction rides in field 41, a 32-byte ``reserved2``.
Edits re-send the whole plan: a value the builder drops is a value the
device forgets.  Every full write goes through one ``NavPlanJobSet`` builder, which is where
the model/border-laps gate lives, so each public builder is exercised here.
"""

from __future__ import annotations

import dataclasses
import struct
from collections.abc import Callable

import betterproto2
import pytest

from pymammotion.data.model.hash_list import Plan
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, NavPlanJobSet
from tests._helpers import (
    LUBA1_NAME as _LUBA1,
    LUBA1_PRODUCT_KEY as _LUBA1_KEY,
    NEWER_MODEL_NAME,
    UNRECOGNISED_NAME as _UNNAMED,
    make_stored_plan_frame,
)

_SUPPORTED = NEWER_MODEL_NAME
_UNSUPPORTED = "Luba-VS6ABCDE"  # Luba 2: the app hides the Edge Coverage row

#: Field 39, wire type 5 (fixed32): tag (39 << 3) | 5 = 317 -> varint 0xBD 0x02, then a little-endian float.
_FIELD_39_TAG = b"\xbd\x02"
#: Varint fields 37 / 38: tags (37 << 3) = 296 -> 0xA8 0x02 and (38 << 3) = 304 -> 0xB0 0x02.
_TOWARD_MODE_TAG = b"\xa8\x02"
_TOWARD_ANGLE_TAG = b"\xb0\x02"

_WRITES = pytest.mark.parametrize("build", ["create_plan", "edit_plan", "send_schedule"])


def _field_39(distance: float) -> bytes:
    return _FIELD_39_TAG + struct.pack("<f", distance)


def _plan_job(payload: bytes) -> NavPlanJobSet:
    name, value = betterproto2.which_one_of(LubaMsg().parse(payload).nav, "SubNavMsg")
    assert name == "todev_planjob_set"
    return value


def _plan(**overrides: object) -> Plan:
    return Plan(**{"plan_id": "p1", "edge_mode": 1, "ride_boundary_distance": 0.5, **overrides})


@_WRITES
@pytest.mark.parametrize("distance", [0.5, 0.2])
def test_plan_writes_put_the_ride_boundary_distance_on_the_wire_as_field_39(build: str, distance: float) -> None:
    """Any distance passes through unchanged; nothing snaps it to the app's two positions."""
    payload = getattr(MammotionCommand(_SUPPORTED, 1), build)(_plan(ride_boundary_distance=distance))

    assert _field_39(distance) in payload, f"field 39 = {distance}f not found in {payload.hex()}"
    assert _plan_job(payload).ride_boundary_distance == pytest.approx(distance)


@_WRITES
def test_plan_write_drops_the_ride_boundary_distance_on_an_unsupported_model(build: str) -> None:
    """The app never offers the row on these models, so the value must not reach the device."""
    payload = getattr(MammotionCommand(_UNSUPPORTED, 1), build)(_plan())

    assert _FIELD_39_TAG not in payload, f"field 39 sent to an unsupported model: {payload.hex()}"
    assert _plan_job(payload).ride_boundary_distance == 0.0


@_WRITES
def test_plan_write_drops_the_ride_boundary_distance_without_border_laps(build: str) -> None:
    """``edge_mode`` is the plan's border-lap count; with none, there is no edge to ride on."""
    payload = getattr(MammotionCommand(_SUPPORTED, 1), build)(_plan(edge_mode=0))

    assert _FIELD_39_TAG not in payload, f"field 39 sent with border laps off: {payload.hex()}"
    assert _plan_job(payload).ride_boundary_distance == 0.0


_Resend = Callable[[MammotionCommand, Plan], bytes]

_RESENDS = pytest.mark.parametrize(
    "resend",
    [
        pytest.param(lambda command, plan: command.edit_plan(plan), id="edit"),
        pytest.param(lambda command, plan: command.rename_plan(plan, "renamed"), id="rename"),
        pytest.param(lambda command, plan: command.enable_plan(plan, False), id="disable"),
        pytest.param(lambda command, plan: command.copy_plan(plan, "copy", "p2"), id="copy"),
    ],
)


def _read_back(stored: float) -> Plan:
    frame = NavPlanJobSet(plan_id="p1", edge_mode=1, total_plan_num=1, ride_boundary_distance=stored)
    return Plan.from_dict(frame.to_dict(casing=betterproto2.Casing.SNAKE))


@_RESENDS
@pytest.mark.parametrize("stored", [0.2, 0.5])
def test_resending_a_read_back_plan_keeps_its_ride_boundary_distance(resend: _Resend, stored: float) -> None:
    """Each of these re-sends the whole stored plan; the device replaces it wholesale."""
    payload = resend(MammotionCommand(_SUPPORTED, 1), _read_back(stored))

    assert _field_39(stored) in payload, f"stored {stored} not echoed: {payload.hex()}"
    assert _plan_job(payload).ride_boundary_distance == pytest.approx(stored)


@_RESENDS
def test_resending_a_read_back_plan_keeps_edge_coverage_off(resend: _Resend) -> None:
    """A stored 0.0 must stay 0.0, which proves the echo above is the stored value and not a default."""
    payload = resend(MammotionCommand(_SUPPORTED, 1), _read_back(0.0))

    assert _FIELD_39_TAG not in payload, f"a stored 0.0 came back non-zero: {payload.hex()}"


@pytest.mark.regression
@_WRITES
@pytest.mark.parametrize("device", [_SUPPORTED, _UNSUPPORTED, _LUBA1])
def test_plan_writes_put_the_path_angle_mode_and_included_angle_on_the_wire(build: str, device: str) -> None:
    """``send_schedule`` hard-coded ``toward_mode=0``, so neither field reached the device.

    The app sends ``planBean1.getTowardMode()`` / ``getDemond_angle()`` to every model, Luba 1 included, so a
    relative or absolute path-angle schedule was silently stored as the default.
    """
    payload = getattr(MammotionCommand(device, 1), build)(_plan(toward_mode=2, toward_included_angle=45))

    assert _TOWARD_MODE_TAG + b"\x02" in payload, f"field 37 = 2 not found in {payload.hex()}"
    assert _TOWARD_ANGLE_TAG + b"\x2d" in payload, f"field 38 = 45 not found in {payload.hex()}"
    job = _plan_job(payload)
    assert (job.toward_mode, job.toward_included_angle) == (2, 45)


def _read_back_toward(toward_mode: int, toward_included_angle: int) -> Plan:
    frame = NavPlanJobSet(
        plan_id="p1", total_plan_num=1, toward_mode=toward_mode, toward_included_angle=toward_included_angle
    )
    return Plan.from_dict(frame.to_dict(casing=betterproto2.Casing.SNAKE))


@pytest.mark.regression
@_RESENDS
@pytest.mark.parametrize("stored", [1, 2])
def test_resending_a_read_back_plan_keeps_its_toward_mode(resend: _Resend, stored: int) -> None:
    """An edit, rename, toggle or copy re-sent ``toward_mode=0``, resetting the stored path-angle mode."""
    payload = resend(MammotionCommand(_SUPPORTED, 1), _read_back_toward(stored, 30))

    assert _TOWARD_MODE_TAG + bytes([stored]) in payload, f"stored toward_mode {stored} not echoed: {payload.hex()}"
    job = _plan_job(payload)
    assert (job.toward_mode, job.toward_included_angle) == (stored, 30)


@_RESENDS
def test_resending_a_read_back_plan_keeps_toward_mode_zero(resend: _Resend) -> None:
    """A stored 0 must stay 0, which proves the echo above is the stored value and not a constant."""
    payload = resend(MammotionCommand(_SUPPORTED, 1), _read_back_toward(0, 0))

    assert _TOWARD_MODE_TAG not in payload, f"a stored toward_mode 0 came back non-zero: {payload.hex()}"
    assert _TOWARD_ANGLE_TAG not in payload, f"a stored included angle 0 came back non-zero: {payload.hex()}"


#: Field 30 (``reserved``), wire type 2: tag (30 << 3) | 2 = 242 -> varint 0xF2 0x01, then the length.
_RESERVED_TAG = b"\xf2\x01\x08"
#: Field 14 (``week``), varint: tag 14 << 3 = 112.
_WEEK_TAG = b"\x70"


def _reserved_on_wire(payload: bytes) -> list[int]:
    start = payload.index(_RESERVED_TAG) + len(_RESERVED_TAG)
    return list(payload[start : start + 8])


def _read_back_luba1(byte_4: int, field_37: int = 0) -> Plan:
    """A Luba 1 plan as the device stores it: every reserved byte echoed +10."""
    return Plan.from_wire(make_stored_plan_frame(byte_4, field_37), _LUBA1)


@pytest.mark.regression
@_WRITES
@pytest.mark.parametrize("toward_mode", [1, 2])
def test_a_luba1_plan_write_carries_toward_mode_in_reserved_byte_4_and_field_37(build: str, toward_mode: int) -> None:
    """A Luba 1 schedule was sent with ``reserved[4] = 0``, where that model keeps its path-angle mode.

    ``WorkSettingViewModel.getReserved`` writes ``bArr[4] = towardMode`` for a Luba 1 and ``sendSchedule`` still
    sets field 37 to the same value.
    """
    payload = getattr(MammotionCommand(_LUBA1, 1), build)(_plan(toward_mode=toward_mode))

    assert _reserved_on_wire(payload) == [0, 0, 0, 0, toward_mode, 0, 0, 0], payload.hex()
    assert _TOWARD_MODE_TAG + bytes([toward_mode]) in payload, f"field 37 = {toward_mode} missing: {payload.hex()}"


@_WRITES
def test_a_newer_model_plan_write_keeps_reserved_byte_4_zero(build: str) -> None:
    payload = getattr(MammotionCommand(_SUPPORTED, 1), build)(_plan(toward_mode=2))

    assert _reserved_on_wire(payload) == [0] * 8, payload.hex()
    assert _TOWARD_MODE_TAG + b"\x02" in payload, f"field 37 = 2 missing: {payload.hex()}"


@pytest.mark.regression
@_RESENDS
@pytest.mark.parametrize("stored", [1, 2])
def test_resending_a_read_back_luba1_plan_keeps_its_toward_mode(resend: _Resend, stored: int) -> None:
    """A Luba 1 read-back decoded ``toward_mode`` from field 37 and re-sent that on every edit.

    The device holds the mode in ``reserved[4]`` (echoed +10), so field 37 went out as 0 while byte 4 kept the
    real mode: the two disagreed, and a host reading ``Plan.toward_mode`` saw the wrong one.
    """
    payload = resend(MammotionCommand(_LUBA1, 1), _read_back_luba1(byte_4=stored + 10))

    assert _reserved_on_wire(payload)[4] == stored, payload.hex()
    assert _TOWARD_MODE_TAG + bytes([stored]) in payload, f"field 37 = {stored} missing: {payload.hex()}"


@pytest.mark.regression
def test_editing_the_toward_mode_of_a_read_back_luba1_plan_sends_the_new_mode() -> None:
    """Changing ``toward_mode`` on a stored Luba 1 plan re-sent the stored ``reserved[4]``, so the change was lost."""
    edited = dataclasses.replace(_read_back_luba1(byte_4=11), toward_mode=2)

    payload = MammotionCommand(_LUBA1, 1).edit_plan(edited)

    assert _reserved_on_wire(payload)[4] == 2, payload.hex()
    assert _TOWARD_MODE_TAG + b"\x02" in payload, payload.hex()


@pytest.mark.regression
@_WRITES
def test_a_luba1_plan_write_sends_the_first_of_weeks_as_week(build: str) -> None:
    """The app sets ``week = weeks[0]`` on a Luba 1 (``NewWorkSettingActivity.java:1289-1291``); we sent ``week`` as is."""
    payload = getattr(MammotionCommand(_LUBA1, 1), build)(_plan(week=0, weeks=[3, 5]))

    assert _WEEK_TAG + b"\x03" in payload, f"field 14 = 3 missing: {payload.hex()}"
    assert _plan_job(payload).week == 3


@_WRITES
def test_a_luba1_plan_write_without_weeks_keeps_week(build: str) -> None:
    """With no ``weeks`` there is no first entry to substitute, so the held ``week`` is sent."""
    assert _plan_job(getattr(MammotionCommand(_LUBA1, 1), build)(_plan(week=4, weeks=[]))).week == 4


@_WRITES
def test_a_newer_model_plan_write_sends_week_as_is(build: str) -> None:
    """Only a Luba 1 swaps in ``weeks[0]``; elsewhere ``week`` goes out unchanged, even when it is 0."""
    payload = getattr(MammotionCommand(_SUPPORTED, 1), build)(_plan(week=0, weeks=[3, 5]))

    assert _plan_job(payload).week == 0


def _luba1_by_product_key() -> MammotionCommand:
    command = MammotionCommand(_UNNAMED, 1)
    command.set_device_product_key(_LUBA1_KEY)
    return command


@_WRITES
def test_a_luba1_known_only_by_product_key_carries_toward_mode_in_reserved_byte_4_and_field_37(build: str) -> None:
    payload = getattr(_luba1_by_product_key(), build)(_plan(toward_mode=2))

    assert _reserved_on_wire(payload) == [0, 0, 0, 0, 2, 0, 0, 0], payload.hex()
    assert _TOWARD_MODE_TAG + b"\x02" in payload, f"field 37 = 2 missing: {payload.hex()}"


@_WRITES
def test_a_luba1_known_only_by_product_key_sends_the_first_of_weeks_as_week(build: str) -> None:
    """The name matches no rule, so the builder must pass its product key to ``week_for_send``."""
    payload = getattr(_luba1_by_product_key(), build)(_plan(week=6, weeks=[3, 5]))

    assert _WEEK_TAG + b"\x03" in payload, f"field 14 = 3 missing: {payload.hex()}"
    assert _plan_job(payload).week == 3


def _read_back_with_weeks(device_name: str) -> Plan:
    frame = NavPlanJobSet(plan_id="p1", total_plan_num=1, week=6, weeks=[3, 5])
    return Plan.from_wire(frame, device_name)


@_RESENDS
def test_resending_a_read_back_luba1_plan_sends_the_first_of_weeks_as_week(resend: _Resend) -> None:
    payload = resend(MammotionCommand(_LUBA1, 1), _read_back_with_weeks(_LUBA1))

    assert _WEEK_TAG + b"\x03" in payload, f"field 14 = 3 missing: {payload.hex()}"
    assert _plan_job(payload).week == 3


@_RESENDS
def test_resending_a_read_back_newer_model_plan_sends_week_as_held(resend: _Resend) -> None:
    payload = resend(MammotionCommand(_SUPPORTED, 1), _read_back_with_weeks(_SUPPORTED))

    assert _WEEK_TAG + b"\x06" in payload, f"field 14 = 6 missing: {payload.hex()}"
    assert _plan_job(payload).week == 6


#: Field 41 (``reserved2``), packed: tag (41 << 3) | 2 = 330 -> varint 0xCA 0x02, then length 32.
_RESERVED2_TAG = b"\xca\x02\x20"
#: Field 40 (``task_settings_mode``), varint: tag 40 << 3 = 320 -> 0xC0 0x02.
_TASK_SETTINGS_MODE_TAG = b"\xc0\x02"
#: The app has no per-model gate on either field.
_EVERY_MODEL = pytest.mark.parametrize("device", [_SUPPORTED, _UNSUPPORTED, _LUBA1])


def _reserved2_on_wire(payload: bytes) -> bytes:
    assert _RESERVED2_TAG in payload, f"no 32-byte field 41 in {payload.hex()}"
    start = payload.index(_RESERVED2_TAG) + len(_RESERVED2_TAG)
    return payload[start : start + 32]


def _read_back_auto_change_direction(stored: int, device: str) -> Plan:
    return Plan.from_wire(make_stored_plan_frame(reserved2=[stored] + [10] * 31), device)


@pytest.mark.regression
@_WRITES
@_EVERY_MODEL
@pytest.mark.parametrize(("setting", "byte_0"), [(True, 1), (False, 0), (None, 0)], ids=["on", "off", "unset"])
def test_plan_writes_send_auto_change_direction_as_the_apps_32_byte_reserved2(
    build: str, device: str, setting: bool | None, byte_0: int
) -> None:
    """Schedules were sent without field 41, so a schedule could never carry auto-reverse mowing direction.

    Every app schedule builder fills it from ``getReserved2`` (32 bytes, the setting in byte 0, zeroed when off)
    and ``MACommandApiHelper.sendSchedule`` sends it to every model.
    """
    payload = getattr(MammotionCommand(device, 1), build)(_plan(auto_change_direction=setting))

    assert _reserved2_on_wire(payload) == bytes([byte_0] + [0] * 31), payload.hex()
    assert _plan_job(payload).auto_change_direction == [byte_0] + [0] * 31


@_WRITES
@_EVERY_MODEL
def test_plan_writes_leave_task_settings_mode_unset(build: str, device: str) -> None:
    """``sendSchedule`` never sets field 40, unlike the route builders."""
    payload = getattr(MammotionCommand(device, 1), build)(_plan(auto_change_direction=True))

    assert _TASK_SETTINGS_MODE_TAG not in payload, payload.hex()
    assert _plan_job(payload).task_settings_mode == 0


@pytest.mark.regression
@_RESENDS
@_EVERY_MODEL
@pytest.mark.parametrize(("stored", "byte_0"), [(11, 1), (10, 0)], ids=["on", "off"])
def test_resending_a_read_back_plan_keeps_its_auto_change_direction(
    resend: _Resend, device: str, stored: int, byte_0: int
) -> None:
    """An edit, rename, toggle or copy re-sent no field 41, so the stored auto-reverse setting was dropped.

    The app re-sends byte 0 with the +10 echo removed (``JobScheduleActivity.java:843-855``).
    """
    payload = resend(MammotionCommand(device, 1), _read_back_auto_change_direction(stored, device))

    assert _reserved2_on_wire(payload) == bytes([byte_0] + [0] * 31), payload.hex()
    assert _plan_job(payload).auto_change_direction == [byte_0] + [0] * 31


@_RESENDS
@_EVERY_MODEL
def test_resending_a_read_back_plan_leaves_task_settings_mode_unset(resend: _Resend, device: str) -> None:
    payload = resend(MammotionCommand(device, 1), _read_back_auto_change_direction(11, device))

    assert _plan_job(payload).task_settings_mode == 0
