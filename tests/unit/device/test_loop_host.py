"""The LoopHost contract between DeviceHandle and the activity loops.

The loops are free coroutines that take their host and own no state.  That was an
undocumented convention, and they satisfied it by reaching into ~22 private
attributes of DeviceHandle; LoopHost declares it instead.  These tests hold both
directions: DeviceHandle must supply everything the contract promises, and the
contract must not grow members no loop actually uses.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from pymammotion.device.loop_host import LoopHost
from tests.unit._helpers import make_mock_handle

LOOP_MODULES = ("mqtt_loop", "ble_loop", "dynamics_line_loop")
DEVICE_DIR = pathlib.Path(LoopHost.__module__.replace(".", "/")).parent


def _protocol_members() -> set[str]:
    return {m for m in LoopHost.__protocol_attrs__ if not m.startswith("_")}


def _loop_accesses() -> dict[str, set[str]]:
    """Every ``handle.<attr>`` the loop modules read or call, per module."""
    found: dict[str, set[str]] = {}
    for name in LOOP_MODULES:
        tree = ast.parse((DEVICE_DIR / f"{name}.py").read_text())
        attrs = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "handle"
        }
        found[name] = attrs
    return found


@pytest.mark.parametrize("member", sorted(_protocol_members()))
def test_device_handle_supplies_every_contract_member(member: str) -> None:
    # Checked against an instance: device_name, iot_id and queue are set in __init__,
    # so they are absent from the class itself.
    handle = make_mock_handle()
    assert hasattr(handle, member), f"DeviceHandle is missing LoopHost.{member}"


def test_loops_touch_nothing_outside_the_contract() -> None:
    """A loop reaching past LoopHost is the drift this contract exists to catch."""
    members = _protocol_members()
    offenders = {
        module: sorted(attrs - members) for module, attrs in _loop_accesses().items() if attrs - members
    }
    assert not offenders, f"loops access members not declared on LoopHost: {offenders}"


def test_loops_touch_no_private_members() -> None:
    """The whole point: the host's privates are not part of the loops' interface."""
    offenders = {
        module: sorted(a for a in attrs if a.startswith("_"))
        for module, attrs in _loop_accesses().items()
        if any(a.startswith("_") for a in attrs)
    }
    assert not offenders, f"loops still reach into privates: {offenders}"


def test_contract_has_no_unused_members() -> None:
    """Every member should be earned by a real loop dependency, or it is dead weight."""
    used: set[str] = set()
    for attrs in _loop_accesses().values():
        used |= attrs
    unused = _protocol_members() - used
    assert not unused, f"LoopHost declares members no loop uses: {sorted(unused)}"
