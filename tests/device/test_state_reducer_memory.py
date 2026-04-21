"""Demonstrates the memory allocation growth bug from #125.

Every nav sub-message deep-copies the HashList regardless of whether the
sub-message actually writes to the map. This test holds references to each
produced snapshot (mimicking debounce buses / HA coordinators / subscribers)
and asserts the total heap growth stays bounded across many nav_sys_param_cmd
messages that never touch the map.

On the leaky implementation, every apply() produces a new, fully distinct
HashList containing fresh copies of every CommDataCouple — the held snapshots
retain them all and total memory grows linearly with iteration count.
"""

from __future__ import annotations

import gc
import tracemalloc

from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.hash_list import CommDataCouple, NavGetCommData
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.proto import LubaMsg, MctlNav, NavSysParamMsg


def _make_device_with_large_map(points_per_frame: int = 500) -> MowerDevice:
    """Build a device with a realistic-size HashList."""
    device = MowerDevice(name="Luba-Test")
    frame = NavGetCommData(
        pver=0,
        sub_cmd=0,
        action=0,
        type=0,
        hash=123,
        total_frame=1,
        current_frame=1,
        data_hash=0,
        data_len=points_per_frame,
        data_couple=[CommDataCouple(x=float(i), y=float(i)) for i in range(points_per_frame)],
    )
    device.map.area[123] = [frame]
    return device


def test_retained_snapshots_do_not_balloon_on_nav_sys_param() -> None:
    """nav_sys_param_cmd writes only mower_state; retained snapshots must share the map.

    When subscribers retain snapshots (debounce bus, state machine history,
    HA coordinator .data), the deep-copy cost per message is paid per-snapshot.
    A correct reducer shares the HashList across snapshots, so holding N
    snapshots costs O(1) map memory, not O(N).
    """
    points = 500
    iterations = 200
    reducer = MowerStateReducer()
    current = _make_device_with_large_map(points_per_frame=points)
    msg = LubaMsg(nav=MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=3, context=1)))

    # Warm up: process a few messages to let any one-time allocations settle.
    for _ in range(3):
        current = reducer.apply(current, msg)

    gc.collect()
    tracemalloc.start()
    baseline_bytes, _ = tracemalloc.get_traced_memory()

    retained: list[MowerDevice] = []
    for _ in range(iterations):
        current = reducer.apply(current, msg)
        retained.append(current)

    final_bytes, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    growth_bytes = final_bytes - baseline_bytes

    # Leaky implementation: each retained snapshot has its own CommDataCouple
    # list (500 points * ~100-200 bytes) — 200 snapshots * 500 * 150 ≈ 15 MiB.
    # Correct implementation: map is shared across all retained snapshots — a
    # per-snapshot overhead of just mower_state (small) is all that accrues.
    max_allowed_growth_bytes = 2 * 1024 * 1024  # 2 MiB budget for 200 snapshots
    assert growth_bytes < max_allowed_growth_bytes, (
        f"Heap grew {growth_bytes / 1024 / 1024:.1f} MiB across {iterations} "
        f"retained snapshots of nav_sys_param_cmd with a {points}-point map — "
        f"HashList is being deep-copied into every snapshot (#125)"
    )
