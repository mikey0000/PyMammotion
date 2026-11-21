"""``MammotionClient`` stream subscription — the request reaches the HTTP layer of the device's own account."""

from __future__ import annotations

from unittest.mock import MagicMock, create_autospec

import pytest

from pymammotion.client import MammotionClient
from pymammotion.http.http import MammotionHTTP
from tests._helpers import make_account_session, make_bare_client, make_mock_handle


async def test_fetch_stream_subscription_passes_all_cameras_through() -> None:
    """Only the HTTP layer knows which slots that means."""
    client = make_bare_client()
    http = create_autospec(MammotionHTTP, instance=True)
    http.get_stream_subscription.return_value = MagicMock(data=MagicMock())

    await client._fetch_stream_subscription(http, "iot-1", True, all_cameras=True)

    http.get_stream_subscription.assert_awaited_once_with("iot-1", True, all_cameras=True)


def _stub_the_io(client: MammotionClient) -> None:
    """Replace the token fetch and the device command, the client's two I/O seams here, with specced stubs."""
    client._fetch_stream_subscription = create_autospec(
        client._fetch_stream_subscription, return_value=MagicMock(data=MagicMock())
    )
    client.send_command_with_args = create_autospec(client.send_command_with_args)


async def _client_with_device(device_name: str) -> MammotionClient:
    session = make_account_session("owner@example.com")
    client = make_bare_client(session)
    await client._device_registry.register(make_mock_handle(device_name=device_name), session.account_id)
    _stub_the_io(client)
    return client


@pytest.mark.parametrize(
    ("device_name", "has_rear"),
    [("Yuka-ABC123", True), ("Yuka-MNTXVHBE", False), ("Yuka-YM1234", False), ("Luba-VS563L6H", False)],
)
async def test_only_the_full_size_yuka_asks_for_the_rear_camera(device_name: str, has_rear: bool) -> None:
    """The Yuka Minis have no rear camera; the app requests it for LUBA_YUKA alone."""
    client = await _client_with_device(device_name)

    await client.get_stream_subscription(device_name, "iot-1", all_cameras=True)

    assert client._fetch_stream_subscription.await_args.args[2] is has_rear


@pytest.mark.regression
async def test_the_token_is_fetched_with_the_devices_own_account() -> None:
    """The token was fetched with the first account's session whatever account owned the device.

    On a host with two accounts, the second account's mowers got a request signed with the
    wrong bearer token, which the cloud rejects.
    """
    first, owner = make_account_session("first@example.com"), make_account_session("owner@example.com")
    client = make_bare_client(first, owner)
    await client._device_registry.register(make_mock_handle(device_name="Luba-VS563L6H"), owner.account_id)
    _stub_the_io(client)

    await client.get_stream_subscription("Luba-VS563L6H", "iot-1")

    assert client._fetch_stream_subscription.await_args.args[0] is owner.mammotion_http


async def test_an_unregistered_device_gets_no_token() -> None:
    client = await _client_with_device("Luba-VS563L6H")

    assert await client.get_stream_subscription("Luba-Other", "iot-1") is None
    client._fetch_stream_subscription.assert_not_awaited()
