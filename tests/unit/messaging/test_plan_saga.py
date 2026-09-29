"""PlanFetchSaga: decoding the stored plans the device returns, driven through a real broker and command builder."""

from __future__ import annotations

import asyncio

import pytest

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.plan_saga import PlanFetchSaga
from pymammotion.proto import LubaMsg, MctlNav
from tests._helpers import (
    LUBA1_NAME,
    LUBA1_PRODUCT_KEY,
    NEWER_MODEL_NAME,
    UNRECOGNISED_NAME,
    make_stored_plan_frame,
)

_TIMEOUT = 1.0


def _stored_plan(reserved_byte_4: int, field_37: int) -> LubaMsg:
    return LubaMsg(nav=MctlNav(todev_planjob_set=make_stored_plan_frame(reserved_byte_4, field_37)))


async def _fetch(device_name: str, reply: LubaMsg, product_key: str = "") -> PlanFetchSaga:
    broker = DeviceMessageBroker()

    async def send_command(_payload: bytes) -> None:
        await broker.on_message(reply)

    command_builder = MammotionCommand(device_name, 1)
    command_builder.set_device_product_key(product_key)
    saga = PlanFetchSaga(command_builder=command_builder, send_command=send_command)
    await asyncio.wait_for(saga.execute(broker), _TIMEOUT)
    return saga


@pytest.mark.regression
async def test_a_luba1_plan_is_fetched_with_its_toward_mode_from_reserved() -> None:
    """The saga took field 37 for every model; a Luba 1 keeps the mode in ``reserved[4]`` (echoed +10)."""
    saga = await _fetch(LUBA1_NAME, _stored_plan(reserved_byte_4=11, field_37=0))

    assert saga.result["p1"].toward_mode == 1


async def test_a_newer_models_plan_is_fetched_with_its_toward_mode_from_field_37() -> None:
    saga = await _fetch(NEWER_MODEL_NAME, _stored_plan(reserved_byte_4=11, field_37=2))

    assert saga.result["p1"].toward_mode == 2


async def test_a_luba1_known_only_by_product_key_is_fetched_with_its_toward_mode_from_reserved() -> None:
    """The name matches no rule, so the saga must pass the builder's product key through to the decode."""
    saga = await _fetch(UNRECOGNISED_NAME, _stored_plan(reserved_byte_4=12, field_37=0), product_key=LUBA1_PRODUCT_KEY)

    assert saga.result["p1"].toward_mode == 2


async def test_a_plan_is_fetched_with_its_auto_change_direction_from_field_41() -> None:
    reply = LubaMsg(nav=MctlNav(todev_planjob_set=make_stored_plan_frame(reserved2=[11] + [10] * 31)))

    saga = await _fetch(NEWER_MODEL_NAME, reply)

    assert saga.result["p1"].auto_change_direction is True
