"""Tests for MapFetchSaga — type=26 (VISUAL_OBSTACLE_ZONE) must be stored, not skipped."""
from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import MagicMock


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


def _comm_data_msg(hash_id: int, type_code: int) -> LubaMsg:
    """Build a LubaMsg carrying a single-frame toapp_get_commondata_ack."""
    return LubaMsg(
        nav=MctlNav(
            toapp_get_commondata_ack=NavGetCommDataAck(
                pver=1,
                action=8,
                type=type_code,
                hash=hash_id,
                total_frame=1,
                current_frame=1,
            )
        )
    )


async def _run_saga_with_messages(
    broker: DeviceMessageBroker,
    saga: MapFetchSaga,
    messages: list[LubaMsg],
    delay: float = 0.02,
) -> None:
    """Drive saga + sequential message injection concurrently."""

    async def _inject() -> None:
        for msg in messages:
            await asyncio.sleep(delay)
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

    saga = MapFetchSaga(
        device_id="dev-1",
        device_name="Luba-Test",
        is_luba1=True,  # skip area-names step
        command_builder=_make_command_builder(),
        send_command=send_command,
    )

    hash_id = 1640341264244214677

    await _run_saga_with_messages(
        broker,
        saga,
        messages=[
            _hash_list_msg([hash_id]),
            _comm_data_msg(hash_id, type_code=0),  # PathType.AREA
        ],
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

    saga = MapFetchSaga(
        device_id="dev-2",
        device_name="Luba-Test",
        is_luba1=True,
        command_builder=_make_command_builder(),
        send_command=send_command,
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

    saga = MapFetchSaga(
        device_id="dev-3",
        device_name="Luba-Test",
        is_luba1=True,
        command_builder=_make_command_builder(),
        send_command=send_command,
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
        ),
        timeout=5.0,
    )

    assert saga.result is not None
    assert area_hash in saga.result.area
    assert unknown_hash in saga.result.visual_obstacle_zone
    assert saga._command_builder.synchronize_hash_data.call_count == 2  # noqa: SLF001