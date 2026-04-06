"""Exceptions for the Aliyun cloud gateway and related MQTT clients."""

from Tea.exceptions import UnretryableException

from pymammotion.transport.base import SessionExpiredError, TransportType


class AuthRefreshException(Exception):
    """Raise exception when library cannot refresh token."""


class DeviceOfflineException(Exception):
    """Raise exception when device is offline."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[1]


class FailedRequestException(Exception):
    """Raise exception when request response is bad."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[0]


class NoConnectionException(UnretryableException):
    """Raise exception when device is unreachable."""


class GatewayTimeoutException(Exception):
    """Raise exception when the gateway times out."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[1]


class TooManyRequestsException(Exception):
    """Raise exception when the gateway times out."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[1]


class LoginException(Exception):
    """Raise exception when library cannot log in."""


class CheckSessionException(SessionExpiredError):
    """Backward-compatible alias for SessionExpiredError defaulting to CLOUD_ALIYUN."""

    def __init__(self, message: str = "") -> None:
        super().__init__(TransportType.CLOUD_ALIYUN, message)


EXPIRED_CREDENTIAL_EXCEPTIONS = SessionExpiredError
