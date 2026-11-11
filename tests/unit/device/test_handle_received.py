"""``DeviceHandle.subscribe_received`` — every decoded inbound frame, solicited or not.

The broker hands a solicited reply only to its waiter, so ``subscribe_unsolicited``
never sees it; tracing needs a hook that does.
"""

from __future__ import annotations

import asyncio

from pymammotion.device.handle import DeviceHandle
from pymammotion.proto import AppGetAllAreaHashName, LubaMsg, MctlNav, MsgDevice
from pymammotion.transport.base import Subscription
from tests.unit.device._helpers import make_handle

_TIMEOUT = 2.0


def _area_names_reply() -> bytes:
    nav = MctlNav(toapp_all_hash_name=AppGetAllAreaHashName(device_id="iot-r"))
    return bytes(LubaMsg(sender=MsgDevice.DEV_MAINCTL, rcver=MsgDevice.DEV_MOBILEAPP, nav=nav))


def _subscribed(handle: DeviceHandle) -> tuple[list[LubaMsg], Subscription]:
    """Collect received frames; the caller must hold the Subscription or it unsubscribes."""
    received: list[LubaMsg] = []

    async def _on_received(msg: LubaMsg) -> None:
        received.append(msg)

    return received, handle.subscribe_received(_on_received)


async def test_a_solicited_reply_reaches_received_subscribers() -> None:
    handle = make_handle("Yuka-Recv")
    received, _sub_received = _subscribed(handle)
    unsolicited: list[LubaMsg] = []

    async def _on_unsolicited(msg: LubaMsg) -> None:
        unsolicited.append(msg)

    _sub = handle.broker.subscribe_unsolicited(_on_unsolicited)

    async def _reply() -> None:
        await handle.on_raw_message(_area_names_reply())

    response = await asyncio.wait_for(
        handle.broker.send_and_wait(send_fn=_reply, expected_field="toapp_all_hash_name"), _TIMEOUT
    )

    assert response.nav.toapp_all_hash_name is not None
    assert [m.nav.toapp_all_hash_name.device_id for m in received] == ["iot-r"]
    assert unsolicited == []


async def test_an_unsolicited_frame_reaches_received_subscribers() -> None:
    handle = make_handle("Yuka-Recv")
    received, _sub_received = _subscribed(handle)

    await handle.on_raw_message(_area_names_reply())

    assert [m.nav.toapp_all_hash_name.device_id for m in received] == ["iot-r"]


async def test_a_payload_rejected_as_not_a_luba_msg_is_not_emitted() -> None:
    handle = make_handle("Yuka-Recv")
    received, _sub_received = _subscribed(handle)

    # Parses, but packed bytes land in ``sender`` as a list — the handle's non-LubaMsg guard.
    await handle.on_raw_message(b"\x12\x05ab")

    assert received == []
