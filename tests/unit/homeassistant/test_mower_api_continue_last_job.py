"""``HomeAssistantMowerApi.async_continue_last_job``: the HA-facing "continue last job" action.

The action is a named command dispatched through ``MammotionClient.send_command_with_args``, which
resolves the name on ``MammotionCommand``.  The test resolves the captured call the same way, so it
fails if the name or its keyword arguments stop matching the builder.
"""

from __future__ import annotations

from unittest.mock import create_autospec

import betterproto2

from pymammotion.client import MammotionClient
from pymammotion.homeassistant.mower_api import HomeAssistantMowerApi
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg


def _make_api_with_client() -> tuple[HomeAssistantMowerApi, MammotionClient]:
    api = HomeAssistantMowerApi.__new__(HomeAssistantMowerApi)
    api.update_failures = 0
    client = create_autospec(MammotionClient, instance=True)
    api._mammotion = client
    return api, client


async def test_async_continue_last_job_sends_a_start_working_msg_for_the_work_id() -> None:
    api, client = _make_api_with_client()

    assert await api.async_continue_last_job("Luba-VS6ABCDE", work_id=7) is True

    name, command = client.send_command_with_args.await_args.args
    payload = getattr(MammotionCommand(name, user_account=42), command)(
        **client.send_command_with_args.await_args.kwargs
    )
    field, message = betterproto2.which_one_of(LubaMsg().parse(payload).nav, "SubNavMsg")
    assert (name, field, message.work_id) == ("Luba-VS6ABCDE", "todev_work_report_start_working_msg", 7)
