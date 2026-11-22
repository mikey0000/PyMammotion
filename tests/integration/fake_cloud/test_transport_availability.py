"""What a host hears when one cloud transport is given up, and how it brings it back.

``on_transport_availability_changed`` fires on each edge only: given up (``available``
False, with the reason) and recovered (True, ``None``).  ``unavailable_transports`` is
the matching query, and ``retry_transport`` is the host's one password-free attempt.
"""

from __future__ import annotations

import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import ReLoginRequiredError, TransportType
from tests._helpers import wait_until
from tests.fakeserver.cloud import FakeMammotionCloud

from ._helpers import aliyun_transport, log_in_aliyun_account, make_aliyun_account, make_cached_login

pytestmark = pytest.mark.asyncio(loop_scope="session")

_ALIYUN = TransportType.CLOUD_ALIYUN
_MAMMOTION = TransportType.CLOUD_MAMMOTION


def _record_availability(client: MammotionClient) -> list[tuple[str, TransportType, bool, bool]]:
    """Each callback as (account, transport, available, has_reason)."""
    events: list[tuple[str, TransportType, bool, bool]] = []

    async def _changed(account_id: str, transport_type: TransportType, available: bool, reason: str | None) -> None:
        events.append((account_id, transport_type, available, reason is not None))

    client.on_transport_availability_changed = _changed
    return events


async def _give_up_aliyun_at_runtime(cloud: FakeMammotionCloud, client: MammotionClient) -> None:
    """Aliyun forgets the session and refuses the rebuild; wait until the transport is given up."""
    transport = aliyun_transport(client, cloud.scenario)
    cloud.scenario.faults["aliyun_session"] = 2064
    cloud.scenario.revoke_aliyun_session()
    cloud.aliyun_broker.drop_all_clients()
    await wait_until(lambda: not transport.is_usable)


@pytest.mark.regression
async def test_giving_up_aliyun_at_runtime_tells_the_host_once(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """The give-up reached only the per-device error bus, which no host listens to: mowers went dark in silence."""
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client, hybrid=True)
    events = _record_availability(client)

    await _give_up_aliyun_at_runtime(fake_cloud, client)

    await wait_until(lambda: events, message="the host was never told")
    assert events == [(scenario.account, _ALIYUN, False, True)]
    assert set(client.unavailable_transports(scenario.account)) == {_ALIYUN}


@pytest.mark.regression
async def test_a_refused_rebuild_at_restore_tells_the_host(fake_cloud: FakeMammotionCloud) -> None:
    """A restore whose Aliyun rebuild was refused reported success and said nothing."""
    scenario = fake_cloud.scenario
    make_aliyun_account(scenario, hybrid=True)
    cached = await make_cached_login(fake_cloud)
    scenario.age_cached_aliyun_session(cached)
    scenario.revoke_aliyun_session()
    scenario.faults["aliyun_session"] = 2064
    client = MammotionClient()
    events = _record_availability(client)
    try:
        await client.restore_credentials(scenario.account, scenario.password, cached)

        await wait_until(lambda: events, message="the host was never told")
        assert events == [(scenario.account, _ALIYUN, False, True)]
        assert set(client.unavailable_transports(scenario.account)) == {_ALIYUN}
    finally:
        await client.stop()


async def test_retry_transport_brings_aliyun_back_without_a_password(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client, hybrid=True)
    events = _record_availability(client)
    await _give_up_aliyun_at_runtime(fake_cloud, client)
    await wait_until(lambda: events)
    del scenario.faults["aliyun_session"]

    await client.retry_transport(scenario.account, _ALIYUN)

    await wait_until(lambda: aliyun_transport(client, scenario).is_connected)
    await wait_until(lambda: len(events) == 2, message="the recovery was never reported")
    assert events[-1] == (scenario.account, _ALIYUN, True, False)
    assert client.unavailable_transports(scenario.account) == {}
    assert scenario.counters.get("password_grants", 0) == 0


async def test_a_refused_retry_raises_and_leaves_the_transport_given_up(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client, hybrid=True)
    events = _record_availability(client)
    await _give_up_aliyun_at_runtime(fake_cloud, client)
    await wait_until(lambda: events)

    with pytest.raises(Exception):  # noqa: PT011 — any refusal; the state below is the assertion
        await client.retry_transport(scenario.account, _ALIYUN)

    assert set(client.unavailable_transports(scenario.account)) == {_ALIYUN}
    assert events == [(scenario.account, _ALIYUN, False, True)], "a failed retry must not report a recovery"
    assert scenario.counters.get("password_grants", 0) == 0


async def test_an_unrenewable_jwt_is_reported_and_retry_transport_restores_it(
    fake_cloud: FakeMammotionCloud,
) -> None:
    scenario = fake_cloud.scenario
    scenario.mqtt_jwt_returns_no_data = True
    client = MammotionClient()
    events = _record_availability(client)
    try:
        await client.login_and_initiate_cloud(scenario.account, scenario.password)
        await wait_until(lambda: events, message="the host was never told")
        assert events == [(scenario.account, _MAMMOTION, False, True)]
        mower = client.mower(scenario.device.device_name)
        assert mower is not None, "the account's mower vanished instead of showing as unavailable"
        assert not mower.has_usable_transport
        scenario.mqtt_jwt_returns_no_data = False

        await client.retry_transport(scenario.account, _MAMMOTION)

        await wait_until(lambda: mower.has_usable_transport)
        await wait_until(lambda: len(events) == 2, message="the recovery was never reported")
        assert events[-1] == (scenario.account, _MAMMOTION, True, False)
        assert client.unavailable_transports(scenario.account) == {}
    finally:
        await client.stop()


async def test_retry_transport_refuses_an_account_that_needs_reauth(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client, hybrid=True)
    await _give_up_aliyun_at_runtime(fake_cloud, client)
    scenario.expire_session()
    del scenario.faults["aliyun_session"]

    with pytest.raises(ReLoginRequiredError):
        await client.retry_transport(scenario.account, _ALIYUN)

    assert scenario.counters.get("password_grants", 0) == 0


async def test_a_new_login_reports_the_given_up_transport_recovered(
    fake_cloud: FakeMammotionCloud, client: MammotionClient
) -> None:
    """Reconfiguring cures a given-up transport; the host must hear so, or its issue never clears."""
    scenario = fake_cloud.scenario
    await log_in_aliyun_account(fake_cloud, client, hybrid=True)
    events = _record_availability(client)
    await _give_up_aliyun_at_runtime(fake_cloud, client)
    await wait_until(lambda: events)
    del scenario.faults["aliyun_session"]

    await client.login_and_initiate_cloud(scenario.account, scenario.password)

    await wait_until(lambda: len(events) == 2, message="the recovery was never reported")
    assert events[-1] == (scenario.account, _ALIYUN, True, False)
    assert client.unavailable_transports(scenario.account) == {}
