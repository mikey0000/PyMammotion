"""Tests for MapFetchSaga — type=26 (VISUAL_OBSTACLE_ZONE) must be stored, not skipped."""
from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import MagicMock

import betterproto2

from pymammotion.data.model.hash_list import HashList, NavGetCommData, NavGetHashListData
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.map_saga import MapFetchSaga
from pymammotion.proto import LubaMsg, MctlNav, NavGetCommDataAck, NavGetHashListAck


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_command_builder() -> MagicMock:
    """Minimal command-builder double — just returns empty bytes for every call."""
    cb = MagicMock()
    cb.get_area_name_list.return_value = b""
    cb.get_all_boundary_hash_list.return_value = b""
    cb.synchronize_hash_data.return_value = b""
    cb.get_regional_data.return_value = b""
    return cb


def _hash_list_msg(hash_ids: list[int]) -> LubaMsg:
    """Build a LubaMsg carrying a single-frame toapp_gethash_ack with the given hash IDs."""
    return LubaMsg(
        nav=MctlNav(
            toapp_gethash_ack=NavGetHashListAck(
                pver=1,
                sub_cmd=0,
                total_frame=1,
                current_frame=1,
                data_couple=hash_ids,
            )
        )
    )


def _comm_data_msg(
    hash_id: int,
    type_code: int,
    *,
    current_frame: int = 1,
    total_frame: int = 1,
    paternal_hash_a: int = 0,
) -> LubaMsg:
    """Build a LubaMsg carrying a single-frame toapp_get_commondata_ack."""
    return LubaMsg(
        nav=MctlNav(
            toapp_get_commondata_ack=NavGetCommDataAck(
                pver=1,
                action=8,
                type=type_code,
                hash=hash_id,
                total_frame=total_frame,
                current_frame=current_frame,
                paternal_hash_a=paternal_hash_a,
            )
        )
    )


def _apply_msg_to_map(msg: LubaMsg, m: HashList) -> None:
    """Minimal StateReducer simulation: update m with each incoming nav message."""
    if not msg.nav:
        return
    try:
        leaf_name, leaf_val = betterproto2.which_one_of(msg.nav, "SubNavMsg")
        if leaf_name == "toapp_gethash_ack":
            m.update_root_hash_list(NavGetHashListData.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE)))
        elif leaf_name == "toapp_get_commondata_ack":
            m.update(NavGetCommData.from_dict(leaf_val.to_dict(casing=betterproto2.Casing.SNAKE)))
    except Exception:  # noqa: BLE001
        pass


async def _run_saga_with_messages(
    broker: DeviceMessageBroker,
    saga: MapFetchSaga,
    messages: list[LubaMsg],
    delay: float = 0.02,
    map_update: HashList | None = None,
) -> None:
    """Drive saga + sequential message injection concurrently.

    If *map_update* is provided, each message is also applied to that HashList
    to simulate the StateReducer updating device.map before the saga reads it.
    """

    async def _inject() -> None:
        for msg in messages:
            await asyncio.sleep(delay)
            if map_update is not None:
                _apply_msg_to_map(msg, map_update)
            await broker.on_message(msg)

    injector = asyncio.create_task(_inject())
    try:
        await saga.execute(broker)
    finally:
        injector.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await injector


# ---------------------------------------------------------------------------
# test 1 — known type (area=0): saga stores data and terminates normally
# ---------------------------------------------------------------------------


async def test_saga_terminates_with_known_type() -> None:
    """Saga must complete and store data when the device returns a known type (0=AREA)."""
    broker = DeviceMessageBroker()
    sends: list[bytes] = []

    async def send_command(cmd: bytes) -> None:
        sends.append(cmd)

    _map = HashList()
    saga = MapFetchSaga(
        device_id="dev-1",
        device_name="Luba-Test",
        is_luba1=True,  # skip area-names step
        command_builder=_make_command_builder(),
        send_command=send_command,
        get_map=lambda: _map,
    )

    hash_id = 1640341264244214677

    await _run_saga_with_messages(
        broker,
        saga,
        messages=[
            _hash_list_msg([hash_id]),
            _comm_data_msg(hash_id, type_code=0),  # PathType.AREA
        ],
        map_update=_map,
    )

    assert saga.result is not None
    assert hash_id in saga.result.area


# ---------------------------------------------------------------------------
# test 2 — unknown type (26): saga must NOT loop forever; it should complete
# ---------------------------------------------------------------------------


async def test_saga_does_not_loop_on_unknown_type() -> None:
    """Saga must store type=26 (VISUAL_OBSTACLE_ZONE) and not re-request the hash.

    Regression test: before VISUAL_OBSTACLE_ZONE was added to PathType/HashList,
    update() returned False for type=26 so the hash was never stored, causing
    missing_hashlist() to keep returning it and the saga to loop indefinitely.
    """
    broker = DeviceMessageBroker()
    sends: list[bytes] = []

    async def send_command(cmd: bytes) -> None:
        sends.append(cmd)

    _map = HashList()
    saga = MapFetchSaga(
        device_id="dev-2",
        device_name="Luba-Test",
        is_luba1=True,
        command_builder=_make_command_builder(),
        send_command=send_command,
        get_map=lambda: _map,
    )

    hash_id = 1640341264244214677

    # Only one comm-data message is injected — the saga must not ask for it again
    await asyncio.wait_for(
        _run_saga_with_messages(
            broker,
            saga,
            messages=[
                _hash_list_msg([hash_id]),
                _comm_data_msg(hash_id, type_code=26),  # unknown / unhandled type
            ],
            map_update=_map,
        ),
        timeout=5.0,  # would hang indefinitely before the fix
    )

    assert saga.result is not None
    # type=26 → VISUAL_OBSTACLE_ZONE — must be stored in the correct dict
    assert hash_id in saga.result.visual_obstacle_zone
    assert hash_id not in saga.result.area
    assert hash_id not in saga.result.obstacle
    assert hash_id not in saga.result.path

    # The device should have been asked exactly once for hash data (not re-requested)
    synchronize_calls = saga._command_builder.synchronize_hash_data.call_count  # noqa: SLF001
    assert synchronize_calls == 1, f"Expected 1 synchronize call, got {synchronize_calls}"


# ---------------------------------------------------------------------------
# test 3 — mixed: one known + one unknown type; known is stored, unknown is skipped
# ---------------------------------------------------------------------------


async def test_saga_stores_known_and_skips_unknown_types() -> None:
    """When two hashes are present — one AREA (type=0) and one VISUAL_OBSTACLE_ZONE (type=26) —
    both are stored in their respective dicts."""
    broker = DeviceMessageBroker()
    sends: list[bytes] = []

    async def send_command(cmd: bytes) -> None:
        sends.append(cmd)

    _map = HashList()
    saga = MapFetchSaga(
        device_id="dev-3",
        device_name="Luba-Test",
        is_luba1=True,
        command_builder=_make_command_builder(),
        send_command=send_command,
        get_map=lambda: _map,
    )

    area_hash = 1111111111111111111
    unknown_hash = 2222222222222222222

    await asyncio.wait_for(
        _run_saga_with_messages(
            broker,
            saga,
            messages=[
                _hash_list_msg([area_hash, unknown_hash]),
                _comm_data_msg(area_hash, type_code=0),    # PathType.AREA — stored
                _comm_data_msg(unknown_hash, type_code=26),  # unknown — skipped
            ],
            map_update=_map,
        ),
        timeout=5.0,
    )

    assert saga.result is not None
    assert area_hash in saga.result.area
    assert unknown_hash in saga.result.visual_obstacle_zone
    assert saga._command_builder.synchronize_hash_data.call_count == 2  # noqa: SLF001


# ---------------------------------------------------------------------------
# test 4 — virtual wall (21) + corridor line (19) + corridor point (20) are stored
# ---------------------------------------------------------------------------


async def test_saga_stores_virtual_wall_and_corridor_types() -> None:
    """Regression test for types 19, 20, 21.

    Before these types were added to ``PathType`` / ``HashList``,
    ``HashList.update`` returned False for them so each frame was dropped and
    the saga looped re-requesting the same hash.  After the fix each type
    lands in its dedicated dict and the saga completes.
    """
    broker = DeviceMessageBroker()
    sends: list[bytes] = []

    async def send_command(cmd: bytes) -> None:
        sends.append(cmd)

    _map = HashList()
    saga = MapFetchSaga(
        device_id="dev-4",
        device_name="Luba-Test",
        is_luba1=True,
        command_builder=_make_command_builder(),
        send_command=send_command,
        get_map=lambda: _map,
    )

    corridor_line_hash = 3000000000000000001
    corridor_point_hash = 3000000000000000002
    virtual_wall_hash = 3000000000000000003

    await asyncio.wait_for(
        _run_saga_with_messages(
            broker,
            saga,
            messages=[
                _hash_list_msg([corridor_line_hash, corridor_point_hash, virtual_wall_hash]),
                _comm_data_msg(corridor_line_hash, type_code=19),   # CORRIDOR_LINE
                _comm_data_msg(corridor_point_hash, type_code=20),  # CORRIDOR_POINT
                _comm_data_msg(virtual_wall_hash, type_code=21),    # VIRTUAL_WALL
            ],
            map_update=_map,
        ),
        timeout=5.0,
    )

    assert saga.result is not None
    assert corridor_line_hash in saga.result.corridor_line
    assert corridor_point_hash in saga.result.corridor_point
    assert virtual_wall_hash in saga.result.virtual_wall
    # Each type must be routed to exactly its own dict — not to a sibling.
    assert corridor_line_hash not in saga.result.virtual_wall
    assert virtual_wall_hash not in saga.result.corridor_line
    # Saga should have asked for each hash exactly once.
    assert saga._command_builder.synchronize_hash_data.call_count == 3  # noqa: SLF001


# ---------------------------------------------------------------------------
# Regression tests for LUBA_VA log incident 2026-05-22
# ---------------------------------------------------------------------------


async def test_saga_acks_unrelated_dynamics_line_frame() -> None:
    """type=18 frames arriving mid-fetch must be acked, not silently dropped.

    Regression for HA log 2026-05-22: LUBA_VA was spontaneously sending
    dynamics_line (type=18, no hash) frames while MapFetchSaga was waiting on
    area data.  The saga's hash-filter dropped them without acking, so the
    device kept retransmitting with incrementing ``dataHash``, eventually
    starving the actual area-data response and timing out.

    Mirrors APK ``HashDataManager.setRegionalData`` (HashDataManager.java:1219)
    which acks every non-duplicate frame regardless of hash.
    """
    broker = DeviceMessageBroker()
    sends: list[bytes] = []

    async def send_command(cmd: bytes) -> None:
        sends.append(cmd)

    _map = HashList()
    cb = _make_command_builder()
    saga = MapFetchSaga(
        device_id="dev-luba-va",
        device_name="Luba-VAAAYRNG",
        is_luba1=True,
        command_builder=cb,
        send_command=send_command,
        get_map=lambda: _map,
    )

    area_hash = 5829472998950549898

    await asyncio.wait_for(
        _run_saga_with_messages(
            broker,
            saga,
            messages=[
                _hash_list_msg([area_hash]),
                # Dynamics-line frame arrives BEFORE the area frame — saga must
                # ack it even though it doesn't match the current hash.
                _comm_data_msg(0, type_code=18),
                _comm_data_msg(area_hash, type_code=0),
            ],
            map_update=_map,
        ),
        timeout=5.0,
    )

    # The dynamics-line frame must have been acked via get_regional_data.
    # Total acks expected: 1 hash-list-ack + 1 unrelated-dynamics ack +
    # 1 area-data ack = 2 get_regional_data calls (hash-list uses a different builder).
    assert cb.get_regional_data.call_count >= 2, (
        f"saga must ack unrelated dynamics_line frames; "
        f"got only {cb.get_regional_data.call_count} get_regional_data calls"
    )
    assert saga.result is not None
    assert area_hash in saga.result.area


async def test_saga_advances_on_unknown_type_single_frame() -> None:
    """Saga must advance current_hash after receiving a single-frame transaction
    of an unknown type (e.g. radar-only type=23 observed on LUBA_VA).

    Regression for HA log: device returned type=23 single-frame for a hash that
    pymammotion's PathType didn't model.  The frame was dropped at update(),
    find_incomplete_hashes kept reporting the hash as missing, and the saga
    looped re-requesting it indefinitely.  Fixed by:
    (a) HashList stores unknown types in unknown_type_frames, and
    (b) saga tracks addressed_hashes locally to advance even if the data
        layer hadn't classified the type.
    """
    broker = DeviceMessageBroker()
    sends: list[bytes] = []

    async def send_command(cmd: bytes) -> None:
        sends.append(cmd)

    _map = HashList()
    cb = _make_command_builder()
    saga = MapFetchSaga(
        device_id="dev-luba-va-2",
        device_name="Luba-VAAAYRNG",
        is_luba1=True,
        command_builder=cb,
        send_command=send_command,
        get_map=lambda: _map,
    )

    # Two hashes — the first responds with a totally unknown type=99 single
    # frame, the second with a known type=0 (AREA).  Saga must advance past
    # the first and complete.
    unknown_hash = 2284403252077069651
    area_hash = 5829472998950549898

    await asyncio.wait_for(
        _run_saga_with_messages(
            broker,
            saga,
            messages=[
                _hash_list_msg([unknown_hash, area_hash]),
                _comm_data_msg(unknown_hash, type_code=99),  # never-modelled
                _comm_data_msg(area_hash, type_code=0),
            ],
            map_update=_map,
        ),
        timeout=5.0,
    )

    assert saga.result is not None
    # Saga must have advanced past unknown_hash and fetched area_hash.
    assert area_hash in saga.result.area
    # Each hash requested exactly once — no re-request loop.
    assert cb.synchronize_hash_data.call_count == 2, (
        f"saga looped on unknown type; expected 2 synchronize_hash_data calls, "
        f"got {cb.synchronize_hash_data.call_count}"
    )


async def test_saga_advances_on_radar_no_go_zone_single_frame() -> None:
    """Same shape as the unknown-type test but with PathType.NO_GO_ZONE (23),
    which we now explicitly model.  Verifies the known-type path also advances
    cleanly on a single-frame radar element."""
    broker = DeviceMessageBroker()

    async def send_command(cmd: bytes) -> None:
        pass

    _map = HashList()
    cb = _make_command_builder()
    saga = MapFetchSaga(
        device_id="dev-radar",
        device_name="Luba-VAAAYRNG",
        is_luba1=True,
        command_builder=cb,
        send_command=send_command,
        get_map=lambda: _map,
    )

    no_go_hash = 2284403252077069651
    area_hash = 5829472998950549898

    await asyncio.wait_for(
        _run_saga_with_messages(
            broker,
            saga,
            messages=[
                _hash_list_msg([no_go_hash, area_hash]),
                _comm_data_msg(no_go_hash, type_code=23),  # NO_GO_ZONE
                _comm_data_msg(area_hash, type_code=0),
            ],
            map_update=_map,
        ),
        timeout=5.0,
    )

    assert saga.result is not None
    assert no_go_hash in saga.result.no_go_zone
    assert area_hash in saga.result.area
    assert cb.synchronize_hash_data.call_count == 2
