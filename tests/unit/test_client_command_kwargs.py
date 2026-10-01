"""``MammotionClient``'s command verbs pass every keyword through to the command builder.

The device name, builder key and expected reply field are positional-only, so a builder
argument that shares a name with them (``set_area_name``'s ``name``, ``set_debug_config``'s
``key``) reaches the builder instead of colliding with the verb's own parameter.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from pymammotion.messaging.command_queue import Priority
from pymammotion.proto import LubaMsg
from pymammotion.transport.base import TransportType
from tests._helpers import make_bare_client, make_mock_handle, make_mock_transport

_TIMEOUT = 2.0


async def _client_echoing_commands(name: str) -> tuple[MammotionClient, list[LubaMsg]]:
    """A registered handle whose transport records each command and replays it as the device's reply."""
    sent: list[LubaMsg] = []
    handle: DeviceHandle = make_mock_handle(device_name=name)
    transport = make_mock_transport(TransportType.CLOUD_ALIYUN)

    async def _echo(payload: bytes, *_args: object, **_kwargs: object) -> None:
        sent.append(LubaMsg().parse(payload))
        await handle.on_raw_message(payload)

    transport.send = AsyncMock(side_effect=_echo)
    transport.send_user = AsyncMock(side_effect=_echo)
    await handle.add_transport(transport)
    client = make_bare_client()
    await client._device_registry.register(handle)  # noqa: SLF001
    return client, sent


@pytest.mark.regression
async def test_send_command_and_wait_passes_a_name_keyword_to_the_builder() -> None:
    """Renaming an area raised ``TypeError: got multiple values for argument 'name'``.

    ``send_command_and_wait`` named its device parameter ``name``, so ``set_area_name``'s
    own ``name=`` collided with it and every area rename from HA failed.
    """
    client, sent = await _client_echoing_commands("Luba-T1")

    await asyncio.wait_for(
        client.send_command_and_wait(
            "Luba-T1",
            "set_area_name",
            "toapp_map_name_msg",
            priority=Priority.USER,
            device_id="iot-1",
            hash_id=42,
            name="Front",
        ),
        _TIMEOUT,
    )

    assert [(m.nav.toapp_map_name_msg.hash, m.nav.toapp_map_name_msg.name) for m in sent] == [(42, "Front")]


@pytest.mark.regression
async def test_send_command_with_args_passes_name_and_key_keywords_to_the_builder() -> None:
    """The same collision on the fire-and-forget verb, for both ``name`` and ``key``."""
    client, sent = await _client_echoing_commands("Luba-T2")

    await client.send_command_with_args(
        "Luba-T2", "set_area_name", priority=Priority.USER, device_id="iot-2", hash_id=7, name="Back"
    )
    await client.send_command_with_args(
        "Luba-T2", "set_debug_config", priority=Priority.USER, key="log_level", value="debug"
    )

    assert sent[0].nav.toapp_map_name_msg.name == "Back"
    debug_cfg = sent[1].sys.debug_cfg_write
    assert (debug_cfg.key, debug_cfg.value) == ("log_level", "debug")
