"""AliyunMQTTTransport — concrete Transport for Aliyun IoT MQTT.

Differences from MQTTTransport (Mammotion direct MQTT):
- Credentials use HMAC-SHA1 signed client_id / password (Aliyun IoT convention).
- Topics have separate subscribe sets and a single publish topic.
- Incoming messages are JSON envelopes; the transport unwraps the
  ``params.value.content`` base64 field and forwards raw bytes to on_message.
- TLS uses a bundled Aliyun / GlobalSign CA bundle (port 8883).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import ssl
import time
from typing import TYPE_CHECKING

import aiomqtt

from pymammotion.transport.base import AuthError, Transport, TransportAvailability, TransportError, TransportType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.auth.token_manager import AliyunCredentials

_logger = logging.getLogger(__name__)

# Aliyun IoT broker CA certificate bundle (GlobalSign + Aliyun IoT roots)
_ALIYUN_BROKER_CA_DATA = """
-----BEGIN CERTIFICATE-----
MIIDdTCCAl2gAwIBAgILBAAAAAABFUtaw5QwDQYJKoZIhvcNAQEFBQAwVzELMAkG
A1UEBhMCQkUxGTAXBgNVBAoTEEdsb2JhbFNpZ24gbnYtc2ExEDAOBgNVBAsTB1Jv
b3QgQ0ExGzAZBgNVBAMTEkdsb2JhbFNpZ24gUm9vdCBDQTAeFw05ODA5MDExMjAw
MDBaFw0yODAxMjgxMjAwMDBaMFcxCzAJBgNVBAYTAkJFMRkwFwYDVQQKExBHbG9i
YWxTaWduIG52LXNhMRAwDgYDVQQLEwdSb290IENBMRswGQYDVQQDExJHbG9iYWxT
aWduIFJvb3QgQ0EwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDaDuaZ
jc6j40+Kfvvxi4Mla+pIH/EqsLmVEQS98GPR4mdmzxzdzxtIK+6NiY6arymAZavp
xy0Sy6scTHAHoT0KMM0VjU/43dSMUBUc71DuxC73/OlS8pF94G3VNTCOXkNz8kHp
1Wrjsok6Vjk4bwY8iGlbKk3Fp1S4bInMm/k8yuX9ifUSPJJ4ltbcdG6TRGHRjcdG
snUOhugZitVtbNV4FpWi6cgKOOvyJBNPc1STE4U6G7weNLWLBYy5d4ux2x8gkasJ
U26Qzns3dLlwR5EiUWMWea6xrkEmCMgZK9FGqkjWZCrXgzT/LCrBbBlDSgeF59N8
9iFo7+ryUp9/k5DPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNVHRMBAf8E
BTADAQH/MB0GA1UdDgQWBBRge2YaRQ2XyolQL30EzTSo//z9SzANBgkqhkiG9w0B
AQUFAAOCAQEA1nPnfE920I2/7LqivjTFKDK1fPxsnCwrvQmeU79rXqoRSLblCKOz
yj1hTdNGCbM+w6DjY1Ub8rrvrTnhQ7k4o+YviiY776BQVvnGCv04zcQLcFGUl5gE
38NflNUVyRRBnMRddWQVDf9VMOyGj/8N7yy5Y0b2qvzfvGn9LhJIZJrglfCm7ymP
AbEVtQwdpf5pLGkkeB6zpxxxYu7KyJesF12KwvhHhm4qxFYxldBniYUr+WymXUad
DKqC5JlR3XC321Y9YeRq4VzW9v493kHMB65jUr9TU/Qr6cf9tveCX4XSQRjbgbME
HMUfpIBvFSDJ3gyICh3WZlXi/EjJKSZp4A==
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIID3zCCAsegAwIBAgISfiX6mTa5RMUTGSC3rQhnestIMA0GCSqGSIb3DQEBCwUA
MHcxCzAJBgNVBAYTAkNOMREwDwYDVQQIDAhaaGVqaWFuZzERMA8GA1UEBwwISGFu
Z3pob3UxEzARBgNVBAoMCkFsaXl1biBJb1QxEDAOBgNVBAsMB1Jvb3QgQ0ExGzAZ
BgNVBAMMEkFsaXl1biBJb1QgUm9vdCBDQTAgFw0yMzA3MDQwNjM2NThaGA8yMDUz
MDcwNDA2MzY1OFowdzELMAkGA1UEBhMCQ04xETAPBgNVBAgMCFpoZWppYW5nMREw
DwYDVQQHDAhIYW5nemhvdTETMBEGA1UECgwKQWxpeXVuIElvVDEQMA4GA1UECwwH
Um9vdCBDQTEbMBkGA1UEAwwSQWxpeXVuIElvVCBSb290IENBMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoK//6vc2oXhnvJD7BVhj6grj7PMlN2N4iNH4
GBmLmMdkF1z9eQLjksYc4Zid/FX67ypWFtdycOei5ec0X00m53Gvy4zLGBo2uKgi
T9IxMudmt95bORZbaph4VK82gPNU4ewbiI1q2loRZEHRdyPORTPpvNLHu8DrYBnY
Vg5feEYLLyhxg5M1UTrT/30RggHpaa0BYIPxwsKyylQ1OskOsyZQeOyPe8t8r2D4
RBpUGc5ix4j537HYTKSyK3Hv57R7w1NzKtXoOioDOm+YySsz9sTLFajZkUcQci4X
aedyEeguDLAIUKiYicJhRCZWljVlZActorTgjCY4zRajodThrQIDAQABo2MwYTAO
BgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB/zAdBgNVHQ4EFgQUkWHoKi2h
DlS1/rYpcT/Ue+aKhP8wHwYDVR0jBBgwFoAUkWHoKi2hDlS1/rYpcT/Ue+aKhP8w
DQYJKoZIhvcNAQELBQADggEBADrrLcBY7gDXN8/0KHvPbGwMrEAJcnF9z4MBxRvt
rEoRxhlvRZzPi7w/868xbipwwnksZsn0QNIiAZ6XzbwvIFG01ONJET+OzDy6ZqUb
YmJI09EOe9/Hst8Fac2D14Oyw0+6KTqZW7WWrP2TAgv8/Uox2S05pCWNfJpRZxOv
Lr4DZmnXBJCMNMY/X7xpcjylq+uCj118PBobfH9Oo+iAJ4YyjOLmX3bflKIn1Oat
vdJBtXCj3phpfuf56VwKxoxEVR818GqPAHnz9oVvye4sQqBp/2ynrKFxZKUaJtk0
7UeVbtecwnQTrlcpWM7ACQC0OO0M9+uNjpKIbksv1s11xu0=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIFgzCCA2ugAwIBAgIORea7A4Mzw4VlSOb/RVEwDQYJKoZIhvcNAQEMBQAwTDE
gMB4GA1UECxMXR2xvYmFsU2lnbiBSb290IENBIC0gUjYxEzARBgNVBAoTCkdsb2
JhbFNpZ24xEzARBgNVBAMTCkdsb2JhbFNpZ24wHhcNMTQxMjEwMDAwMDAwWhcNM
zQxMjEwMDAwMDAwWjBMMSAwHgYDVQQLExdHbG9iYWxTaWduIFJvb3QgQ0EgLSBS
NjETMBEGA1UEChMKR2xvYmFsU2lnbjETMBEGA1UEAxMKR2xvYmFsU2lnbjCCAiI
wDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAJUH6HPKZvnsFMp7PPcNCPG0RQ
ssgrRIxutbPK6DuEGSMxSkb3/pKszGsIhrxbaJ0cay/xTOURQh7ErdG1rG1ofuT
ToVBu1kZguSgMpE3nOUTvOniX9PeGMIyBJQbUJmL025eShNUhqKGoC3GYEOfsSK
vGRMIRxDaNc9PIrFsmbVkJq3MQbFvuJtMgamHvm566qjuL++gmNQ0PAYid/kD3n
16qIfKtJwLnvnvJO7bVPiSHyMEAc4/2ayd2F+4OqMPKq0pPbzlUoSB239jLKJz9
CgYXfIWHSw1CM69106yqLbnQneXUQtkPGBzVeS+n68UARjNN9rkxi+azayOeSsJ
Da38O+2HBNXk7besvjihbdzorg1qkXy4J02oW9UivFyVm4uiMVRQkQVlO6jxTiW
m05OWgtH8wY2SXcwvHE35absIQh1/OZhFj931dmRl4QKbNQCTXTAFO39OfuD8l4
UoQSwC+n+7o/hbguyCLNhZglqsQY6ZZZZwPA1/cnaKI0aEYdwgQqomnUdnjqGBQ
Ce24DWJfncBZ4nWUx2OVvq+aWh2IMP0f/fMBH5hc8zSPXKbWQULHpYT9NLCEnFl
WQaYw55PfWzjMpYrZxCRXluDocZXFSxZba/jJvcE+kNb7gu3GduyYsRtYQUigAZ
cIN5kZeR1BonvzceMgfYFGM8KEyvAgMBAAGjYzBhMA4GA1UdDwEB/wQEAwIBBjA
PBgNVHRMBAf8EBTADAQH/MB0GA1UdDgQWBBSubAWjkxPioufi1xzWx/B/yGdToD
AfBgNVHSMEGDAWgBSubAWjkxPioufi1xzWx/B/yGdToDANBgkqhkiG9w0BAQwFA
AOCAgEAgyXt6NH9lVLNnsAEoJFp5lzQhN7craJP6Ed41mWYqVuoPId8AorRbrcW
c+ZfwFSY1XS+wc3iEZGtIxg93eFyRJa0lV7Ae46ZeBZDE1ZXs6KzO7V33EByrKP
rmzU+sQghoefEQzd5Mr6155wsTLxDKZmOMNOsIeDjHfrYBzN2VAAiKrlNIC5waN
rlU/yDXNOd8v9EDERm8tLjvUYAGm0CuiVdjaExUd1URhxN25mW7xocBFymFe944
Hn+Xds+qkxV/ZoVqW/hpvvfcDDpw+5CRu3CkwWJ+n1jez/QcYF8AOiYrg54NMMl
+68KnyBr3TsTjxKM4kEaSHpzoHdpx7Zcf4LIHv5YGygrqGytXm3ABdJ7t+uA/iU
3/gKbaKxCXcPu9czc8FB10jZpnOZ7BN9uBmm23goJSFmH63sUYHpkqmlD75HHTO
wY3WzvUy2MmeFe8nI+z1TIvWfspA9MRf/TuTAjB0yPEL+GltmZWrSZVxykzLsVi
VO6LAUP5MSeGbEYNNVMnbrt9x+vJJUEeKgDu+6B5dpffItKoZB0JaezPkvILFa9
x8jvOOJckvB595yEunQtYQEgfn7R8k8HWV+LLUNS60YMlOH1Zkd5d9VUWx+tJDf
LRVpOoERIyNiwmcUVhAn21klJwGW45hpxbqCo8YLoRT5s1gLXCmeDBVrJpBA=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIICCzCCAZGgAwIBAgISEdK7ujNu1LzmJGjFDYQdmOhDMAoGCCqGSM49BAMDME
YxCzAJBgNVBAYTAkJFMRkwFwYDVQQKExBHbG9iYWxTaWduIG52LXNhMRwwGgYD
VQQDExNHbG9iYWxTaWduIFJvb3QgRTQ2MB4XDTE5MDMyMDAwMDAwMFoXDTQ2MD
MyMDAwMDAwMFowRjELMAkGA1UEBhMCQkUxGTAXBgNVBAoTEEdsb2JhbFNpZ24g
bnYtc2ExHDAaBgNVBAMTE0dsb2JhbFNpZ24gUm9vdCBFNDYwdjAQBgcqhkjOPQ
IBBgUrgQQAIgNiAAScDrHPt+ieUnd1NPqlRqetMhkytAepJ8qUuwzSChDH2omw
lwxwEwkBjtjqR+q+soArzfwoDdusvKSGN+1wCAB16pMLey5SnCNoIwZD7JIvU4
Tb+0cUB+hflGddyXqBPCCjQjBAMA4GA1UdDwEB/wQEAwIBhjAPBgNVHRMBAf8E
BTADAQH/MB0GA1UdDgQWBBQxCpCPtsad0kRLgLWi5h+xEk8blTAKBggqhkjOPQ
QDAwNoADBlAjEA31SQ7Zvvi5QCkxeCmb6zniz2C5GMn0oUsfZkvLtoURMMA/cV
i4RguYv/Uo7njLwcAjA8+RHUjE7AwWHCFUyqqx0LMV87HOIAl0Qx5v5zli/alt
P+CAezNIm8BZ/3Hobui3A=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIFWjCCA0KgAwIBAgISEdK7udcjGJ5AXwqdLdDfJWfRMA0GCSqGSIb3DQEBDAU
AMEYxCzAJBgNVBAYTAkJFMRkwFwYDVQQKExBHbG9iYWxTaWduIG52LXNhMRwwGg
YDVQQDExNHbG9iYWxTaWduIFJvb3QgUjQ2MB4XDTE5MDMyMDAwMDAwMFoXDTQ2M
DMyMDAwMDAwMFowRjELMAkGA1UEBhMCQkUxGTAXBgNVBAoTEEdsb2JhbFNpZ24g
bnYtc2ExHDAaBgNVBAMTE0dsb2JhbFNpZ24gUm9vdCBSNDYwggIiMA0GCSqGSIb
3DQEBAQUAA4ICDwAwggIKAoICAQCsrHQy6LNl5brtQyYdpokNRbopiLKkHWPd08
EsCVeJOaFV6Wc0dwxu5FUdUiXSE2te4R2pt32JMl8Nnp8semNgQB+msLZ4j5lUl
ghYruQGvGIFAha/r6gjA7aUD7xubMLL1aa7DOn2wQL7Id5m3RerdELv8HQvJfTq
a1VbkNud316HCkD7rRlr+/fKYIje2sGP1q7Vf9Q8g+7XFkyDRTNrJ9CG0Bwta/O
rffGFqfUo0q3v84RLHIf8E6M6cqJaESvWJ3En7YEtbWaBkoe0G1h6zD8K+kZPT
Xhc+CtI4wSEy132tGqzZfxCnlEmIyDLPRT5ge1lFgBPGmSXZgjPjHvjK8Cd+RTy
G/FWaha/LIWFzXg4mutCagI0GIMXTpRW+LaCtfOW3T3zvn8gdz57GSNrLNRyc0N
XfeD412lPFzYE+cCQYDdF3uYM2HSNrpyibXRdQr4G9dlkbgIQrImwTDsHTUB+JM
WKmIJ5jqSngiCNI/onccnfxkF0oE32kRbcRoxfKWMxWXEM2G/CtjJ9++ZdU6Z+F
fy7dXxd7Pj2Fxzsx2sZy/N78CsHpdlseVR2bJ0cpm4O6XkMqCNqo98bMDGfsVR7
/mrLZqrcZdCinkqaByFrgY/bxFn63iLABJzjqls2k+g9vXqhnQt2sQvHnf3PmKg
Gwvgqo6GDoLclcqUC4wIDAQABo0IwQDAOBgNVHQ8BAf8EBAMCAYYwDwYDVR0TAQ
H/BAUwAwEB/zAdBgNVHQ4EFgQUA1yrc4GHqMywptWU4jaWSf8FmSwwDQYJKoZIh
vcNAQEMBQADggIBAHx47PYCLLtbfpIrXTncvtgdokIzTfnvpCo7RGkerNlFo048
p9gkUbJUHJNOxO97k4VgJuoJSOD1u8fpaNK7ajFxzHmuEajwmf3lH7wvqMxX63b
EIaZHU1VNaL8FpO7XJqti2kM3S+LGteWygxk6x9PbTZ4IevPuzz5i+6zoYMzRx6
Fcg0XERczzF2sUyQQCPtIkpnnpHs6i58FZFZ8d4kuaPp92CC1r2LpXFNqD6v6MV
enQTqnMdzGxRBF6XLE+0xRFFRhiJBPSy03OXIPBNvIQtQ6IbbjhVp+J3pZmOUdk
LG5NrmJ7v2B0GbhWrJKsFjLtrWhV/pi60zTe9Mlhww6G9kuEYO4Ne7UyWHmRVSy
BQ7N0H3qqJZ4d16GLuc1CLgSkZoNNiTW2bKg2SnkheCLQQrzRQDGQob4Ez8pn7f
XwgNNgyYMqIgXQBztSvwyeqiv5u+YfjyW6hY0XHgL+XVAEV8/+LbzvXMAaq7afJ
Mbfc2hIkCwU9D9SGuTSyxTDYWnP4vkYxboznxSjBF25cfe1lNj2M8FawTSLfJvd
kzrnE6JwYZ+vj+vYxXX4M2bUdGc6N3ec592kD3ZDZopD8p/7DEJ4Y9HiD2971KE
9dJeFt0g5QdYg/NA6s/rob8SKunE3vouXsXgxT7PntgMTzlSdriVZzH81Xwj3QE
UxeCp6
-----END CERTIFICATE-----
"""

_MQTT_PORT = 8883
_MQTT_KEEPALIVE = 60
_MQTT_MAX_INFLIGHT = 20
_MQTT_MAX_QUEUED = 40
_MQTT_RECONNECT_MIN_SEC = 1
_MQTT_RECONNECT_MAX_SEC = 60


@dataclass(frozen=True)
class AliyunMQTTConfig:
    """Frozen configuration for an AliyunMQTTTransport instance.

    Attributes:
        host: Aliyun IoT MQTT broker hostname, e.g.
            ``"{productKey}.iot-as-mqtt.{region}.aliyuncs.com"``.
        client_id: Full Aliyun MQTT client ID (including securemode / signmethod
            suffix). Built once per connection attempt via
            :meth:`AliyunMQTTTransport._build_credentials`.
        username: Aliyun MQTT username in the form ``"{deviceName}&{productKey}"``.
        password: HMAC-SHA1 signed password derived from the device secret.
        device_name: Aliyun IoT device name.
        product_key: Aliyun IoT product key.
        device_secret: Device secret used to sign connection credentials.
        iot_token: Short-lived Aliyun IoT session token, sent in the bind message.
        port: MQTT broker port (default 8883 for TLS).
        keepalive: MQTT keepalive interval in seconds.

    """

    host: str
    client_id_base: str
    username: str
    device_name: str
    product_key: str
    device_secret: str
    iot_token: str
    port: int = _MQTT_PORT
    keepalive: int = _MQTT_KEEPALIVE

    @classmethod
    def from_aliyun_credentials(
        cls,
        region_id: str,
        product_key: str,
        device_name: str,
        device_secret: str,
        credentials: AliyunCredentials,
        client_id_base: str | None = None,
    ) -> AliyunMQTTConfig:
        """Build an AliyunMQTTConfig from AliyunCredentials.

        Args:
            region_id: Aliyun region, e.g. ``"cn-shanghai"``.
            product_key: Aliyun IoT product key.
            device_name: Aliyun IoT device name.
            device_secret: Device secret for HMAC signing.
            credentials: Current :class:`AliyunCredentials` from the token manager.
            client_id_base: Optional override for the base client ID; defaults to
                ``"{product_key}&{device_name}"``.

        Returns:
            A fully constructed :class:`AliyunMQTTConfig`.

        """
        base = client_id_base or f"{product_key}&{device_name}"
        return cls(
            host=f"{product_key}.iot-as-mqtt.{region_id}.aliyuncs.com",
            client_id_base=base,
            username=f"{device_name}&{product_key}",
            device_name=device_name,
            product_key=product_key,
            device_secret=device_secret,
            iot_token=credentials.iot_token,
        )


class AliyunMQTTTransport(Transport):
    """Concrete Transport for the Aliyun IoT MQTT platform.

    Separate subscribe and publish topics
    ------------------------------------
    Aliyun IoT uses a split topic model: the broker pushes data to
    ``/sys/{productKey}/{deviceName}/app/down/...`` topics, while commands
    are published to ``/sys/{productKey}/{deviceName}/app/up/...`` (or
    thing model topics).  Call :meth:`add_subscribe_topic` to register
    inbound topics and :meth:`set_publish_topic` to set the outbound topic.

    Envelope unwrapping
    -------------------
    Incoming JSON messages wrap the device payload in a base64-encoded
    ``params.value.content`` field.  The transport decodes this field and
    forwards the raw bytes to the ``on_message`` callback; the broker layer
    is responsible for protobuf decoding.

    Authentication
    --------------
    HMAC-SHA1 credentials are re-derived on every connection attempt so that
    the timestamp-embedded signature remains fresh.
    """

    on_message: Callable[[bytes], Awaitable[None]] | None = None
    on_device_message: Callable[[str, bytes], Awaitable[None]] | None = None

    def __init__(self, config: AliyunMQTTConfig) -> None:
        """Initialise the transport with the supplied Aliyun configuration."""
        self._config = config
        self._client: aiomqtt.Client | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._availability: TransportAvailability = TransportAvailability.DISCONNECTED
        self._subscribe_topics: list[str] = []
        self._publish_topic: str | None = None
        self._tls_context: ssl.SSLContext = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH, cadata=_ALIYUN_BROKER_CA_DATA
        )

    # ------------------------------------------------------------------
    # Topic management
    # ------------------------------------------------------------------

    def add_subscribe_topic(self, topic: str) -> None:
        """Register a topic to subscribe to on (re)connect.

        Args:
            topic: Full MQTT topic string to subscribe to.

        """
        if topic not in self._subscribe_topics:
            self._subscribe_topics.append(topic)

    def set_publish_topic(self, topic: str) -> None:
        """Set the single outbound topic used by :meth:`send`.

        Args:
            topic: Full MQTT topic string to publish commands to.

        """
        self._publish_topic = topic

    # ------------------------------------------------------------------
    # Transport ABC
    # ------------------------------------------------------------------

    @property
    def transport_type(self) -> TransportType:
        """Return TransportType.CLOUD_ALIYUN for this implementation."""
        return TransportType.CLOUD_ALIYUN

    @property
    def is_connected(self) -> bool:
        """True when the receive-loop task is running and the connection is established."""
        return (
            self._availability is TransportAvailability.CONNECTED and self._task is not None and not self._task.done()
        )

    @property
    def availability(self) -> TransportAvailability:
        """Current availability state of this transport."""
        return self._availability

    async def connect(self) -> None:
        """Start the Aliyun MQTT receive loop task.

        Does nothing if already connected.
        """
        if self.is_connected:
            _logger.debug("AliyunMQTTTransport.connect() called while already connected — ignoring")
            return

        self._stop_event.clear()
        self._availability = TransportAvailability.CONNECTING
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run())

    async def disconnect(self) -> None:
        """Signal the receive loop to stop and wait for it to finish."""
        self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._availability = TransportAvailability.DISCONNECTED
        self._client = None

    async def send(self, payload: bytes) -> None:
        """Publish *payload* to the configured publish topic.

        Args:
            payload: Raw bytes to publish.

        Raises:
            TransportError: If the transport is not connected or no publish topic
                has been configured.

        """
        if not self.is_connected or self._client is None:
            msg = "AliyunMQTTTransport is not connected; cannot send payload"
            raise TransportError(msg)
        if self._publish_topic is None:
            msg = "No publish topic configured; call set_publish_topic() first"
            raise TransportError(msg)
        await self._client.publish(self._publish_topic, payload)

    # ------------------------------------------------------------------
    # Credential helpers
    # ------------------------------------------------------------------

    def _build_credentials(self) -> tuple[str, str]:
        """Derive a fresh (client_id, password) pair stamped with the current time.

        Aliyun IoT requires a timestamp embedded in both the client ID suffix and
        the HMAC-SHA1 signed password so that stale credentials are rejected.

        Returns:
            A ``(client_id, password)`` tuple ready to pass to aiomqtt.Client.

        """
        timestamp = str(int(time.time()))
        client_id = f"{self._config.client_id_base}|securemode=2,signmethod=hmacsha1,ext=1,_ss=1,timestamp={timestamp}|"
        sign_content = (
            f"clientId{self._config.client_id_base}"
            f"deviceName{self._config.device_name}"
            f"productKey{self._config.product_key}"
            f"timestamp{timestamp}"
        )
        password = hmac.new(
            self._config.device_secret.encode("utf-8"),
            sign_content.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()
        return client_id, password

    def _default_subscribe_topics(self) -> list[str]:
        """Return the default set of Aliyun IoT subscribe topics for this device."""
        base = f"/sys/{self._config.product_key}/{self._config.device_name}"
        return [
            f"{base}/app/down/account/bind_reply",
            f"{base}/app/down/thing/event/property/post_reply",
            f"{base}/app/down/thing/wifi/status/notify",
            f"{base}/app/down/thing/wifi/connect/event/notify",
            f"{base}/app/down/_thing/event/notify",
            f"{base}/app/down/thing/events",
            f"{base}/app/down/thing/status",
            f"{base}/app/down/thing/properties",
            f"{base}/app/down/thing/model/down_raw",
        ]

    def _effective_subscribe_topics(self) -> list[str]:
        """Return subscribe topics, falling back to defaults if none are configured."""
        return self._subscribe_topics if self._subscribe_topics else self._default_subscribe_topics()

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Run the main Aliyun MQTT connection loop, reconnecting with exponential backoff."""
        backoff = _MQTT_RECONNECT_MIN_SEC

        while not self._stop_event.is_set():
            client_id, password = self._build_credentials()
            try:
                async with aiomqtt.Client(
                    hostname=self._config.host,
                    port=self._config.port,
                    username=self._config.username,
                    password=password,
                    identifier=client_id,
                    keepalive=self._config.keepalive,
                    tls_context=self._tls_context,
                    protocol=aiomqtt.ProtocolVersion.V311,
                    max_inflight_messages=_MQTT_MAX_INFLIGHT,
                    max_queued_incoming_messages=_MQTT_MAX_QUEUED,
                ) as client:
                    self._client = client
                    backoff = _MQTT_RECONNECT_MIN_SEC  # reset on successful connect
                    self._availability = TransportAvailability.CONNECTED

                    for topic in self._effective_subscribe_topics():
                        await client.subscribe(topic, qos=1)

                    # Send the Aliyun IoT bind message to register the app client
                    bind_topic = f"/sys/{self._config.product_key}/{self._config.device_name}/app/up/account/bind"
                    await client.publish(
                        bind_topic,
                        json.dumps(
                            {
                                "id": "msgid1",
                                "version": "1.0",
                                "request": {"clientId": self._config.username},
                                "params": {"iotToken": self._config.iot_token},
                            }
                        ),
                        qos=1,
                    )

                    async for message in client.messages:
                        if self._stop_event.is_set():
                            break
                        raw = bytes(message.payload)
                        result = self._unwrap_envelope(str(message.topic), raw)
                        if result is not None:
                            decoded, iot_id = result
                            if iot_id and self.on_device_message is not None:
                                await self.on_device_message(iot_id, decoded)
                            elif self.on_message is not None:
                                await self.on_message(decoded)

            except aiomqtt.MqttCodeError as exc:
                rc = exc.rc
                if rc in (4, 5):
                    _logger.error(
                        "Aliyun MQTT connection refused (rc=%s): %s — stopping reconnect",
                        rc,
                        exc,
                    )
                    self._stop_event.set()
                    self._client = None
                    self._availability = TransportAvailability.DISCONNECTED
                    raise AuthError(str(exc)) from exc
                _logger.warning("Aliyun MQTT error (rc=%s): %s — retry in %ds", rc, exc, backoff)
            except aiomqtt.MqttError as exc:
                _logger.warning("Aliyun MQTT disconnected: %s — retry in %ds", exc, backoff)
            except asyncio.CancelledError:
                break
            finally:
                self._client = None
                if self._availability is TransportAvailability.CONNECTED:
                    self._availability = TransportAvailability.DISCONNECTED

            if not self._stop_event.is_set():
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    break
                backoff = min(backoff * 2, _MQTT_RECONNECT_MAX_SEC)

    # ------------------------------------------------------------------
    # Envelope unwrapping
    # ------------------------------------------------------------------

    def _unwrap_envelope(self, topic: str, raw: bytes) -> tuple[bytes, str] | None:
        """Extract the base64-encoded protobuf payload and iot_id from an Aliyun IoT envelope.

        The Aliyun broker wraps device messages in a JSON envelope of the form::

            {
              "method": "thing.events",
              "params": {
                "iotId": "<device iot_id>",
                "identifier": "device_protobuf_msg_event",
                "value": {"content": "<base64-encoded protobuf>"},
                ...
              },
              ...
            }

        For Mammotion direct-MQTT events the path is::

            {
              "params": {"iotId": "<device iot_id>", "content": "<base64-encoded protobuf>"},
              ...
            }

        Both shapes are attempted.  If neither matches, the message is logged
        and *None* is returned so the caller can skip it.

        Args:
            topic: The MQTT topic the message arrived on (used for logging).
            raw: Raw bytes of the JSON envelope.

        Returns:
            ``(decoded_bytes, iot_id)`` tuple, or *None* if unwrapping fails.
            ``iot_id`` may be an empty string if the field is absent.

        """
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            _logger.debug("Non-JSON payload on topic %s, skipping", topic)
            return None

        iot_id: str = parsed.get("params", {}).get("iotId", "")

        # Aliyun thing.events shape: params.value.content
        try:
            content: str | None = parsed["params"]["value"]["content"]
            if content:
                return base64.b64decode(content), iot_id
        except (KeyError, TypeError):
            pass

        # Mammotion direct-MQTT event shape: params.content
        try:
            content = parsed["params"]["content"]
            if content:
                return base64.b64decode(content), iot_id
        except (KeyError, TypeError):
            pass

        _logger.debug("No base64 content field found in envelope on topic %s", topic)
        return None
