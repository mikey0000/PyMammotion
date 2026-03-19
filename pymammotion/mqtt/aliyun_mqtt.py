"""Aliyun IoT MQTT client for PyMammotion."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import hashlib
import hmac
import json
from logging import getLogger
import ssl
import time
from typing import TYPE_CHECKING

import aiomqtt

if TYPE_CHECKING:
    from pymammotion.aliyun.cloud_gateway import CloudIOTGateway

logger = getLogger(__name__)

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


class AliyunMQTT:
    """Async MQTT client for the Aliyun IoT platform.

    Handles Aliyun-specific credential format and topic structure using aiomqtt.
    Runs a persistent asyncio task that reconnects with exponential backoff on
    any connection error.
    """

    def __init__(
        self,
        region_id: str,
        product_key: str,
        device_name: str,
        device_secret: str,
        iot_token: str,
        cloud_client: CloudIOTGateway,
        client_id: str | None = None,
    ) -> None:
        self._cloud_client = cloud_client
        self._product_key = product_key
        self._device_name = device_name

        # Base client_id: "{product_key}&{device_name}" per Aliyun convention
        self._client_id_base = f"{product_key}&{device_name}" if client_id is None else client_id
        self._device_secret = device_secret
        self._mqtt_username = f"{device_name}&{product_key}"
        self._mqtt_host = f"{product_key}.iot-as-mqtt.{region_id}.aliyuncs.com"

        self.is_connected = False
        self.is_ready = False
        self.on_connected: Callable[[], Awaitable[None]] | None = None
        self.on_ready: Callable[[], Awaitable[None]] | None = None
        self.on_error: Callable[[str], Awaitable[None]] | None = None
        self.on_disconnected: Callable[[], Awaitable[None]] | None = None
        self.on_message: Callable[[str, bytes, str], Awaitable[None]] | None = None

        self._tls_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cadata=_ALIYUN_BROKER_CA_DATA)
        self._task: asyncio.Task[None] | None = None
        self._disconnect_requested = False
        self.loop = asyncio.get_running_loop()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def connect_async(self) -> None:
        """Schedule the connection loop on the event loop.

        Safe to call from any thread (including a thread-pool executor).
        Ignored if already connected or a connection task is already running.
        """
        if self.is_connected:
            logger.debug("connect_async called while already connected — ignoring")
            return
        self._disconnect_requested = False
        self.loop.call_soon_threadsafe(self._start_task)

    def disconnect(self) -> None:
        """Stop the connection loop and disconnect."""
        self._disconnect_requested = True
        if self._task is not None:
            self.loop.call_soon_threadsafe(self._task.cancel)

    @property
    def iot_token(self) -> str:
        if authcode_response := self._cloud_client.session_by_authcode_response.data:
            return authcode_response.iotToken
        return ""

    async def send_cloud_command(self, iot_id: str, command: bytes) -> str:
        """Send a command via the Aliyun cloud gateway."""
        return await self._cloud_client.send_cloud_command(iot_id, command)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = self.loop.create_task(self._run())

    def _build_credentials(self) -> tuple[str, str]:
        """Return (client_id, password) stamped with the current timestamp."""
        timestamp = str(int(time.time()))
        client_id = f"{self._client_id_base}|securemode=2,signmethod=hmacsha1,ext=1,_ss=1,timestamp={timestamp}|"
        sign_content = (
            f"clientId{self._client_id_base}"
            f"deviceName{self._device_name}"
            f"productKey{self._product_key}"
            f"timestamp{timestamp}"
        )
        password = hmac.new(self._device_secret.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha1).hexdigest()
        return client_id, password

    def _subscription_topics(self) -> list[str]:
        base = f"/sys/{self._product_key}/{self._device_name}"
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

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Main connection loop — reconnects with exponential backoff."""
        backoff = _MQTT_RECONNECT_MIN_SEC
        while not self._disconnect_requested:
            client_id, password = self._build_credentials()
            try:
                async with aiomqtt.Client(
                    hostname=self._mqtt_host,
                    port=_MQTT_PORT,
                    username=self._mqtt_username,
                    password=password,
                    identifier=client_id,
                    keepalive=_MQTT_KEEPALIVE,
                    tls_context=self._tls_context,
                    protocol=aiomqtt.ProtocolVersion.V311,
                    max_inflight_messages=_MQTT_MAX_INFLIGHT,
                    max_queued_incoming_messages=_MQTT_MAX_QUEUED,
                ) as client:
                    backoff = _MQTT_RECONNECT_MIN_SEC  # reset on successful connect

                    for topic in self._subscription_topics():
                        await client.subscribe(topic, qos=1)

                    await client.publish(
                        f"/sys/{self._product_key}/{self._device_name}/app/up/account/bind",
                        json.dumps(
                            {
                                "id": "msgid1",
                                "version": "1.0",
                                "request": {"clientId": self._mqtt_username},
                                "params": {"iotToken": self.iot_token},
                            }
                        ),
                        qos=1,
                    )

                    self.is_connected = True
                    if self.on_connected is not None:
                        await self.on_connected()

                    self.is_ready = True
                    if self.on_ready is not None:
                        await self.on_ready()

                    async for message in client.messages:
                        if self._disconnect_requested:
                            break  # type: ignore[unreachable]
                        await self._dispatch(str(message.topic), message.payload)

            except aiomqtt.MqttCodeError as exc:
                rc = exc.rc
                if rc in (4, 5):
                    logger.error(
                        "MQTT connection refused (rc=%s): %s — stopping reconnect (check credentials/token)",
                        rc,
                        exc,
                    )
                    self._disconnect_requested = True
                    if self.on_error is not None:
                        await self.on_error(str(exc))
                else:
                    logger.warning("MQTT error (rc=%s): %s — retry in %ds", rc, exc, backoff)
            except aiomqtt.MqttError as exc:
                logger.warning("MQTT disconnected: %s — retry in %ds", exc, backoff)
            except asyncio.CancelledError:
                break
            finally:
                if self.is_connected or self.is_ready:
                    self.is_connected = False
                    self.is_ready = False
                    if self.on_disconnected is not None:
                        await self.on_disconnected()

            if not self._disconnect_requested:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MQTT_RECONNECT_MAX_SEC)

    async def _dispatch(self, topic: str, payload: bytes | bytearray | str | int | float | None) -> None:
        """Parse and route an incoming MQTT message."""
        logger.debug("Message on topic %s", topic)
        if isinstance(payload, (bytes, bytearray)):
            raw = bytes(payload)
        elif isinstance(payload, str):
            raw = payload.encode("utf-8")
        else:
            logger.warning("Unexpected payload type %s on topic %s, ignoring", type(payload), topic)
            return

        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Non-JSON payload on topic %s, ignoring", topic)
            return

        iot_id: str = parsed.get("params", {}).get("iotId", "")
        if iot_id and self.on_message is not None:
            await self.on_message(topic, raw, iot_id)
