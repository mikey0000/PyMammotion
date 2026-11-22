"""Tests for TokenManager's clock-driven refresh scheduler.

Every other refresh path is lazy — it runs because something asked for a
credential.  When all of an account's devices are offline the poll loop stops
sending, so no HTTP call is made, ensure_token_valid never fires, and the
in-band Aliyun expiry check inside send_cloud_command never runs.  Without a
clock-driven renewal the credentials rot until the *refresh* tokens expire and
recovery needs the user.

Covers seconds_until_next_refresh, _refresh_due_credentials, and the
start_refresh_scheduler / stop_refresh_scheduler loop.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.auth import token_manager as token_manager_module
from pymammotion.auth.token_manager import MQTTCredentials, TokenManager

from tests._helpers import let_others_run, wait_until
from tests.unit.auth._helpers import make_aliyun_gateway, make_http_mock, make_mqtt_creds


def _tm_scheduled(
    *, http_ttl: float = 7200.0, mqtt_ttl: float | None = None, aliyun_ttl: float | None = None
) -> tuple[TokenManager, AsyncMock]:
    http = make_http_mock(
        refresh_code=0,
        access_token="tok2",
        refresh_token="ref2",
        expires_in=7200.0,
        mqtt_jwt="jwt-new",
        mqtt_host="h",
        mqtt_client_id="c",
        mqtt_username="u",
        login_info=MagicMock(access_token="tok", refresh_token="ref"),
    )
    http.expires_in = time.time() + http_ttl
    tm = TokenManager("user@example.com", http)
    if mqtt_ttl is not None:
        tm._mqtt_creds = MQTTCredentials("h", "c", "u", "j", time.time() + mqtt_ttl)  # noqa: SLF001
    if aliyun_ttl is not None:
        tm.attach_cloud_gateway(_gateway_expiring_in(aliyun_ttl))
    return tm, http


def _gateway_expiring_in(ttl: float, iot_token_expire: int = 7200) -> MagicMock:
    """A gateway whose current iotToken expires in *ttl* seconds; a refresh issues a new one now."""
    gateway = make_aliyun_gateway(
        issued_at=int(time.time() + ttl) - iot_token_expire, iot_token="iot-old", iot_token_expire=iot_token_expire
    )

    async def _refresh(*, force: bool = False) -> None:
        gateway.session_by_authcode_response.data.iotToken = "iot-new"
        gateway._iot_token_issued_at = int(time.time())  # noqa: SLF001

    gateway.check_or_refresh_session.side_effect = _refresh
    return gateway


# ── when the next refresh is due ────────────────────────────────────────────


def test_next_refresh_uses_http_lead_time() -> None:
    """The HTTP token is renewed 5 minutes before it expires."""
    tm, _ = _tm_scheduled(http_ttl=3600.0)
    assert 3600 - 300 - 2 < tm.seconds_until_next_refresh <= 3600 - 300


def test_next_refresh_picks_the_earliest_credential() -> None:
    """Whichever expires soonest sets the wake-up, not the first one checked."""
    tm, _ = _tm_scheduled(http_ttl=86400.0, mqtt_ttl=3600.0)  # mqtt lead is 1800
    assert 3600 - 1800 - 2 < tm.seconds_until_next_refresh <= 3600 - 1800


@pytest.mark.regression
def test_an_attached_aliyun_session_is_scheduled_for_renewal() -> None:
    """The gateway's session was never adopted, so the scheduler skipped Aliyun and idle accounts aged out (2460)."""
    tm, _ = _tm_scheduled(http_ttl=86400.0, aliyun_ttl=5400.0)  # aliyun lead is 3600
    assert 5400 - 3600 - 2 < tm.seconds_until_next_refresh <= 5400 - 3600


@pytest.mark.regression
async def test_a_due_aliyun_session_is_renewed_and_handed_to_the_transport() -> None:
    """Renewed on the clock, the new iotToken reaches the transport's next bind and the host's cache."""
    tm, _ = _tm_scheduled(http_ttl=86400.0, aliyun_ttl=60.0)
    bound: list[str] = []
    tm.on_aliyun_token_refreshed = bound.append
    persisted = AsyncMock()
    tm.on_credentials_updated = persisted

    assert await tm._refresh_due_credentials() is True  # noqa: SLF001

    assert bound == ["iot-new"]
    persisted.assert_awaited_once()


def test_next_refresh_is_zero_when_already_due() -> None:
    tm, _ = _tm_scheduled(http_ttl=60.0)  # inside the 300s lead
    assert tm.seconds_until_next_refresh == 0.0


def test_next_refresh_is_capped() -> None:
    """A far-future expiry still re-checks hourly, so later credentials get picked up."""
    tm, _ = _tm_scheduled(http_ttl=86400.0 * 30)
    assert tm.seconds_until_next_refresh == 3600.0


def test_next_refresh_survives_unusable_expiry() -> None:
    """A malformed expiry must not kill the background task."""
    tm, http = _tm_scheduled()
    http.expires_in = "not a number"
    assert tm.seconds_until_next_refresh == 3600.0


# ── what gets refreshed ─────────────────────────────────────────────────────


async def test_due_http_token_is_refreshed_with_no_api_traffic() -> None:
    """The case this exists for: nothing is being sent, yet the token still renews."""
    tm, http = _tm_scheduled(http_ttl=60.0)

    assert await tm._refresh_due_credentials() is True  # noqa: SLF001

    http.refresh_token_v2.assert_awaited_once()
    http.login_v2.assert_not_called()


async def test_nothing_refreshed_when_nothing_is_due() -> None:
    tm, http = _tm_scheduled(http_ttl=7200.0, mqtt_ttl=86400.0)

    await tm._refresh_due_credentials()  # noqa: SLF001

    http.refresh_token_v2.assert_not_awaited()
    http.get_mqtt_credentials.assert_not_awaited()


async def test_only_the_due_credential_is_refreshed() -> None:
    """A due MQTT JWT must not drag the healthy HTTP token into a rotation."""
    tm, http = _tm_scheduled(http_ttl=86400.0, mqtt_ttl=60.0)

    await tm._refresh_due_credentials()  # noqa: SLF001

    http.get_mqtt_credentials.assert_awaited_once()
    http.refresh_token_v2.assert_not_awaited()


async def test_http_is_refreshed_before_the_credentials_derived_from_it() -> None:
    """Both due: the JWT is minted with the access token, so HTTP must go first."""
    tm, http = _tm_scheduled(http_ttl=60.0, mqtt_ttl=60.0)
    order: list[str] = []
    http.refresh_token_v2.side_effect = lambda *a, **k: (
        order.append("http"),
        MagicMock(code=0, data=MagicMock(access_token="t", refresh_token="r", expires_in=7200.0)),
    )[1]
    http.get_mqtt_credentials.side_effect = lambda *a, **k: (
        order.append("mqtt"),
        MagicMock(data=MagicMock(host="h", client_id="c", username="u", jwt="j")),
    )[1]

    await tm._refresh_due_credentials()  # noqa: SLF001

    assert order == ["http", "mqtt"]


async def test_transport_scoped_failure_does_not_stop_other_refreshes() -> None:
    """A dead MQTT JWT must not prevent the Aliyun session from being renewed."""
    tm, http = _tm_scheduled(http_ttl=86400.0, mqtt_ttl=60.0, aliyun_ttl=60.0)
    http.get_mqtt_credentials = AsyncMock(return_value=MagicMock(data=None))

    assert await tm._refresh_due_credentials() is False  # noqa: SLF001

    assert tm.mqtt_unavailable is not None
    assert tm.reauth_required is None
    tm._cloud_gateway.check_or_refresh_session.assert_awaited()  # noqa: SLF001


# ── the loop ────────────────────────────────────────────────────────────────


async def test_scheduler_renews_a_due_token_then_sleeps() -> None:
    """End-to-end: start the loop with a due token and watch it renew, unprompted."""
    tm, http = _tm_scheduled(http_ttl=60.0)

    def _advance(*_a, **_k) -> MagicMock:
        http.expires_in = time.time() + 7200
        return MagicMock(code=0, data=MagicMock(access_token="t2", refresh_token="r2", expires_in=7200.0))

    http.refresh_token_v2.side_effect = _advance

    tm.start_refresh_scheduler()
    for _ in range(20):  # let the loop run until it settles into its sleep
        await asyncio.sleep(0)
        if http.refresh_token_v2.await_count:
            break
    await tm.stop_refresh_scheduler()

    http.refresh_token_v2.assert_awaited_once()


async def test_scheduler_stops_once_the_account_needs_reauth() -> None:
    """A dead refresh token is terminal — no point waking up again."""
    tm, http = _tm_scheduled(http_ttl=60.0)
    http.refresh_token_v2.return_value = MagicMock(code=401, data=None)

    tm.start_refresh_scheduler()
    for _ in range(20):
        await asyncio.sleep(0)
        if tm._scheduler_task.done():  # noqa: SLF001
            break

    assert tm.reauth_required is not None
    assert tm._scheduler_task.done()  # noqa: SLF001
    await tm.stop_refresh_scheduler()


async def test_scheduler_is_idempotent_and_cancellable() -> None:
    tm, _ = _tm_scheduled(http_ttl=7200.0)

    tm.start_refresh_scheduler()
    first = tm._scheduler_task  # noqa: SLF001
    tm.start_refresh_scheduler()
    assert tm._scheduler_task is first, "second start must not spawn a rival task"  # noqa: SLF001

    await tm.stop_refresh_scheduler()
    assert first.done()
    await tm.stop_refresh_scheduler()  # stopping twice is safe


async def test_scheduler_sleep_skips_credentials_behind_terminal_flags() -> None:
    """A given-up transport's past-due expiry must not wake the scheduler forever."""
    http = make_http_mock()
    http.expires_in = time.time() + 86400
    tm = TokenManager("acc1", http)
    await tm.initialize(None, None, make_mqtt_creds(-100))  # already past due

    assert tm.seconds_until_next_refresh == 0.0
    tm._mark_mqtt_unavailable("mqtt dead")
    assert tm.seconds_until_next_refresh > 0.0


@pytest.mark.regression
async def test_a_due_http_token_refreshed_by_someone_else_meanwhile_is_not_refreshed_again() -> None:
    """The due check ran before queuing for the lock, so a refresh that landed while waiting was repeated.

    Each repeat rotates the refresh token server-side for nothing.
    """
    tm, http = _tm_scheduled(http_ttl=60.0)
    async with tm._lock:  # noqa: SLF001 — another refresh path holds the lock
        scheduled = asyncio.ensure_future(tm._refresh_due_credentials())  # noqa: SLF001
        await let_others_run()
        http.expires_in = time.time() + 7200  # ...and renews the token before releasing it
    await asyncio.wait_for(scheduled, timeout=1.0)

    http.refresh_token_v2.assert_not_awaited()


async def test_scheduler_backs_off_after_a_transient_failure_and_tries_again(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(token_manager_module, "_SCHEDULER_RETRY_DELAY", 0.0)
    tm, http = _tm_scheduled(http_ttl=60.0)

    def _renew_on_the_second_try(*_a: object, **_k: object) -> MagicMock:
        if http.refresh_token_v2.await_count == 1:
            raise ConnectionError("cloud unreachable")
        http.expires_in = time.time() + 7200
        return MagicMock(code=0, data=MagicMock(access_token="t2", refresh_token="r2", expires_in=7200.0))

    http.refresh_token_v2.side_effect = _renew_on_the_second_try

    tm.start_refresh_scheduler()
    try:
        await wait_until(lambda: http.refresh_token_v2.await_count == 2)
    finally:
        await tm.stop_refresh_scheduler()

    assert tm.reauth_required is None


async def test_scheduler_retries_a_deferred_aliyun_session_until_it_is_established(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restore's transient failure is retried on the clock, and the client hears when it succeeds."""
    monkeypatch.setattr(token_manager_module, "_SCHEDULER_RETRY_DELAY", 0.0)
    tm, http = _tm_scheduled(http_ttl=86400.0)
    http.login_info = MagicMock()
    gateway = make_aliyun_gateway(issued_at=int(time.time()))
    failures = [ConnectionError("down"), ConnectionError("still down")]

    async def _get_region(_country_code: str) -> None:
        if failures:
            raise failures.pop(0)
        gateway.region_response = MagicMock()

    gateway.get_region.side_effect = _get_region
    established = AsyncMock()
    tm.on_aliyun_established = established

    assert await tm.recover_aliyun(gateway) is None
    tm.start_refresh_scheduler()
    try:
        await wait_until(lambda: established.await_count == 1)
    finally:
        await tm.stop_refresh_scheduler()

    established.assert_awaited_once_with(gateway)
    assert tm.cloud_gateway is gateway
    assert tm.aliyun_unavailable is None
