"""Shared pytest fixtures for the Luba-API test suite."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from pymammotion.device.handle import DeviceHandle


@pytest.fixture(autouse=True)
def _suppress_ble_polling_loop():
    """Globally suppress the BLE polling-loop auto-start.

    The polling loop's first iteration enqueues either a continuous-stream
    renewal (ACTIVE/IDLE-continuous modes) or a count=1 poll, both of which
    fire through the queue and would race with send-routing tests that drain
    the queue.  Tests that need to exercise the polling loop directly should
    invoke ``handle._ble_polling_loop()`` themselves or re-patch the starter.
    """
    with patch.object(DeviceHandle, "_start_ble_polling_loop", lambda self: None):
        yield
