"""Exceptions for the Aliyun cloud gateway and related MQTT clients."""

from Tea.exceptions import UnretryableException


class SetupException(Exception):
    """Raise when mqtt expires token or token is invalid."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[1]


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


class CheckSessionException(Exception):
    """Raise exception when checking session results in a failure."""


EXPIRED_CREDENTIAL_EXCEPTIONS = (CheckSessionException, SetupException)
