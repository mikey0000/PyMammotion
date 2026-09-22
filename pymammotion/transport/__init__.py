"""Transport layer for PyMammotion — abstractions for MQTT and BLE connections."""

from __future__ import annotations

from pymammotion.transport.aliyun_mqtt import AliyunMQTTConfig, AliyunMQTTTransport
from pymammotion.transport.base import (
    AuthError,
    BLEUnavailableError,
    CommandTimeoutError,
    ConcurrentRequestError,
    EventBus,
    NoBLEAddressKnownError,
    NoTransportAvailableError,
    ReLoginRequiredError,
    SagaFailedError,
    SagaInterruptedError,
    Subscription,
    Transport,
    TransportAvailability,
    TransportError,
    TransportRateLimitedError,
    TransportType,
)
from pymammotion.transport.cloud import CloudTransport

__all__ = [
    "AliyunMQTTConfig",
    "AliyunMQTTTransport",
    "AuthError",
    "BLEUnavailableError",
    "CloudTransport",
    "CommandTimeoutError",
    "ConcurrentRequestError",
    "EventBus",
    "NoBLEAddressKnownError",
    "NoTransportAvailableError",
    "ReLoginRequiredError",
    "SagaFailedError",
    "SagaInterruptedError",
    "Subscription",
    "Transport",
    "TransportAvailability",
    "TransportError",
    "TransportRateLimitedError",
    "TransportType",
]
