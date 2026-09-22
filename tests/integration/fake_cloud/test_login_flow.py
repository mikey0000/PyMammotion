"""Login and connection flows against the live fake cloud."""

from __future__ import annotations

import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import LoginFailedError
from tests.fakeserver.cloud import FakeMammotionCloud
from tests.fakeserver.scenario import DEACTIVATED_MSG

from .conftest import wait_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_login_connects_mqtt_and_registers_device(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """Full happy path: password grant → device discovery → live MQTT session."""
    scenario = fake_cloud.scenario
    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    assert scenario.counters.get("password_grants") == 1
    assert scenario.counters.get("refresh_grants", 0) == 0

    handle = client.mower(scenario.device.device_name)
    assert handle is not None
    assert handle.iot_id == scenario.device.iot_id

    # The transport should establish a real broker session.
    await wait_for(lambda: len(fake_cloud.mammotion_broker.sessions) == 1)
    assert handle.has_usable_transport


async def test_wrong_password_raises_login_failed(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    with pytest.raises(LoginFailedError):
        await client.login_and_initiate_cloud(scenario.account, "not-the-password")

    assert scenario.counters.get("password_grants") == 1
    # A rejected login must not produce any token refresh or MQTT traffic.
    assert scenario.counters.get("refresh_grants", 0) == 0
    assert scenario.counters.get("mammotion_mqtt_connects", 0) == 0


async def test_deactivated_account_raises_login_failed_with_reason(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """The state observed in the field: Mammotion deactivates the account."""
    scenario = fake_cloud.scenario
    scenario.deactivate_account()

    with pytest.raises(LoginFailedError, match="deactivated"):
        await client.login_and_initiate_cloud(scenario.account, scenario.password)

    assert DEACTIVATED_MSG in (scenario.login_reject or (0, ""))[1]
    assert scenario.counters.get("mammotion_mqtt_connects", 0) == 0
