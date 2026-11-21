"""``MammotionClient.queue_command_and_wait``: a background read that waits its turn in the device's queue.

``_FakeMower`` stands in for the device behind the cloud transport's ``send`` and counts
the version requests it answers, so one read is exactly one request.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowingDevice
from pymammotion.device.handle import DeviceHandle, DeviceNotRegisteredError
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_queue import Priority
from pymammotion.messaging.saga import Saga
from pymammotion.proto import DevNet, DrvDevInfoResp, LubaMsg
from pymammotion.transport.base import TransportAvailability, TransportType
from tests._helpers import make_bare_client, make_mock_handle, make_mock_transport, wait_until

_TIMEOUT = 2.0
_NAME = "Luba-Q1"
_DEVINFO_REPLY = bytes(LubaMsg(net=DevNet(toapp_devinfo_resp=DrvDevInfoResp())))


class _FakeMower:
    """The device side: answers each version request with ``toapp_devinfo_resp``, a loop turn later."""

    def __init__(self, handle: DeviceHandle) -> None:
        self.handle = handle
        self.requests = 0
        self._replies: set[asyncio.Task[None]] = set()

    async def send(self, payload: bytes, **_: object) -> None:
        net = LubaMsg().parse(payload).net
        if net is None or net.todev_devinfo_req is None:
            return
        self.requests += 1
        task = asyncio.create_task(self.handle.on_raw_message(_DEVINFO_REPLY))
        self._replies.add(task)
        task.add_done_callback(self._replies.discard)


@pytest.fixture
async def handle() -> AsyncIterator[DeviceHandle]:
    handle = make_mock_handle(device_name=_NAME, device=MowingDevice())
    # UNKNOWN availability: replaying CONNECTED would queue a report request ahead of every read.
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN, availability=TransportAvailability.UNKNOWN)
    await handle.add_transport(mqtt)
    yield handle
    await handle.stop()


@pytest.fixture
def mower(handle: DeviceHandle) -> _FakeMower:
    mower = _FakeMower(handle)
    handle.get_transport(TransportType.CLOUD_ALIYUN).send = AsyncMock(side_effect=mower.send)  # type: ignore[union-attr]
    return mower


@pytest.fixture
async def client(handle: DeviceHandle) -> MammotionClient:
    client = make_bare_client()
    await client._device_registry.register(handle)  # noqa: SLF001
    return client


async def test_queue_command_and_wait_returns_the_reply(
    client: MammotionClient, handle: DeviceHandle, mower: _FakeMower
) -> None:
    # Started here, not in the fixture: async fixtures run on the session loop.
    handle.queue.start()
    reply = await asyncio.wait_for(
        client.queue_command_and_wait(_NAME, "get_device_version_main", "toapp_devinfo_resp"), _TIMEOUT
    )

    assert reply.net.toapp_devinfo_resp is not None
    assert mower.requests == 1


async def test_queue_command_and_wait_sends_nothing_while_a_saga_runs(
    client: MammotionClient, handle: DeviceHandle, mower: _FakeMower
) -> None:
    """The read is held until the saga ends, so it can never share the channel with the saga's traffic."""
    started, release = asyncio.Event(), asyncio.Event()

    class _BlockingSaga(Saga):
        name = "blocking"

        async def _run(self, b: DeviceMessageBroker) -> None:
            started.set()
            await release.wait()

    handle.queue.start()
    await handle.enqueue_saga(_BlockingSaga())
    await asyncio.wait_for(started.wait(), _TIMEOUT)
    read = asyncio.create_task(client.queue_command_and_wait(_NAME, "get_device_version_main", "toapp_devinfo_resp"))
    await wait_until(lambda: handle.queue.pending_count == 1, message="the read was never queued")

    assert mower.requests == 0, "the read was sent while the saga held the queue"
    release.set()
    await asyncio.wait_for(read, _TIMEOUT)
    assert mower.requests == 1


async def test_queue_command_and_wait_refuses_a_direct_priority(client: MammotionClient, mower: _FakeMower) -> None:
    with pytest.raises(ValueError, match="direct-send priority"):
        await client.queue_command_and_wait(
            _NAME, "get_device_version_main", "toapp_devinfo_resp", priority=Priority.USER
        )

    assert mower.requests == 0


async def test_an_unknown_device_raises_a_key_error_subclass(client: MammotionClient) -> None:
    """Typed for the host to map, and still a ``KeyError`` for callers of the earlier contract."""
    with pytest.raises(DeviceNotRegisteredError) as raised:
        await client.queue_command_and_wait("Luba-Missing", "get_device_version_main", "toapp_devinfo_resp")

    assert isinstance(raised.value, KeyError)
