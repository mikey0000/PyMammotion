"""Route (``NavReqCoverPath``) builders: the ``toward`` angle on plan (sub_cmd 0) and modify (sub_cmd 3).

The app zeroes ``toward`` on a modify when ``toward_mode`` is 0 inside the builder itself
(``MACommandApiHelper.modifyGenerateRouteInformation`` / ``MACommandHelper.modifyGenerateRouteInformation``),
so every caller gets it.  Its plan builder (``GenerateRouteInformation``) has no such rule.

``toward`` is read off the serialised ``NavReqCoverPath`` (field 11, varint) by walking its fields,
because a bare tag-byte search can collide with value bytes (``speed`` is a float).
"""

from __future__ import annotations

import betterproto2
import pytest

from pymammotion.data.model import GenerateRouteInformation
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, NavReqCoverPath

_DEVICE = "Luba-VA6ABCDE"
_USER_ACCOUNT = 1
_TOWARD_FIELD = 11


def _cover_path(payload: bytes) -> NavReqCoverPath:
    name, value = betterproto2.which_one_of(LubaMsg().parse(payload).nav, "SubNavMsg")
    assert name == "bidire_reqconver_path"
    return value


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return result, pos


def _wire_varint_field(message: bytes, field_number: int) -> int | None:
    """Return the varint field's value as serialised, or ``None`` when it is absent (proto3: absent == 0)."""
    found = None
    pos = 0
    while pos < len(message):
        tag, pos = _varint(message, pos)
        number, wire_type = tag >> 3, tag & 7
        if wire_type == 0:
            value, pos = _varint(message, pos)
            if number == field_number:
                found = value
        elif wire_type == 1:
            pos += 8
        elif wire_type == 2:
            length, pos = _varint(message, pos)
            pos += length
        elif wire_type == 5:
            pos += 4
        else:
            raise AssertionError(f"unexpected wire type {wire_type} in {message.hex()}")
    return found


def _wire_toward(payload: bytes) -> int | None:
    return _wire_varint_field(bytes(_cover_path(payload)), _TOWARD_FIELD)


def _command() -> MammotionCommand:
    return MammotionCommand(_DEVICE, _USER_ACCOUNT)


@pytest.mark.regression
def test_modify_sends_toward_zero_when_toward_mode_is_zero() -> None:
    """A modify with toward_mode 0 sent the caller's stale toward angle; the app sends 0 in that case."""
    payload = _command().modify_route_information(GenerateRouteInformation(toward=45, toward_mode=0))

    assert _cover_path(payload).sub_cmd == 3
    assert _wire_toward(payload) is None, "toward (field 11) must be 0, so absent from the wire"


@pytest.mark.parametrize("toward_mode", [1, 2], ids=["mode-1", "mode-2"])
def test_modify_keeps_toward_when_toward_mode_is_set(toward_mode: int) -> None:
    payload = _command().modify_route_information(GenerateRouteInformation(toward=45, toward_mode=toward_mode))

    assert _wire_toward(payload) == 45


def test_modify_does_not_mutate_the_callers_route() -> None:
    """The zeroing is a wire concern; the route the caller holds keeps its angle."""
    route = GenerateRouteInformation(toward=45, toward_mode=0)

    _command().modify_route_information(route)

    assert route.toward == 45


def test_plan_keeps_toward_when_toward_mode_is_zero() -> None:
    """The app's plan builder sends toward as given, whatever toward_mode is."""
    payload = _command().generate_route_information(GenerateRouteInformation(toward=45, toward_mode=0))

    assert _cover_path(payload).sub_cmd == 0
    assert _wire_toward(payload) == 45
