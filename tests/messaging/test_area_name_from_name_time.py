"""Regression tests for area naming — name_time.name priority over numbered fallbacks.

The bug: when toapp_all_hash_name returns no names (or omits some areas), the
fallback generators in state_reducer and map_saga would assign "area 1", "area 2"
etc., ignoring the name_time.name field already present on every fetched frame.
This caused area names to flip between the correct user-assigned name and the
numbered fallback depending on message ordering.

Fixed behaviour: both fallback generators prefer name_time.name when non-empty.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import (
    AreaHashNameList,
    CommDataCouple,
    FrameList,
    HashList,
    NavGetCommData,
    NavNameTime,
)
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import AppGetAllAreaHashName, AreaHashName, LubaMsg, MctlNav


# ---------------------------------------------------------------------------
# FrameList.name property
# ---------------------------------------------------------------------------


class TestFrameListName:
    def test_returns_name_time_name_when_set(self) -> None:
        frame = NavGetCommData(name_time=NavNameTime(name="Voor", create_time=1, modify_time=1))
        fl = FrameList(data=[frame])
        assert fl.name == "Voor"

    def test_returns_empty_when_name_time_name_is_empty(self) -> None:
        frame = NavGetCommData(name_time=NavNameTime(name="", create_time=0, modify_time=0))
        fl = FrameList(data=[frame])
        assert fl.name == ""

    def test_returns_empty_when_no_data(self) -> None:
        fl = FrameList()
        assert fl.name == ""

    def test_uses_first_frame_only(self) -> None:
        """name_time.name from the first frame wins even if later frames differ."""
        fl = FrameList(
            data=[
                NavGetCommData(name_time=NavNameTime(name="First")),
                NavGetCommData(name_time=NavNameTime(name="Second")),
            ]
        )
        assert fl.name == "First"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_area_frame(hash_val: int, name: str) -> NavGetCommData:
    return NavGetCommData(
        hash=hash_val,
        total_frame=1,
        current_frame=1,
        name_time=NavNameTime(name=name, create_time=1, modify_time=1),
        data_couple=[CommDataCouple(x=0.0, y=0.0)],
    )


def _make_device_with_named_areas(areas: dict[int, str]) -> MowerDevice:
    """Build a MowerDevice whose area dict has frames with name_time.name set."""
    device = MowerDevice(name="Test-Mower")
    for hash_val, name in areas.items():
        device.map.area[hash_val] = FrameList(data=[_make_area_frame(hash_val, name)])
    return device


# ---------------------------------------------------------------------------
# state_reducer: toapp_all_hash_name with empty hashnames
# ---------------------------------------------------------------------------


class TestStateReducerAreaNameFallback:
    def _apply_empty_hash_name(self, device: MowerDevice) -> MowerDevice:
        """Apply a toapp_all_hash_name message with no entries."""
        reducer = MowerStateReducer()
        msg = LubaMsg(
            nav=MctlNav(
                toapp_all_hash_name=AppGetAllAreaHashName(hashnames=[]),
            )
        )
        return reducer.apply(device, msg)

    def _apply_hash_name_with_entries(
        self, device: MowerDevice, entries: list[tuple[int, str]]
    ) -> MowerDevice:
        reducer = MowerStateReducer()
        msg = LubaMsg(
            nav=MctlNav(
                toapp_all_hash_name=AppGetAllAreaHashName(
                    hashnames=[AreaHashName(hash=h, name=n) for h, n in entries]
                )
            )
        )
        return reducer.apply(device, msg)

    def test_uses_name_time_name_when_hashnames_empty(self) -> None:
        """When the device returns no hash names, name_time.name takes priority."""
        device = _make_device_with_named_areas({111: "Voor", 222: "Achter"})
        result = self._apply_empty_hash_name(device)
        by_hash = {a.hash: a.name for a in result.map.area_name}
        assert by_hash[111] == "Voor"
        assert by_hash[222] == "Achter"

    def test_falls_back_to_numbered_when_name_time_name_empty(self) -> None:
        """When name_time.name is blank, numbered fallbacks are still used."""
        device = _make_device_with_named_areas({111: "", 222: ""})
        result = self._apply_empty_hash_name(device)
        by_hash = {a.hash: a.name for a in result.map.area_name}
        # Sorted hashes: 111 → "area 1", 222 → "area 2"
        assert by_hash[111] == "area 1"
        assert by_hash[222] == "area 2"

    def test_mixed_named_and_unnamed_areas(self) -> None:
        """Named frames use their name; unnamed frames get numbered fallbacks."""
        device = _make_device_with_named_areas({111: "Voor", 222: ""})
        result = self._apply_empty_hash_name(device)
        by_hash = {a.hash: a.name for a in result.map.area_name}
        assert by_hash[111] == "Voor"
        assert by_hash[222] == "area 2"

    def test_explicit_hashnames_win_over_name_time(self) -> None:
        """When the device returns explicit names, those take priority."""
        device = _make_device_with_named_areas({111: "Voor"})
        result = self._apply_hash_name_with_entries(device, [(111, "Front Lawn")])
        by_hash = {a.hash: a.name for a in result.map.area_name}
        assert by_hash[111] == "Front Lawn"

    def test_name_does_not_flip_on_repeated_empty_hash_name(self) -> None:
        """Applying toapp_all_hash_name with empty names repeatedly must not flip the name."""
        device = _make_device_with_named_areas({111: "Voor", 222: "Achter"})
        reducer = MowerStateReducer()
        msg = LubaMsg(nav=MctlNav(toapp_all_hash_name=AppGetAllAreaHashName(hashnames=[])))
        for _ in range(5):
            device = reducer.apply(device, msg)
        by_hash = {a.hash: a.name for a in device.map.area_name}
        assert by_hash[111] == "Voor"
        assert by_hash[222] == "Achter"


# ---------------------------------------------------------------------------
# map_saga fallback after full sync
# ---------------------------------------------------------------------------


class TestMapSagaAreaNameFallback:
    """Test the fallback name generation in MapFetchSaga._run."""

    def test_uses_name_time_name_when_area_name_empty(self) -> None:
        """After a full map sync with no area_name, name_time.name is preferred."""
        from pymammotion.data.model.hash_list import HashList

        current_map = HashList()
        current_map.area[111] = FrameList(data=[_make_area_frame(111, "Voor")])
        current_map.area[222] = FrameList(data=[_make_area_frame(222, "Achter")])
        # area_name is empty → simulate the map_saga fallback path directly
        assert not current_map.area_name
        current_map.area_name = [
            AreaHashNameList(name=current_map.area[h].name or f"area {i + 1}", hash=h)
            for i, h in enumerate(sorted(current_map.area.keys()))
        ]
        by_hash = {a.hash: a.name for a in current_map.area_name}
        assert by_hash[111] == "Voor"
        assert by_hash[222] == "Achter"

    def test_numbered_fallback_when_name_time_empty(self) -> None:
        current_map = HashList()
        current_map.area[111] = FrameList(data=[_make_area_frame(111, "")])
        current_map.area[222] = FrameList(data=[_make_area_frame(222, "")])
        current_map.area_name = [
            AreaHashNameList(name=current_map.area[h].name or f"area {i + 1}", hash=h)
            for i, h in enumerate(sorted(current_map.area.keys()))
        ]
        by_hash = {a.hash: a.name for a in current_map.area_name}
        assert by_hash[111] == "area 1"
        assert by_hash[222] == "area 2"

    def test_skips_fallback_when_area_name_already_set(self) -> None:
        """If area_name is already populated the fallback must not overwrite it."""
        current_map = HashList()
        current_map.area[111] = FrameList(data=[_make_area_frame(111, "Voor")])
        current_map.area_name = [AreaHashNameList(name="Existing", hash=111)]
        # Simulate the guard: `if not current_map.area_name and current_map.area`
        if not current_map.area_name and current_map.area:
            current_map.area_name = [
                AreaHashNameList(name=current_map.area[h].name or f"area {i + 1}", hash=h)
                for i, h in enumerate(sorted(current_map.area.keys()))
            ]
        assert current_map.area_name[0].name == "Existing"
