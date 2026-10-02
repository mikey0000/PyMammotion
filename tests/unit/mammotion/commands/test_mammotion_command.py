"""``MammotionCommand.read_write_device`` routing between ``nav_sys_param_cmd`` and ``bidire_comm_cmd``."""

from __future__ import annotations

import pytest

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg

LUBA_1 = "Luba-ABCDEF"
LUBA_2 = "Luba-VS6ABCDE"
YUKA_MINI = "Yuka-MN12345"


@pytest.mark.regression
@pytest.mark.parametrize("device_name", [LUBA_1, LUBA_2, YUKA_MINI])
@pytest.mark.parametrize(("rw_id", "context", "rw"), [(12, 2, 1), (12, 0, 0), (13, 0, 0)])
def test_animal_protection_ids_never_go_out_on_bidire_comm_cmd(
    device_name: str, rw_id: int, context: int, rw: int
) -> None:
    """Ids 12/13 are WildGuard, which the app sends on ``nav_sys_param_cmd`` on every device type.

    ``read_write_device`` sent them as ``bidire_comm_cmd`` everywhere; the mower never answers that, so the
    caller timed out waiting (Mammotion-HA#922).
    """
    msg = LubaMsg().parse(MammotionCommand(device_name, 1).read_write_device(rw_id, context, rw))
    assert msg.sys is None or msg.sys.bidire_comm_cmd is None
    param = msg.nav.nav_sys_param_cmd
    assert (param.id, param.context, param.rw) == (rw_id, context, rw)


@pytest.mark.parametrize("rw_id", [3, 6, 7, 8, 10, 11])
@pytest.mark.parametrize(("device_name", "on_nav"), [(LUBA_1, False), (LUBA_2, True), (YUKA_MINI, True)])
def test_generic_ids_route_to_nav_only_on_luba_pro(rw_id: int, device_name: str, on_nav: bool) -> None:
    msg = LubaMsg().parse(MammotionCommand(device_name, 1).read_write_device(rw_id, 1, 1))
    assert (msg.nav is not None and msg.nav.nav_sys_param_cmd is not None) is on_nav
