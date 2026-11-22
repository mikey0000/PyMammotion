"""Commands over the Aliyun cloud API (thing/service/invoke), as the transport sends them."""

from __future__ import annotations

import time

import pytest
import time_machine

from pymammotion.aliyun.exceptions import AuthRefreshException, DeviceOfflineException, DeviceUnboundException
from pymammotion.client import MammotionClient
from tests.fakeserver.cloud import FakeMammotionCloud

from ._helpers import aliyun_transport, counts, log_in_aliyun_account

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_command_reaches_the_mower_through_the_invoke_api(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    await log_in_aliyun_account(fake_cloud, client)
    iot_id = fake_cloud.scenario.aliyun_device.iot_id

    await aliyun_transport(client, fake_cloud.scenario).send(b"\x08\x01", iot_id=iot_id)

    assert (iot_id, b"\x08\x01") in fake_cloud.aliyun_invocations


@pytest.mark.parametrize(
    ("code", "expected"),
    [(50104, DeviceOfflineException), (29004, DeviceUnboundException)],
    ids=["offline", "unbound"],
)
async def test_command_refusal_is_classified_by_the_cloud_code_table(
    fake_cloud: FakeMammotionCloud, client: MammotionClient, code: int, expected: type[Exception]
) -> None:
    await log_in_aliyun_account(fake_cloud, client)
    fake_cloud.scenario.faults["aliyun_invokes"] = code

    with pytest.raises(expected):
        await aliyun_transport(client, fake_cloud.scenario).send(
            b"\x08\x01", iot_id=fake_cloud.scenario.aliyun_device.iot_id
        )


async def test_command_with_a_locally_expired_refresh_token_is_refused_without_traffic(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """Past the Aliyun refresh token's lifetime nothing can renew the iotToken, so nothing is sent."""
    scenario = fake_cloud.scenario
    scenario.aliyun_refresh_token_ttl = scenario.iot_token_ttl + 3600
    scenario.access_token_ttl = 4 * 86400
    await log_in_aliyun_account(fake_cloud, client)
    transport = aliyun_transport(client, scenario)

    with time_machine.travel(time.time() + scenario.aliyun_refresh_token_ttl + 60, tick=False):
        with pytest.raises(AuthRefreshException):
            await transport.send(b"\x08\x01", iot_id=scenario.aliyun_device.iot_id)

    assert counts(scenario, "aliyun_invokes", "aliyun_check_session") == {
        "aliyun_invokes": 0,
        "aliyun_check_session": 0,
    }
