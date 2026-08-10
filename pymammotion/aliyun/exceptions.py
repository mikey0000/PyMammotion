"""Exceptions for the Aliyun cloud gateway and related MQTT clients."""

from pymammotion.transport.base import SessionExpiredError, TransportType

# ---------------------------------------------------------------------------
# Cloud response codes
#
# Both cloud send paths — CloudIOTGateway.send_cloud_command (Aliyun) and
# MQTTTransport._invoke (Mammotion direct) — classify the same failures, so the
# code sets live here once instead of being pattern-matched inline in each.  Add
# a newly-observed code to the set below and both paths pick it up.
#
# Values cross-checked against the Mammotion Android app 2.3.8.201
# (AppConstants.BindCode).
# ---------------------------------------------------------------------------

#: The cloud accepted the request but the device is not reachable right now.
#: 6205/6221 are Aliyun-era codes; 50103/50104 are the Mammotion-direct ones
#: (APK: BindCode.DEVICE_OFFLINE = 6221, BindCode.MA_DEVICE_OFFLINE = 50104).
DEVICE_OFFLINE_CODES = frozenset({6205, 6221, 50103, 50104})

#: The device is no longer bound to this account — usually a migration from the
#: Aliyun platform to Mammotion direct MQTT.
DEVICE_UNBOUND_CODES = frozenset({29004})

#: The cloud reached the device but it did not answer in time.
GATEWAY_TIMEOUT_CODES = frozenset({20056})

#: Pairing attempted outside the device's bind window, or with a dead QR code
#: (APK: BindCode.NOT_IN_BIND_WINDOW = 6618, MA_NOT_IN_BIND_WINDOW = 50105,
#: QR_NOT_EXIT = 2067).  Recorded for completeness: this library discovers
#: already-bound devices and has no pairing flow, so nothing raises these yet.
BIND_WINDOW_CLOSED_CODES = frozenset({6618, 50105})
QR_CODE_INVALID_CODES = frozenset({2067})


class AuthRefreshException(Exception):
    """Raise exception when library cannot refresh token."""


class DeviceOfflineException(Exception):
    """Raise exception when device is offline."""

    def __init__(self, message: object, iot_id: str) -> None:
        super().__init__(message)
        self.iot_id = iot_id


class DeviceUnboundException(Exception):
    """Raise when the cloud reports the device is no longer bound to the account.

    Aliyun returns code 29004 ("device is unbind") when a device has been removed
    from the account on the Aliyun (pre-2025) platform — usually because it has
    migrated to the Mammotion direct MQTT (post-2025) platform.
    """

    def __init__(self, message: object, iot_id: str) -> None:
        super().__init__(message)
        self.iot_id = iot_id


class FailedRequestException(Exception):
    """Raise exception when request response is bad."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[0]


class GatewayTimeoutException(Exception):
    """Raise exception when the gateway times out."""

    def __init__(self, message: object, iot_id: str) -> None:
        super().__init__(message)
        self.iot_id = iot_id


class TooManyRequestsException(Exception):
    """Raise exception when the gateway returns HTTP 429 (rate limited)."""

    def __init__(self, message: object, iot_id: str) -> None:
        super().__init__(message)
        self.iot_id = iot_id


class CloudSetupError(Exception):
    """Raised when the Aliyun cloud gateway setup sequence fails (region, AEP, session).

    Indicates a recoverable connectivity or API error, not a logic bug — callers
    should surface this as a "cannot connect" condition rather than crashing.
    """


class LoginException(Exception):
    """Raise exception when library cannot log in."""


class CheckSessionException(SessionExpiredError):
    """Backward-compatible alias for SessionExpiredError defaulting to CLOUD_ALIYUN."""

    def __init__(self, message: str = "") -> None:
        super().__init__(TransportType.CLOUD_ALIYUN, message)


EXPIRED_CREDENTIAL_EXCEPTIONS = SessionExpiredError
