"""Map-free mowing ("DropMow") is the app's ``noAreaWork``, on the task-control message.

It starts the mower from where it stands, with no map and no boundary.  The app
keeps it behind its Beta Features screen, offers it only on the X5 models, and
takes it only while the mower is idle, so the interesting part of the wire
format is that it is *not* a route command — no areas, no plan, just an action
on ``todev_taskctrl``.
"""

from __future__ import annotations

import betterproto2
import pytest

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, MsgCmdType, NavTaskCtrl
from pymammotion.utility.device_type import DeviceType

_X5 = "Luba-VA123456"


def _task_ctrl(payload: bytes) -> tuple[LubaMsg, NavTaskCtrl]:
    msg = LubaMsg().parse(payload)
    name, value = betterproto2.which_one_of(msg.nav, "SubNavMsg")
    assert name == "todev_taskctrl"
    return msg, value


def test_it_sends_action_16_on_the_task_control_message() -> None:
    """The app's noAreaWork(): type 1, action 16, result 0."""
    msg, ctrl = _task_ctrl(MammotionCommand(_X5, 1).start_no_area_work())

    assert msg.msgtype == MsgCmdType.NAV
    assert (ctrl.type, ctrl.action, ctrl.result) == (1, 16, 0)


def test_it_does_not_collide_with_the_other_task_actions() -> None:
    """16 has to be its own action, not an overload of start/pause/cancel."""
    command = MammotionCommand(_X5, 1)
    actions = {
        "start": _task_ctrl(command.start_job())[1].action,
        "pause": _task_ctrl(command.pause_execute_task())[1].action,
        "cancel": _task_ctrl(command.cancel_job())[1].action,
        "dock": _task_ctrl(command.return_to_dock())[1].action,
        "no_area": _task_ctrl(command.start_no_area_work())[1].action,
    }

    assert actions["no_area"] == 16
    assert len(set(actions.values())) == len(actions), actions


def test_it_carries_no_route_or_area() -> None:
    """Map-free means map-free: nothing that would scope it to a mapped zone."""
    msg, _ = _task_ctrl(MammotionCommand(_X5, 1).start_no_area_work())

    assert betterproto2.which_one_of(msg.nav, "SubNavMsg")[0] == "todev_taskctrl"
    assert msg.nav.bidire_reqconver_path is None
    assert msg.nav.todev_planjob_set is None


@pytest.mark.parametrize(
    "device_name",
    ["Luba-VA123456", "Luba-HM123456", "Luba-ME123456", "Luba-MB123456", "Luba-LA123456", "Luba-MD123456"],
)
def test_the_x5_models_are_recognised(device_name: str) -> None:
    """Only these are offered the feature, mirroring the app's isX5DeviceTyp()."""
    assert DeviceType.is_x5_series(device_name)


@pytest.mark.parametrize("device_name", ["Luba-VS563L6H", "Yuka-MNTXVHBE", "Spino-E1C36JT4", "RTKBAU242721575"])
def test_everything_else_is_not_offered_it(device_name: str) -> None:
    """A mower on the older platform, a pool cleaner and a base station alike."""
    assert not DeviceType.is_x5_series(device_name)
