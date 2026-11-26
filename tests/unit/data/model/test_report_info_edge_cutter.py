"""``DeviceData.edge_cutter_installed``: the edge cutter (trimmer) the app requires before offering "use trimmer".

The app sets ``hasBeatEdgeModule`` from ``rpt_dev_status.edge_cutter_status.edge_cutter_installation_status == 1``
(``MACarDataManager.setMediumPacket``) and shows the row only with it and the model's schema showing code 40.
"""

from __future__ import annotations

import betterproto2
import pytest

from pymammotion.data.model.report_info import DeviceData
from pymammotion.proto import RptDevStatus
from tests.unit.data.model._helpers import make_wire_field


@pytest.mark.parametrize(("status", "installed"), [(0, False), (1, True), (2, False)])
def test_the_edge_cutter_is_installed_only_when_field_16_reports_exactly_1(status: int, installed: bool) -> None:
    """``rpt_dev_status`` field 16 is ``edge_cutter_status_t``; the app tests its field 1 with ``== 1``.

    The frame is encoded by hand so the field numbers are pinned to the app's, not to our proto.
    """
    frame = make_wire_field(16, 2, bytes([2]) + make_wire_field(1, 0, bytes([status])))

    dev = DeviceData.from_dict(RptDevStatus().parse(frame).to_dict(casing=betterproto2.Casing.SNAKE))

    assert dev.edge_cutter_installed is installed


def test_a_report_without_field_16_has_no_edge_cutter() -> None:
    """Older firmware never sends the field, which reads as no edge cutter, as in the app."""
    assert DeviceData().edge_cutter_installed is False
