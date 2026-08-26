"""Credential-cache restore against the live fake cloud — the 40102 field scenario."""

from __future__ import annotations

import pytest

from pymammotion.client import MammotionClient
from pymammotion.transport.base import LoginFailedError
from tests.fakeserver.cloud import FakeMammotionCloud

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_restore_with_healthy_cache_skips_login(fake_cloud: FakeMammotionCloud) -> None:
    scenario = fake_cloud.scenario
    first = MammotionClient()
    await first.login_and_initiate_cloud(scenario.account, scenario.password)
    cached = first.to_cache()
    await first.stop()
    assert cached
    scenario.counters.clear()

    second = MammotionClient()
    try:
        await second.restore_credentials(scenario.account, scenario.password, cached)
        assert scenario.counters.get("password_grants", 0) == 0
        assert scenario.counters.get("refresh_grants", 0) == 0  # token is nowhere near expiry
        assert second.mower(scenario.device.device_name) is not None
    finally:
        await second.stop()


async def test_restore_with_revoked_bearers_falls_back_to_one_login(
    fake_cloud: FakeMammotionCloud,
) -> None:
    """Server-side revocation: validate fails → exactly one password grant, no refresh spam."""
    scenario = fake_cloud.scenario
    first = MammotionClient()
    await first.login_and_initiate_cloud(scenario.account, scenario.password)
    cached = first.to_cache()
    await first.stop()

    scenario.expire_session()
    scenario.counters.clear()

    second = MammotionClient()
    try:
        await second.restore_credentials(scenario.account, scenario.password, cached)
        # The cached token still looks locally valid, so validate_login goes
        # straight to the probe call, gets 401, and falls back to ONE login.
        assert scenario.counters.get("password_grants") == 1
        assert scenario.counters.get("refresh_grants", 0) == 0
        assert second.mower(scenario.device.device_name) is not None
    finally:
        await second.stop()


async def test_deactivated_account_restore_costs_one_refresh_and_one_login(
    fake_cloud: FakeMammotionCloud,
) -> None:
    """The exact loop from the field log, per attempt: one 40102 + one rejected login.

    The cached access token is minted near expiry so validate_login's
    ensure_token_valid must attempt the refresh — reproducing the log's
    "refresh rejected (40102) → fallback login → account deactivated" chain.
    The bound under test: ONE refresh grant and ONE password grant per restore,
    and the attempt ends in LoginFailedError (which the HA layer maps to
    ConfigEntryAuthFailed + cache clearing).
    """
    scenario = fake_cloud.scenario
    scenario.access_token_ttl = 60.0  # < the 300 s refresh lead → refresh on validate
    first = MammotionClient()
    await first.login_and_initiate_cloud(scenario.account, scenario.password)
    cached = first.to_cache()
    await first.stop()

    scenario.deactivate_account()
    scenario.counters.clear()

    second = MammotionClient()
    try:
        with pytest.raises(LoginFailedError, match="deactivated"):
            await second.restore_credentials(scenario.account, scenario.password, cached)
        assert scenario.counters.get("refresh_grants") == 1
        assert scenario.counters.get("password_grants") == 1
        assert scenario.counters.get("mammotion_mqtt_connects", 0) == 0
    finally:
        await second.stop()
