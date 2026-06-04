"""Regression tests for bug-fix H7: named-parameter ``__init__`` for the
three Aliyun exceptions that previously used ``*args`` and indexed into
``args[1]`` for ``iot_id``.

The pre-fix signatures broke in two ways:

* Single-arg construction (``TooManyRequestsException("msg")``) raised
  ``IndexError`` on ``args[1]`` instead of a clear ``TypeError``.
* Keyword-arg construction (``TooManyRequestsException(message="m",
  iot_id="x")``) wasn't supported at all.

These tests pin down the new, explicit signature on:

* :class:`pymammotion.aliyun.exceptions.TooManyRequestsException`
* :class:`pymammotion.aliyun.exceptions.DeviceOfflineException`
* :class:`pymammotion.aliyun.exceptions.GatewayTimeoutException`
"""

from __future__ import annotations

import pytest

from pymammotion.aliyun.exceptions import (
    DeviceOfflineException,
    GatewayTimeoutException,
    TooManyRequestsException,
)

# ---------------------------------------------------------------------------
# TooManyRequestsException
# ---------------------------------------------------------------------------


def test_too_many_requests_named_args() -> None:
    exc = TooManyRequestsException(message="rate limited", iot_id="iot-id")
    assert exc.iot_id == "iot-id"
    assert "rate limited" in str(exc)


def test_too_many_requests_positional_args_still_supported() -> None:
    exc = TooManyRequestsException("rate limited", "iot-id")
    assert exc.iot_id == "iot-id"
    assert "rate limited" in str(exc)


def test_too_many_requests_missing_iot_id_clear_error() -> None:
    with pytest.raises(TypeError):
        TooManyRequestsException("rate limited")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# DeviceOfflineException
# ---------------------------------------------------------------------------


def test_device_offline_named_args() -> None:
    exc = DeviceOfflineException(message="offline", iot_id="iot-id")
    assert exc.iot_id == "iot-id"
    assert "offline" in str(exc)


def test_device_offline_positional_args_still_supported() -> None:
    # Real callers pass an int code first (e.g. 6205), then iot_id.
    exc = DeviceOfflineException(6205, "iot-id")
    assert exc.iot_id == "iot-id"
    assert "6205" in str(exc)


def test_device_offline_missing_iot_id_clear_error() -> None:
    with pytest.raises(TypeError):
        DeviceOfflineException("offline")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# GatewayTimeoutException
# ---------------------------------------------------------------------------


def test_gateway_timeout_named_args() -> None:
    exc = GatewayTimeoutException(message="timeout", iot_id="iot-id")
    assert exc.iot_id == "iot-id"
    assert "timeout" in str(exc)


def test_gateway_timeout_positional_args_still_supported() -> None:
    exc = GatewayTimeoutException(20056, "iot-id")
    assert exc.iot_id == "iot-id"
    assert "20056" in str(exc)


def test_gateway_timeout_missing_iot_id_clear_error() -> None:
    with pytest.raises(TypeError):
        GatewayTimeoutException("timeout")  # type: ignore[call-arg]
