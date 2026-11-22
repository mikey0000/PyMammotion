"""Credential-cache restore against the live fake cloud: it restores from the cache or refuses, never logs in."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import CachedLoginUnusableError, ReLoginRequiredError
from tests._helpers import wait_until
from tests.fakeserver.cloud import FakeMammotionCloud

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_restore_with_healthy_cache_skips_login(fake_cloud: FakeMammotionCloud) -> None:
    scenario = fake_cloud.scenario
    first = MammotionClient()
    await first.login_and_initiate_cloud(scenario.account, scenario.password)
    cached = first.to_cache()
    await first.stop()
    assert cached
    await fake_cloud.baseline_counters()

    second = MammotionClient()
    try:
        await second.restore_credentials(scenario.account, scenario.password, cached)
        assert scenario.counters.get("password_grants", 0) == 0
        assert scenario.counters.get("refresh_grants", 0) == 0  # token is nowhere near expiry
        assert second.mower(scenario.device.device_name) is not None
    finally:
        await second.stop()


@pytest.mark.regression
async def test_restore_with_revoked_bearers_marks_the_account_for_reauth_without_a_password_login(
    fake_cloud: FakeMammotionCloud,
) -> None:
    """A cached login the server refused fell back to a silent password grant on every restart.

    The host never learned the session was gone, and a password the server might
    already reject was spent once per restart and once per retry.
    """
    scenario = fake_cloud.scenario
    first = MammotionClient()
    await first.login_and_initiate_cloud(scenario.account, scenario.password)
    cached = first.to_cache()
    await first.stop()

    await fake_cloud.baseline_counters()
    scenario.expire_session()

    second = MammotionClient()
    told = AsyncMock()
    second.on_unrecoverable_auth_error = told
    try:
        with pytest.raises(ReLoginRequiredError):
            await second.restore_credentials(scenario.account, scenario.password, cached)
        assert second.reauth_required is not None
        await wait_until(lambda: told.await_count == 1, message="the host was never told to re-authenticate")
        assert scenario.counters.get("password_grants", 0) == 0
        assert scenario.counters.get("refresh_grants", 0) == 0
    finally:
        await second.stop()


async def test_deactivated_account_restore_costs_one_refresh_and_no_login(
    fake_cloud: FakeMammotionCloud,
) -> None:
    """The loop from the field log is cut at the refresh: no password grant follows a rejected refresh token.

    The cached access token is aged to just inside the refresh lead so
    validate_login's ensure_token_valid must attempt the refresh.
    """
    scenario = fake_cloud.scenario
    first = MammotionClient()
    await first.login_and_initiate_cloud(scenario.account, scenario.password)
    cached = first.to_cache()
    await first.stop()

    # Age the *cached* token rather than minting it near-expiry: a short
    # access_token_ttl at login leaves the first client's refresh scheduler inside its
    # 300 s lead window, spinning refreshes through the whole of setup and racing the
    # counter assertions below.
    await fake_cloud.baseline_counters()
    scenario.age_cached_access_token(cached, remaining=60.0)
    scenario.deactivate_account()

    second = MammotionClient()
    try:
        with pytest.raises(ReLoginRequiredError):
            await second.restore_credentials(scenario.account, scenario.password, cached)
        assert scenario.counters.get("refresh_grants") == 1
        assert scenario.counters.get("password_grants", 0) == 0
        assert scenario.counters.get("mammotion_mqtt_connects", 0) == 0
    finally:
        await second.stop()


@pytest.mark.regression
@pytest.mark.parametrize(
    "cached", [{}, {"mammotion_data": {"code": 0, "msg": "ok", "data": "garbage"}}], ids=["empty", "corrupt"]
)
async def test_restore_without_a_usable_cached_login_raises_and_never_logs_in(
    fake_cloud: FakeMammotionCloud, client: MammotionClient, cached: dict
) -> None:
    """A cache with no usable login fell back to a password grant, once per restart."""
    with pytest.raises(CachedLoginUnusableError):
        await client.restore_credentials(fake_cloud.scenario.account, fake_cloud.scenario.password, cached)

    assert fake_cloud.scenario.counters.get("password_grants", 0) == 0
