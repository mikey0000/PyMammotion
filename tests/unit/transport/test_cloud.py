"""Send quota, firmware exemption and terminal auth flags — the CloudTransport surface.

Moved out of ``test_base.py`` with the members themselves: BLE inherits none of
this, so testing it against a bare ``Transport`` stub was testing a base class for
behaviour only two of its three subclasses have.
"""

import time
from unittest.mock import patch

import pytest

from pymammotion.device.mqtt_loop import _RATE_LIMITED_BACKOFF
from pymammotion.transport.base import TransportAvailability, TransportRateLimitedError, TransportType
from pymammotion.transport.cloud import CloudTransport


def _make_concrete_cloud_transport() -> CloudTransport:
    """Return a minimal concrete CloudTransport (abstract methods stubbed out)."""

    class _Stub(CloudTransport):
        @property
        def transport_type(self) -> TransportType:
            return TransportType.CLOUD_ALIYUN

        @property
        def is_connected(self) -> bool:
            return True

        @property
        def availability(self) -> TransportAvailability:
            return TransportAvailability.CONNECTED

        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def send(self, payload: bytes, iot_id: str = "", firmware_version: str = "1.0.0.0") -> None:
            pass

        async def _invoke(self, payload: bytes, iot_id: str) -> None:
            pass

    return _Stub()


def test_transport_not_rate_limited_initially() -> None:
    """A freshly created CloudTransport is not rate-limited."""
    t = _make_concrete_cloud_transport()
    assert t.is_rate_limited is False


def test_transport_set_rate_limited_blocks_for_duration() -> None:
    """After set_rate_limited(), is_rate_limited is True until the ban expires."""
    t = _make_concrete_cloud_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True


def test_transport_rate_limit_expires_after_12_hours() -> None:
    """is_rate_limited returns False once _rate_limited_until is in the past."""
    t = _make_concrete_cloud_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True

    # Simulate the 12-hour ban having expired.
    t._rate_limited_until = time.monotonic() - 1  # noqa: SLF001
    assert t.is_rate_limited is False


def test_transport_rate_limit_duration_is_12_hours() -> None:
    """set_rate_limited() sets a ban of exactly _RATE_LIMIT_DURATION seconds."""
    t = _make_concrete_cloud_transport()
    before = time.monotonic()
    t.set_rate_limited()
    after = time.monotonic()

    # Ban should expire roughly 12 hours from now.
    expected = 43200.0  # 12 h
    assert before + expected <= t._rate_limited_until <= after + expected  # noqa: SLF001


def test_transport_rate_limit_constant_matches_handle_backoff() -> None:
    """CloudTransport._RATE_LIMIT_DURATION and the poll loop's backoff must agree."""
    t = _make_concrete_cloud_transport()
    assert t._RATE_LIMIT_DURATION == _RATE_LIMITED_BACKOFF  # noqa: SLF001


def test_quota_block_self_clears_when_window_slides_under_limit() -> None:
    """The self-imposed send-quota must release the instant the rolling window drops back
    under the limit — no fixed-duration ban (that is reserved for cloud 429s).
    """
    t = _make_concrete_cloud_transport()
    limit = t._SEND_LIMIT  # noqa: SLF001
    window = t._SEND_WINDOW  # noqa: SLF001
    clock = {"now": 100_000.0}

    with patch("pymammotion.transport.cloud.time.monotonic", side_effect=lambda: clock["now"]):
        for _ in range(limit):
            t.record_send()

        # Quota exhausted — blocked — but NO fixed cloud ban was imposed.
        assert t.is_rate_limited is True
        assert t._rate_limited_until == 0.0  # noqa: SLF001 — quota path must not set the cloud timer
        # Release is exactly one window after the oldest send.
        assert t.seconds_until_send_available() == window

        # Slide the window so the oldest send ages out → count drops to limit-1.
        clock["now"] += window + 1.0
        assert t.is_rate_limited is False
        assert t.seconds_until_send_available() == 0.0


def test_seconds_until_send_available_is_max_of_cloud_ban_and_quota() -> None:
    """When both a cloud ban and the quota are active, the longer release time wins."""
    t = _make_concrete_cloud_transport()
    clock = {"now": 0.0}

    with patch("pymammotion.transport.cloud.time.monotonic", side_effect=lambda: clock["now"]):
        t._rate_limited_until = 100.0  # noqa: SLF001 — short cloud ban
        for _ in range(t._SEND_LIMIT):  # noqa: SLF001 — full window, release a whole window away
            t.record_send()

        # Quota release (_SEND_WINDOW) dominates the 100 s cloud ban.
        assert t.seconds_until_send_available() == t._SEND_WINDOW  # noqa: SLF001

        # Clear the quota; the cloud ban now dominates.
        t._send_timestamps.clear()  # noqa: SLF001
        assert t.seconds_until_send_available() == 100.0
        assert t.is_rate_limited is True  # cloud ban still active


def test_is_send_blocked_applies_firmware_exemption() -> None:
    """is_send_blocked() must exempt firmware >= RATE_LIMIT_REMOVED_VERSION."""
    t = _make_concrete_cloud_transport()
    t.set_rate_limited()
    assert t.is_rate_limited is True

    # Pre-removal firmware: blocked.
    assert t.is_send_blocked("1.11.5.0") is True
    # Post-removal firmware (e.g. Luba Mini 2.x): exempt.
    assert t.is_send_blocked("2.3.27.16") is False
    # Unknown / unparseable version: fail closed (blocked).
    assert t.is_send_blocked("") is True

    # Not rate-limited at all: never blocked, regardless of firmware.
    t._rate_limited_until = time.monotonic() - 1  # noqa: SLF001
    assert t.is_send_blocked("1.11.5.0") is False


def test_cloud_is_usable_goes_false_on_terminal_auth_failure() -> None:
    """The auth-flag notion of usable belongs here, not on the shared base."""
    t = _make_concrete_cloud_transport()
    assert t.is_usable is True

    t.mark_auth_failed()
    assert t.is_usable is False


def test_unrecoverable_auth_failure_is_reported_separately() -> None:
    t = _make_concrete_cloud_transport()
    assert t.is_unrecoverable_auth_failure is False

    t.mark_unrecoverable_auth_failure()
    assert t.is_unrecoverable_auth_failure is True
    assert t.is_usable is False


# The two block sources are separate, and a user-initiated send honours only one


def test_the_two_block_sources_are_reported_separately() -> None:
    """`is_rate_limited` fuses them; the halves have to stay individually readable."""
    t = _make_concrete_cloud_transport()
    assert t.is_cloud_banned is False
    assert t.is_quota_exhausted is False

    t.set_rate_limited()
    assert t.is_cloud_banned is True
    assert t.is_quota_exhausted is False, "a 429 must not be reported as our own quota"
    assert t.is_rate_limited is True


def test_quota_exhaustion_does_not_look_like_a_cloud_ban() -> None:
    t = _make_concrete_cloud_transport()
    for _ in range(t._SEND_LIMIT):  # noqa: SLF001
        t.record_send()

    assert t.is_quota_exhausted is True
    assert t.is_cloud_banned is False, "the self-imposed quota must not set the cloud timer"
    assert t.is_rate_limited is True


def test_user_initiated_spends_past_the_quota_but_not_past_a_cloud_ban() -> None:
    """The whole point of the flag: our own budget yields to a person, the server's does not."""
    t = _make_concrete_cloud_transport()
    for _ in range(t._SEND_LIMIT):  # noqa: SLF001
        t.record_send()

    assert t.is_send_blocked("1.11.5.0") is True
    assert t.is_send_blocked("1.11.5.0", user_initiated=True) is False

    t.set_rate_limited()
    assert t.is_send_blocked("1.11.5.0", user_initiated=True) is True


def test_firmware_exemption_still_wins_for_user_initiated() -> None:
    """Quota-free firmware is exempt regardless of who initiated the send."""
    t = _make_concrete_cloud_transport()
    t.set_rate_limited()
    assert t.is_send_blocked("2.3.27.16", user_initiated=True) is False


async def test_send_user_reaches_the_broker_while_the_quota_is_exhausted() -> None:
    t = _make_concrete_cloud_transport()
    sent: list[bytes] = []
    t._invoke = lambda payload, iot_id: _record(sent, payload)  # type: ignore[assignment, method-assign]
    for _ in range(t._SEND_LIMIT):  # noqa: SLF001
        t.record_send()

    await t.send_user(b"\x01", iot_id="iot", firmware_version="1.11.5.0")

    assert sent == [b"\x01"]


async def test_send_user_is_still_counted_against_the_budget() -> None:
    """The window has to reflect real traffic or the next cadence decision is a lie."""
    t = _make_concrete_cloud_transport()
    t._invoke = lambda payload, iot_id: _record([], payload)  # type: ignore[assignment, method-assign]

    await t.send_user(b"\x01", iot_id="iot", firmware_version="1.11.5.0")

    assert t.sends_in_window() == 1


async def test_send_user_refuses_while_the_cloud_ban_is_active() -> None:
    t = _make_concrete_cloud_transport()
    sent: list[bytes] = []
    t._invoke = lambda payload, iot_id: _record(sent, payload)  # type: ignore[assignment, method-assign]
    t.set_rate_limited()

    with pytest.raises(TransportRateLimitedError):
        await t.send_user(b"\x01", iot_id="iot", firmware_version="1.11.5.0")

    assert sent == []


async def _record(sink: list[bytes], payload: bytes) -> None:
    sink.append(payload)
