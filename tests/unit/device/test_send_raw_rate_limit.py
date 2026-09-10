"""``send_raw`` must not report success for a send the rate limiter blocked.

Written against the unfixed code, where the ``except TransportRateLimitedError``
in ``send_raw`` logged a warning and returned normally — so
``send_command_with_args`` completed without error for a payload the device
never received, and no caller could tell.
"""

from __future__ import annotations

import pytest

from pymammotion.transport.base import TransportRateLimitedError, TransportType
from tests._helpers import make_mock_handle, make_mock_transport


async def test_send_raw_raises_when_the_pre_flight_gate_blocks_the_send() -> None:
    """``_send_marked``'s own gate fires before the transport is touched."""
    transport = make_mock_transport(TransportType.CLOUD_ALIYUN)
    transport.is_send_blocked.return_value = True
    transport.seconds_until_send_available.return_value = 900.0
    handle = make_mock_handle(mqtt_transport=transport)
    await handle.add_transport(transport)

    with pytest.raises(TransportRateLimitedError):
        await handle.send_raw(b"payload")

    transport.send.assert_not_awaited()
    await handle.stop()


async def test_send_raw_raises_when_the_transport_itself_rejects_the_send() -> None:
    """The same must hold for the quota check inside ``Transport.send``."""
    transport = make_mock_transport(TransportType.CLOUD_ALIYUN)
    transport.send.side_effect = TransportRateLimitedError("rate-limited for 900s more")
    handle = make_mock_handle(mqtt_transport=transport)
    await handle.add_transport(transport)

    with pytest.raises(TransportRateLimitedError):
        await handle.send_raw(b"payload")

    await handle.stop()


async def test_the_error_says_how_long_the_block_lasts() -> None:
    """The queue logs the exception text, so the remaining time must be in it."""
    transport = make_mock_transport(TransportType.CLOUD_ALIYUN)
    transport.is_send_blocked.return_value = True
    transport.seconds_until_send_available.return_value = 900.0
    handle = make_mock_handle(mqtt_transport=transport)
    await handle.add_transport(transport)

    with pytest.raises(TransportRateLimitedError, match="900"):
        await handle.send_raw(b"payload")

    await handle.stop()
