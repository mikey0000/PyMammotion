"""Regression tests for the toapp_all_hash_name handler in MowerStateManager.

These cover SITE G: the legacy ``toapp_all_hash_name`` branch in
``MowerStateManager._update_nav_data`` which previously did wholesale replace
with no guard.  When the device returned an empty ``hashnames=[]`` payload
that silently emptied ``device.map.area_name``.

Fixed behaviour (per user decision):
  * empty payload → leave ``area_name`` alone
  * non-empty payload → wholesale replace (user OK'd this — fresh data wins)
"""

from __future__ import annotations

import asyncio

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.model.hash_list import AreaHashNameList
from pymammotion.data.mower_state_manager import MowerStateManager
from pymammotion.proto import AppGetAllAreaHashName, AreaHashName, LubaMsg, MctlNav


def _make_msg(hashnames: list[tuple[int, str]]) -> LubaMsg:
    """Build a real LubaMsg containing a toapp_all_hash_name payload."""
    payload = AppGetAllAreaHashName(
        device_id="dev-001",
        hashnames=[AreaHashName(hash=h, name=n) for h, n in hashnames],
    )
    nav = MctlNav(toapp_all_hash_name=payload)
    return LubaMsg(nav=nav)


class TestToappAllHashNameHandler:
    def test_empty_payload_does_not_wipe(self) -> None:
        """An empty hashnames list from the device must not clobber existing names."""
        device = MowingDevice()
        device.map.area_name = [AreaHashNameList(name="Front", hash=100)]
        manager = MowerStateManager(device)

        msg = _make_msg([])
        asyncio.run(manager.notification(msg))

        assert len(device.map.area_name) == 1
        assert device.map.area_name[0].name == "Front"
        assert device.map.area_name[0].hash == 100

    def test_nonempty_payload_replaces(self) -> None:
        """Non-empty payload performs wholesale replace (per user decision)."""
        device = MowingDevice()
        device.map.area_name = [AreaHashNameList(name="Old", hash=100)]
        manager = MowerStateManager(device)

        msg = _make_msg([(100, "NewFront")])
        asyncio.run(manager.notification(msg))

        names_by_hash = {a.hash: a.name for a in device.map.area_name}
        assert names_by_hash == {100: "NewFront"}

    def test_nonempty_payload_replaces_completely(self) -> None:
        """Replace is wholesale: orphans not in the new payload are dropped."""
        device = MowingDevice()
        device.map.area_name = [
            AreaHashNameList(name="Front", hash=100),
            AreaHashNameList(name="Back", hash=200),
        ]
        manager = MowerStateManager(device)

        msg = _make_msg([(100, "Front"), (300, "Side")])
        asyncio.run(manager.notification(msg))

        names_by_hash = {a.hash: a.name for a in device.map.area_name}
        assert names_by_hash == {100: "Front", 300: "Side"}
