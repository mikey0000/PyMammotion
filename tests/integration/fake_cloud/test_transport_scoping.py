"""A dead Mammotion MQTT JWT must not take the account down with it.

CLAUDE.md: a *transport-scoped* failure sets ``mqtt_unavailable`` and gives up only
that transport — "the login, the cached credentials, and the account's *other*
transport must survive".  ``TokenManager.get_mammotion_mqtt_credentials`` signals it
with ``ReLoginRequiredError``, which is in ``client._AUTH_REJECTED``, so letting it
escape ``_ensure_mammotion_transport`` aborted the whole login/restore.

These assert the survivors, so the regression is caught rather than reasoned about.
"""

from __future__ import annotations

import pytest

from pymammotion.client import MammotionClient
from tests.fakeserver.cloud import FakeMammotionCloud

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_login_survives_an_unrenewable_mqtt_jwt(fake_cloud: FakeMammotionCloud) -> None:
    """The session must end up registered and renewing, not half-built and orphaned.

    ``login_and_initiate_cloud`` bootstraps Mammotion MQTT *before* it registers the
    session and starts the refresh scheduler, so a raise there left a live Aliyun
    transport and started handles on a session nothing could reach or sign out.
    """
    scenario = fake_cloud.scenario
    scenario.mqtt_jwt_returns_no_data = True
    client = MammotionClient()
    try:
        await client.login_and_initiate_cloud(scenario.account, scenario.password)

        session = client._get_default_session()
        assert session is not None, "session was never registered"
        assert client.token_manager is not None
        # The transport is given up, and says so.
        assert client.token_manager.mqtt_unavailable is not None
        # ...but the login itself is untouched, so re-auth must NOT be demanded.
        assert client.token_manager.reauth_required is None
        # And renewal is running, or the still-good credentials would rot.
        assert client.token_manager.seconds_until_next_refresh > 0
        # Credentials remain cacheable — a restore must not be forced to re-login.
        assert client.to_cache() != {}
    finally:
        await client.stop()


async def test_restore_survives_an_unrenewable_mqtt_jwt(fake_cloud: FakeMammotionCloud) -> None:
    """Same for the restore path, which starts the scheduler after the bootstrap."""
    scenario = fake_cloud.scenario
    first = MammotionClient()
    await first.login_and_initiate_cloud(scenario.account, scenario.password)
    cached = first.to_cache()
    await first.stop()
    await fake_cloud.baseline_counters()

    # Drop the cached broker credentials so the restore has to fetch them — with a
    # healthy JWT in the cache it never calls the endpoint and the knob is inert.
    cached.pop("mammotion_mqtt", None)
    scenario.mqtt_jwt_returns_no_data = True
    second = MammotionClient()
    try:
        await second.restore_credentials(scenario.account, scenario.password, cached)

        assert scenario.counters.get("mqtt_jwt_fetches", 0) > 0, "the JWT endpoint was never called"
        assert second.token_manager is not None
        assert second.token_manager.mqtt_unavailable is not None
        assert second.token_manager.reauth_required is None
        assert second.token_manager.seconds_until_next_refresh > 0
        # A transport-scoped failure must not spend a password grant.
        assert scenario.counters.get("password_grants", 0) == 0
    finally:
        await second.stop()
