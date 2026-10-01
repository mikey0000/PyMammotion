"""How ``MammotionClient`` surfaces the Aliyun account lock (bind_reply 2152) to the host.

Another session holding the lock is transport-scoped and not an auth failure: the
host hears it through ``on_account_in_use_changed`` and nothing else — no reauth
prompt (``on_unrecoverable_auth_error``) and no per-mower critical error, because
the login is healthy and the transport retries on its own.  That the transport
never takes the fatal-auth path for a 2152 is pinned in
``tests/unit/transport/test_aliyun_mqtt_account_lock.py``; these tests cover the
client's wiring, so they build the transport through the private
``_setup_aliyun_transport`` seam that is the subject under test, and register the
mower straight into the device registry as the other client tests do.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiomqtt
import pytest

from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.aliyun_mqtt import AliyunMQTTTransport
from tests._helpers import make_mock_handle, wait_until
from tests.unit._helpers import make_aliyun_session
from tests.unit.transport._fakes import FakeMQTTClient
from tests.unit.transport._helpers import make_bind_reply

_ACCOUNT = "a@example.com"


async def _wired() -> tuple[MammotionClient, AliyunMQTTTransport, DeviceHandle]:
    """A client with one registered mower whose cloud transport is the wired Aliyun one.

    The handle holds the real transport so ``_signal_transport_unrecoverable`` would
    select it — a critical-error assertion against it can fail.
    """
    client, _session, transport = make_aliyun_session(account_id=_ACCOUNT)
    client.on_account_in_use_changed = None
    client.on_unrecoverable_auth_error = AsyncMock()
    handle = make_mock_handle("dev1", "Luba-Test", mqtt_transport=transport)
    await client._device_registry.register(handle, _ACCOUNT)  # noqa: SLF001
    return client, transport, handle


async def test_account_lock_transitions_reach_the_host_with_the_account_id() -> None:
    client, transport, _handle = await _wired()
    changes: list[tuple[str, bool]] = []

    async def _on_change(account_id: str, held: bool) -> None:
        changes.append((account_id, held))

    client.on_account_in_use_changed = _on_change
    assert transport.on_account_in_use_changed is not None

    await transport.on_account_in_use_changed(True)
    await transport.on_account_in_use_changed(False)

    assert changes == [(_ACCOUNT, True), (_ACCOUNT, False)]


async def test_account_lock_callback_only_notifies_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    client, transport, handle = await _wired()
    critical = AsyncMock()
    monkeypatch.setattr(handle, "notify_critical_error", critical)
    client.on_account_in_use_changed = AsyncMock()
    assert transport.on_account_in_use_changed is not None

    await transport.on_account_in_use_changed(True)

    client.on_account_in_use_changed.assert_awaited_once_with(_ACCOUNT, True)
    client.on_unrecoverable_auth_error.assert_not_awaited()
    critical.assert_not_awaited()


async def test_account_lock_without_a_host_callback_is_a_no_op() -> None:
    client, transport, _handle = await _wired()
    assert client.on_account_in_use_changed is None
    assert transport.on_account_in_use_changed is not None

    await transport.on_account_in_use_changed(True)

    client.on_unrecoverable_auth_error.assert_not_awaited()


@pytest.mark.regression
async def test_signing_out_a_session_whose_account_lock_is_held_tells_the_host_it_ended() -> None:
    """A re-login replaces the session without revoking it; the old transport's held lock must not outlive it.

    The held state lived only on the transport, and nothing sent the ``held=False``
    transition when it was torn down, so the host's account-in-use repair stayed up
    for a session that no longer existed.
    """
    client, session, transport = make_aliyun_session(account_id=_ACCOUNT)
    changes: list[tuple[str, bool]] = []

    async def _on_change(account_id: str, held: bool) -> None:
        changes.append((account_id, held))

    client.on_account_in_use_changed = _on_change
    locked = FakeMQTTClient(messages=[make_bind_reply(2152)])

    with patch.object(aiomqtt, "Client", return_value=locked):
        await transport.connect()
        await wait_until(lambda: transport.account_in_use, message="the bind was never refused")
        await client._sign_out_session(session, revoke=False)  # noqa: SLF001

    assert changes == [(_ACCOUNT, True), (_ACCOUNT, False)]
