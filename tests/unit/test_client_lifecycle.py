"""MammotionClient.stop(): what a shut-down client leaves running.

The account session owns its cloud transports; a client with no device handles
must still take them down.
"""

from __future__ import annotations

from unittest.mock import patch

import aiomqtt
import pytest

from pymammotion.transport.base import TransportType

from tests._helpers import make_mock_transport, wait_until
from tests.unit._helpers import make_aliyun_session
from tests.unit.transport._fakes import FakeMQTTClient
from tests.unit.transport._helpers import make_bind_reply


@pytest.mark.regression
async def test_stop_disconnects_an_account_transport_no_device_handle_holds() -> None:
    """stop() left the Aliyun receive loop running for an account with no Aliyun devices.

    ``login_and_initiate_cloud`` connects the Aliyun transport even when no device is
    registered on it, and stop() only disconnected transports through device handles,
    so the task outlived the client.
    """
    client, _session, transport = make_aliyun_session()
    with patch.object(aiomqtt, "Client", return_value=FakeMQTTClient(messages=[make_bind_reply(200)])):
        await transport.connect()
        await wait_until(lambda: transport.is_connected, message="transport never connected")

        await client.stop()

    assert transport._task is not None
    assert transport._task.done(), "Aliyun receive loop still running after stop()"
    assert transport.is_connected is False


async def test_stop_disconnects_the_accounts_mammotion_transport() -> None:
    client, session, _aliyun = make_aliyun_session()
    session.mammotion_transport = make_mock_transport(TransportType.CLOUD_MAMMOTION)

    await client.stop()

    session.mammotion_transport.disconnect.assert_awaited_once()
