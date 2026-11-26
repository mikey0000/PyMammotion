"""The app's "use trimmer": byte 2 of ``reserved2``, read from a stored plan and from the running task.

The app (2.3.28.31) keeps it as ``OperationModeDB.use_trimmer`` (RN ``autoHitLine``), 0 meaning use the trimmer
and the default.  ``getReserved2`` writes it raw into byte 2 of the 32-byte buffer that also carries
auto-reverse in byte 0; the device echoes it +10 and ``HorseWorkSettingHelper.toOperationModeDB`` reads it back
with ``decodeLegacyOrRaw`` from buffers longer than two bytes.
"""

from __future__ import annotations

import pytest

from pymammotion.data.model.hash_list import Plan
from pymammotion.data.model.work import CurrentTaskSettings
from tests._helpers import NEWER_MODEL_NAME, make_stored_plan_frame
from tests.unit.data.model._helpers import make_task_settings, make_wire_field

_BUFFERS = pytest.mark.parametrize(
    ("reserved2", "auto_change_direction", "use_trimmer"),
    [
        pytest.param([10, 10, 10] + [10] * 29, False, True, id="echo-on"),
        pytest.param([11, 10, 11] + [10] * 29, True, False, id="echo-off-with-auto-reverse"),
        pytest.param([0, 0, 1] + [0] * 29, False, False, id="raw-off"),
        pytest.param([0, 0, 0] + [0] * 29, False, True, id="raw-on"),
        pytest.param([11, 10, 5] + [10] * 29, True, None, id="unknown-value"),
        pytest.param([11, 10], True, None, id="too-short"),
    ],
)


@_BUFFERS
def test_a_stored_plan_reads_use_trimmer_beside_auto_reverse(
    reserved2: list[int], auto_change_direction: bool, use_trimmer: bool | None
) -> None:
    """Both settings come out of the one field-41 buffer, each from its own byte."""
    plan = Plan.from_wire(make_stored_plan_frame(reserved2=reserved2), NEWER_MODEL_NAME)

    assert (plan.auto_change_direction, plan.use_trimmer) == (auto_change_direction, use_trimmer)


@_BUFFERS
def test_the_running_task_reads_use_trimmer_from_field_21(
    reserved2: list[int], auto_change_direction: bool, use_trimmer: bool | None
) -> None:
    """The running task's field 21 is decoded by the same rule as a plan's field 41."""
    settings = make_task_settings(make_wire_field(21, 2, bytes([len(reserved2), *reserved2])))

    assert (settings.auto_change_direction, settings.use_trimmer) == (auto_change_direction, use_trimmer)


def test_a_plan_without_reserved2_reports_no_use_trimmer() -> None:
    """None, not on: the caller decides what an unreported setting sends."""
    assert Plan.from_wire(make_stored_plan_frame(), NEWER_MODEL_NAME).use_trimmer is None


@pytest.mark.parametrize("model", [Plan, CurrentTaskSettings])
@pytest.mark.parametrize("reported", [True, False, None])
def test_use_trimmer_survives_a_serialisation_round_trip(
    model: type[Plan | CurrentTaskSettings], reported: bool | None
) -> None:
    """Both are persisted decoded, with ``auto_change_direction`` already a bool, so neither may re-decode."""
    saved = model(auto_change_direction=True, use_trimmer=reported)

    restored = model.from_dict(saved.to_dict())

    assert (restored.auto_change_direction, restored.use_trimmer) == (True, reported)


@pytest.mark.parametrize("model", [Plan, CurrentTaskSettings])
def test_a_model_saved_before_use_trimmer_existed_still_loads(
    model: type[Plan | CurrentTaskSettings],
) -> None:
    """Restoring a device cached by an older release must not fail on the missing key."""
    saved = model(auto_change_direction=True).to_dict()
    saved.pop("use_trimmer")

    assert model.from_dict(saved).use_trimmer is None
