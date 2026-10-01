"""How ``MammotionClient``'s send entry points surface a ``TransportError`` that is not an auth failure.

One rule: a direct priority (``Priority.USER`` / ``EMERGENCY``) propagates it, because a
person is waiting on the command and the host has to learn it did not land; anything
else is logged and dropped, because nobody is waiting.  ``TransportRateLimitedError`` is
the case that matters — it never reaches the network, so it is the one a host only ever
sees if the client lets it through, and HA's ``api_limit_exceeded`` handler depends on it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from pymammotion.messaging.command_queue import Priority
from pymammotion.transport.base import TransportRateLimitedError, TransportType
from pymammotion.transport.cloud import CloudTransport
from tests._helpers import make_bare_client, make_mock_handle, make_mock_transport

_TIMEOUT = 1.0
_REPLY_TIMEOUT = 0.05


_NAME = "Luba-T1"


@pytest.fixture
async def banned_device() -> AsyncIterator[tuple[MammotionClient, DeviceHandle, MagicMock]]:
    """A device whose only transport is one the cloud has 429'd: every send is refused locally."""
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.is_cloud_banned = True
    mqtt.is_rate_limited = True
    mqtt.is_send_blocked = MagicMock(return_value=True)
    mqtt.send_user = AsyncMock(spec=CloudTransport.send_user)
    handle = make_mock_handle(device_name=_NAME)
    await handle.add_transport(mqtt)
    client = make_bare_client()
    await client._device_registry.register(handle)  # noqa: SLF001
    try:
        yield client, handle, mqtt
    finally:
        await handle.stop()


@pytest.mark.regression
@pytest.mark.parametrize("priority", [Priority.USER, Priority.EMERGENCY], ids=["user", "emergency"])
async def test_send_command_with_args_raises_a_rate_limit_refusal_on_a_direct_priority(
    banned_device: tuple[MammotionClient, DeviceHandle, MagicMock], priority: Priority
) -> None:
    """``_send_with_auth_retry`` logged and dropped every non-auth ``TransportError``.

    The direct path runs ``execute_command(reraise=True)`` so the host learns a command
    did not land, but the refusal never got that far: a button press on a rate-limited
    account reported success, and HA's ``api_limit_exceeded`` branch was unreachable.
    """
    client, handle, mqtt = banned_device

    with pytest.raises(TransportRateLimitedError):
        await asyncio.wait_for(client.send_command_with_args(_NAME, "start_job", priority=priority), _TIMEOUT)

    mqtt.send_user.assert_not_awaited()


async def test_send_command_with_args_drops_a_rate_limit_refusal_on_a_queued_priority(
    banned_device: tuple[MammotionClient, DeviceHandle, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The client, not the queue, drops it: the queue would absorb it too, so only the client's log tells them apart."""
    client, handle, mqtt = banned_device
    handle.queue.start()

    with caplog.at_level(logging.WARNING, logger="pymammotion.client"):
        await client.send_command_with_args(_NAME, "start_job", priority=Priority.NORMAL)
        # task_done() runs per item, so join() means the send was attempted and absorbed.
        await asyncio.wait_for(handle.queue._queue.join(), _TIMEOUT)  # noqa: SLF001

    assert mqtt.is_send_blocked.called, "the queued send never reached the rate-limit gate"
    assert [r.name for r in caplog.records if r.levelno == logging.WARNING] == ["pymammotion.client"], (
        "expected the client's auth retry to log and drop the refusal, not pass it on to the queue"
    )
    assert handle.queue._task is not None, "the queue processor was never started"  # noqa: SLF001
    assert not handle.queue._task.done(), "the refusal escaped and killed the queue processor"  # noqa: SLF001
    mqtt.send.assert_not_awaited()


@pytest.mark.regression
async def test_refresh_status_raises_a_rate_limit_refusal(
    banned_device: tuple[MammotionClient, DeviceHandle, MagicMock],
) -> None:
    """``refresh_status`` is always user-initiated, yet it took the swallowing default.

    The refusal was dropped inside the auth retry, so ``execute_command(reraise=True)``
    saw a clean return and the press looked like it had been sent.
    """
    client, handle, mqtt = banned_device

    with pytest.raises(TransportRateLimitedError):
        await asyncio.wait_for(client.refresh_status(_NAME), _TIMEOUT)

    mqtt.send_user.assert_not_awaited()


@pytest.mark.regression
async def test_send_command_and_wait_raises_a_rate_limit_refusal_on_a_direct_priority(
    banned_device: tuple[MammotionClient, DeviceHandle, MagicMock],
) -> None:
    """The refusal was dropped, so the broker waited out every reply window for a send that never left.

    A user command then failed as ``CommandTimeoutError`` — "the mower did not answer" —
    instead of the rate limit that actually stopped it.
    """
    client, handle, mqtt = banned_device

    with pytest.raises(TransportRateLimitedError):
        await asyncio.wait_for(
            client.send_command_and_wait(
                _NAME, "get_report_cfg", "toapp_report_data", send_timeout=_REPLY_TIMEOUT, priority=Priority.USER
            ),
            _TIMEOUT,
        )

    mqtt.send_user.assert_not_awaited()
