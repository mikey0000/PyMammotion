"""Grass-collector bits of ``DeviceData.sensor_status``.

The APK splits the packed ``sensor_status`` long into 3-bit fields; the
collector (sweep) state sits at bits 24-26 and the bin-tipping (dump) state at
bits 27-29 (``MACarDataManager.java`` ``(sensorStatus >> 24) & 7`` and
``>> 27``).  These tests pin the shifts and the value mapping.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.enums import CollectorState, DumpState
from pymammotion.data.model.report_info import DeviceData


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, CollectorState.IDLE),
        (1, CollectorState.COLLECTING),
        (2, CollectorState.FAULT),
        (3, CollectorState.FAULT),
        (7, CollectorState.FAULT),
    ],
)
def test_collector_state_reads_bits_24_to_26(raw: int, expected: CollectorState) -> None:
    """The app treats everything above COLLECTING as a collection failure."""
    assert DeviceData(sensor_status=raw << 24).collector_state is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, DumpState.LOWERED),
        (1, DumpState.RAISED),
        (2, DumpState.ADJUSTING),
        (3, DumpState.POURING),
        (5, DumpState.UNKNOWN),
    ],
)
def test_dump_state_reads_bits_27_to_29(raw: int, expected: DumpState) -> None:
    """Unmodelled codes fall back to UNKNOWN rather than raising."""
    assert DeviceData(sensor_status=raw << 27).dump_state is expected


def test_collector_and_dump_bits_do_not_bleed_into_each_other() -> None:
    """Both fields decode independently out of one packed frame."""
    dev = DeviceData(sensor_status=(1 << 24) | (3 << 27))
    assert dev.collector_state is CollectorState.COLLECTING
    assert dev.dump_state is DumpState.POURING


def test_neighbouring_sensor_fields_are_untouched() -> None:
    """Setting the collector bits leaves the bumper and ultrasonic states alone."""
    dev = DeviceData(sensor_status=(2 << 24) | (2 << 27))
    assert dev.bumper_state == 0
    assert dev.blade_state == 0
    assert dev.ult_right == 0


def test_collector_installed_follows_the_installation_status() -> None:
    """The app gates every sweep/dump control on this flag."""
    dev = DeviceData()
    assert dev.collector_installed is False
    dev.collector_status.collector_installation_status = 1
    assert dev.collector_installed is True
