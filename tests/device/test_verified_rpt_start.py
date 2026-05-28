"""Tests for ``DeviceHandle._send_rpt_start_verified``.

Verifies that every RPT_START goes through ``broker.send_and_wait`` expecting
``toapp_report_data`` as the implicit ack, and that on the broker's retry
attempt the ble_sync prefix lands *before* the re-issued RPT_START.

Covers four behaviours:
- success on first attempt
- retry-with-ble_sync-prefix on broker retry
- final CommandTimeoutError → returns False
- ConcurrentRequestError → graceful fallback send + returns False
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import CommandTimeoutError, ConcurrentRequestError


@pytest.fixture
def handle(monkeypatch: pytest.MonkeyPatch) -> DeviceHandle:
    """Bare DeviceHandle with broker + commands mocked.

    We bypass ``DeviceHandle.__init__`` entirely (it brings up a queue, reducer
    etc. that aren't relevant here) and set just the attributes the helper
    touches.  ``commands`` is a ``@property``, so we monkeypatch the descriptor
    at the class level to return our mock.
    """
    h = DeviceHandle.__new__(DeviceHandle)
    h.device_name = "Luba-TEST"
    h.broker = MagicMock()
    h.broker.send_and_wait = AsyncMock()
    mocked_commands = MagicMock()
    mocked_commands.send_todev_ble_sync = MagicMock(return_value=b"\xAAsync")
    monkeypatch.setattr(DeviceHandle, "commands", property(lambda self: mocked_commands))
    return h


async def test_success_returns_true_and_sends_once(handle: DeviceHandle) -> None:
    """First attempt succeeds: send_fn runs once with cmd_bytes only, no ble_sync."""
    cmd_bytes = b"\xBBcmd"
    transport_send = AsyncMock()

    # Drive send_and_wait to invoke our _send exactly once and "succeed"
    async def _drive(send_fn, expected_field, **kwargs) -> None:
        assert expected_field == "toapp_report_data"
        await send_fn()  # one attempt, no exception

    handle.broker.send_and_wait.side_effect = _drive

    result = await handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is True
    # send_fn ran once → transport_send called once with cmd_bytes (no ble_sync)
    transport_send.assert_awaited_once_with(cmd_bytes)


async def test_retry_prefixes_ble_sync_then_cmd(handle: DeviceHandle) -> None:
    """On the broker's 2nd attempt the send order is: ble_sync, then RPT_START.

    The broker's retry budget is 2 attempts by default; we simulate that by
    invoking _send twice from inside send_and_wait, then "succeeding".
    """
    cmd_bytes = b"\xBBcmd"
    sync_bytes = b"\xAAsync"
    handle.commands.send_todev_ble_sync.return_value = sync_bytes
    transport_send = AsyncMock()

    async def _drive(send_fn, expected_field, **kwargs) -> None:
        # Attempt 1
        await send_fn()
        # Attempt 2 (broker's retry)
        await send_fn()

    handle.broker.send_and_wait.side_effect = _drive

    result = await handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is True
    # Expect three sends total: attempt 1 (cmd), attempt 2 (sync + cmd)
    sends = [c.args[0] for c in transport_send.await_args_list]
    assert sends == [cmd_bytes, sync_bytes, cmd_bytes], (
        f"Send order wrong; got {sends!r}"
    )


async def test_command_timeout_returns_false(handle: DeviceHandle) -> None:
    """CommandTimeoutError from the broker → helper returns False (no raise)."""
    cmd_bytes = b"\xBBcmd"
    transport_send = AsyncMock()

    handle.broker.send_and_wait.side_effect = CommandTimeoutError("toapp_report_data", 2)

    result = await handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is False


async def test_concurrent_request_falls_back_to_plain_send(handle: DeviceHandle) -> None:
    """When another verified RPT_START is in flight, the helper:
    1. Catches ConcurrentRequestError silently
    2. Falls back to a fire-and-forget send of cmd_bytes
    3. Returns False (we can't claim verification)
    """
    cmd_bytes = b"\xBBcmd"
    transport_send = AsyncMock()

    handle.broker.send_and_wait.side_effect = ConcurrentRequestError("Already waiting")

    result = await handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is False
    # Fallback fire-and-forget send did happen
    transport_send.assert_awaited_once_with(cmd_bytes)


async def test_retry_prefix_send_failure_does_not_abort(handle: DeviceHandle) -> None:
    """If the ble_sync prefix send itself raises, the helper logs DEBUG and
    still re-issues the RPT_START on that attempt — a flaky sync write must
    not block the actual retry."""
    cmd_bytes = b"\xBBcmd"
    sync_bytes = b"\xAAsync"
    handle.commands.send_todev_ble_sync.return_value = sync_bytes

    # First send (attempt 1, cmd): ok.  Second send (attempt 2, ble_sync prefix): raises.
    # Third send (attempt 2, cmd after the failed prefix): ok.
    transport_send = AsyncMock(
        side_effect=[None, RuntimeError("flaky sync write"), None],
    )

    async def _drive(send_fn, expected_field, **kwargs) -> None:
        await send_fn()  # attempt 1
        await send_fn()  # attempt 2 (prefix raises, cmd should still go)

    handle.broker.send_and_wait.side_effect = _drive

    result = await handle._send_rpt_start_verified(cmd_bytes, transport_send)

    assert result is True
    sends = [c.args[0] for c in transport_send.await_args_list]
    assert sends == [cmd_bytes, sync_bytes, cmd_bytes]
