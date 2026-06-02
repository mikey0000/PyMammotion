"""Regression: editing an area must not silently remove it when the root manifest is stale.

Reproduces the production sequence seen on Luba-VS563L6H.  A user edited an area,
which gave it a NEW content-based hash (e.g. 9054591478795832665).  The device
pushed ``toapp_all_hash_name`` listing the new hash, but our ``root_hash_lists``
still held the PRE-edit manifest.  The device's reported ``bol_hash`` no longer
matched our stored hashes — yet nothing wiped ``root_hash_lists``.  So the
per-frame prune in ``HashList.update`` (the AREA branch calls
``update_hash_lists(self.hashlist)``) dropped the freshly-arrived area geometry,
because its hash wasn't in the stale manifest.  The area was removed instead of
replaced in place.

Fix: when the area name list arrives, reconcile against the device's ``bol_hash``
and wipe ``root_hash_lists`` on a mismatch.  An empty manifest makes
``update_hash_lists`` a no-op (early return), so the new geometry survives until
the map saga re-fetches a fresh root hash list.
"""
from __future__ import annotations

import contextlib

from unittest.mock import AsyncMock

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import (
    CommDataCouple,
    HashList,
    NavGetCommData,
    NavGetHashListData,
)
from pymammotion.data.model.report_info import LocationData
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.proto import AppGetAllAreaHashName, AreaHashName, LubaMsg, MctlNav
from pymammotion.utility.mur_mur_hash import MurMurHashUtil

from ._helpers import make_command_builder

OLD_HASH = 111
NEW_HASH = 9054591478795832665


def _area_frame(hash_val: int) -> NavGetCommData:
    """One-frame AREA boundary (type=0 == PathType.AREA)."""
    return NavGetCommData(
        type=0,
        hash=hash_val,
        total_frame=1,
        current_frame=1,
        data_couple=[CommDataCouple(x=1.0, y=2.0)],
    )


def test_editing_area_does_not_remove_it_when_root_hash_list_is_stale() -> None:
    """An edited area's new hash must survive even though root_hash_lists is pre-edit."""
    device = MowerDevice(name="Luba-VS563L6H")

    # Pre-edit manifest: root_hash_lists still reports only OLD_HASH.
    device.map.update_root_hash_list(
        NavGetHashListData(sub_cmd=0, total_frame=1, current_frame=1, data_couple=[OLD_HASH])
    )
    # The device now reports a bol_hash for the post-edit area set; it no longer
    # matches our stored [OLD_HASH] manifest.
    device.report_data.locations = [LocationData(bol_hash=int(MurMurHashUtil.hash_unsigned_list([NEW_HASH])))]

    reducer = MowerStateReducer()

    # 1) Area name list arrives naming the edited area by its NEW hash. With the
    #    fix this reconciles against bol_hash and wipes the stale root manifest.
    device = reducer.apply(
        device,
        LubaMsg(
            nav=MctlNav(
                toapp_all_hash_name=AppGetAllAreaHashName(
                    hashnames=[AreaHashName(hash=NEW_HASH, name="Backyard part 1")]
                )
            )
        ),
    )

    # 2) The edited area's boundary geometry arrives (reducer forwards to map.update()).
    device.map.update(_area_frame(NEW_HASH))

    # The edited area must survive — replaced in place, not pruned against the
    # stale manifest.
    assert NEW_HASH in device.map.area, "edited area geometry was pruned against the stale root manifest"
    # And its name is present too.
    assert any(a.hash == NEW_HASH and a.name == "Backyard part 1" for a in device.map.area_name)

    # computed_areas (what HA renders) must surface the edited area by its new hash
    # with the correct name, and must not carry the pre-edit hash.
    computed = {a.hash: a.name for a in device.map.computed_areas}
    assert computed.get(NEW_HASH) == "Backyard part 1"
    assert OLD_HASH not in computed


def test_area_name_list_does_not_wipe_root_during_active_saga() -> None:
    """During a MapFetchSaga the reducer must NOT wipe root_hash_lists.

    The saga owns root freshness (it always re-fetches it) and the device may push
    toapp_all_hash_name mid-fetch.  Wiping then would empty find_incomplete_hashes
    and stop step 4 early, leaving area geometry unfetched.
    """
    device = MowerDevice(name="Luba-VS563L6H")
    device.map.update_root_hash_list(
        NavGetHashListData(sub_cmd=0, total_frame=1, current_frame=1, data_couple=[OLD_HASH])
    )
    # bol_hash mismatches the stored manifest — but a saga is in flight.
    device.report_data.locations = [LocationData(bol_hash=int(MurMurHashUtil.hash_unsigned_list([NEW_HASH])))]

    reducer = MowerStateReducer(is_saga_active=lambda: True)
    device = reducer.apply(
        device,
        LubaMsg(
            nav=MctlNav(
                toapp_all_hash_name=AppGetAllAreaHashName(
                    hashnames=[AreaHashName(hash=NEW_HASH, name="Backyard part 1")]
                )
            )
        ),
    )

    # Manifest must be left intact for the saga to finish its fetch.
    assert device.map.hashlist == [OLD_HASH]


# ---------------------------------------------------------------------------
# MapFetchSaga start-of-run bol_hash staleness check
# ---------------------------------------------------------------------------


def _stale_root_map() -> HashList:
    """A HashList whose root manifest is [OLD_HASH] (pre-edit)."""
    hl = HashList()
    hl.update_root_hash_list(
        NavGetHashListData(sub_cmd=0, total_frame=1, current_frame=1, data_couple=[OLD_HASH])
    )
    return hl


async def _run_saga_start_only(hl: HashList, bol_hash: int) -> None:
    """Run MapFetchSaga._run far enough to execute the start-of-run check, then abort.

    The first send (send_todev_ble_sync) is made to raise so the run unwinds right
    after the staleness check — which is all these tests exercise.
    """

    async def _send(_cmd: bytes) -> None:
        raise RuntimeError("stop after start-of-run check")

    saga = MapFetchSaga(
        device_id="d",
        device_name="Luba-VS563L6H",
        is_luba1=True,  # skip the area-name step; we only want the start-of-run check
        command_builder=make_command_builder(),
        send_command=_send,
        get_map=lambda: hl,
        get_bol_hash=lambda: bol_hash,
    )
    with contextlib.suppress(RuntimeError):
        await saga._run(AsyncMock())  # noqa: SLF001


async def test_saga_start_wipes_root_when_bol_hash_mismatches() -> None:
    """A stale root manifest (device bol_hash differs) is wiped at saga start."""
    hl = _stale_root_map()
    await _run_saga_start_only(hl, bol_hash=int(MurMurHashUtil.hash_unsigned_list([NEW_HASH])))
    assert hl.root_hash_lists == []


async def test_saga_start_keeps_root_when_bol_hash_matches() -> None:
    """An in-sync manifest must be preserved (so mid-fetch resume isn't lost)."""
    hl = _stale_root_map()
    in_sync = int(MurMurHashUtil.hash_unsigned_list(hl.area_root_hashlist))
    await _run_saga_start_only(hl, bol_hash=in_sync)
    assert hl.hashlist == [OLD_HASH]


async def test_saga_start_keeps_root_when_bol_hash_unknown() -> None:
    """A device that hasn't reported a bol_hash (0) must not trigger a wipe."""
    hl = _stale_root_map()
    await _run_saga_start_only(hl, bol_hash=0)
    assert hl.hashlist == [OLD_HASH]
