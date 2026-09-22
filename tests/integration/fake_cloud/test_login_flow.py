"""Login and connection flows against the live fake cloud."""

from __future__ import annotations

import pytest

from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import CloudSetupError
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


def _aliyun_gateway_rejects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make the first Aliyun step fail the way the API gateway refuses a session.

    The fake serves no Aliyun endpoints, so the gateway boundary is replaced here.
    Returns the list of country codes the chain was started with.
    """
    attempts: list[str] = []

    async def _reject(_self: CloudIOTGateway, country_code: str) -> None:
        attempts.append(country_code)
        raise CloudSetupError("Error in getting mqtt credentials: API gateway refused the session")

    monkeypatch.setattr(CloudIOTGateway, "get_region", _reject)
    return attempts


@pytest.mark.regression
async def test_shared_page_data_alone_does_not_start_aliyun(
    fake_cloud: FakeMammotionCloud, client: MammotionClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aliyun setup was gated on the shared-device page, which the real cloud always fills.

    The app starts the Aliyun login only from the login's authorization code.
    """
    scenario = fake_cloud.scenario
    scenario.share_page_returns_data = True
    attempts = _aliyun_gateway_rejects(monkeypatch)

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    assert attempts == []
    assert client.mower(scenario.device.device_name) is not None


@pytest.mark.regression
async def test_aliyun_failure_leaves_mammotion_devices_working(
    fake_cloud: FakeMammotionCloud, client: MammotionClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An Aliyun gateway refusal used to abort the whole login, bricking a Mammotion-only account.

    The app runs the two platforms independently: a failed Aliyun login costs only
    the Aliyun device list (``DeviceManager.getAliDeviceListCheckLogin``).
    """
    scenario = fake_cloud.scenario
    scenario.issue_authorization_code = True
    scenario.share_page_returns_data = True
    attempts = _aliyun_gateway_rejects(monkeypatch)

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    assert attempts == ["EU"]
    handle = client.mower(scenario.device.device_name)
    assert handle is not None
    await wait_for(lambda: len(fake_cloud.mammotion_broker.sessions) == 1)
    assert handle.has_usable_transport
    assert client.token_manager is not None
    assert client.token_manager.reauth_required is None


@pytest.mark.regression
async def test_aliyun_failure_is_raised_when_nothing_else_is_bound(
    fake_cloud: FakeMammotionCloud, client: MammotionClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old gate skipped Aliyun here, so the login succeeded with no devices and hid the fault."""
    scenario = fake_cloud.scenario
    scenario.issue_authorization_code = True
    scenario.mammotion_device_bound = False
    _aliyun_gateway_rejects(monkeypatch)

    with pytest.raises(CloudSetupError, match="API gateway refused"):
        await client.login_and_initiate_cloud(scenario.account, scenario.password)
