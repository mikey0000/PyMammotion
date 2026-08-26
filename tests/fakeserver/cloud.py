"""FakeMammotionCloud — one object owning the HTTP API and both MQTT brokers."""

from __future__ import annotations

import json
import time

from aiohttp import web

from .broker import FakeMQTTBroker, Session
from .http_api import build_app
from .scenario import Scenario


class FakeMammotionCloud:
    """The whole fake cloud: HTTP API + Mammotion broker + Aliyun broker.

    Usage::

        cloud = FakeMammotionCloud()
        await cloud.start()
        monkeypatch.setattr("pymammotion.http.http.MAMMOTION_DOMAIN", cloud.base_url)
        monkeypatch.setattr("pymammotion.http.http.MAMMOTION_API_DOMAIN", cloud.base_url)
        ...
        await cloud.stop()
    """

    def __init__(self, scenario: Scenario | None = None, http_port: int = 0) -> None:
        self.scenario = scenario or Scenario()
        self.mammotion_broker = FakeMQTTBroker()
        self.aliyun_broker = FakeMQTTBroker()
        self._http_port = http_port
        self._runner: web.AppRunner | None = None
        self.port: int = 0
        #: (iot_id, protobuf_bytes) for every successful mqtt_invoke.
        self.invocations: list[tuple[str, bytes]] = []
        #: Aliyun bind attempts observed (the raw JSON payloads).
        self.bind_requests: list[dict] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def mqtt_host(self) -> str:
        """Host string handed out by /v1/mqtt/auth/jwt — plaintext local broker."""
        return f"tcp://127.0.0.1:{self.mammotion_broker.port}"

    async def start(self) -> None:
        await self.mammotion_broker.start()
        await self.aliyun_broker.start()
        self.mammotion_broker.authenticate = self._mammotion_auth
        self.aliyun_broker.authenticate = self._aliyun_auth
        self.aliyun_broker.on_client_publish = self._on_aliyun_publish

        app = build_app(
            self.scenario,
            base_url_getter=lambda: self.base_url,
            mqtt_host_getter=lambda: self.mqtt_host,
            on_invoke=self._on_invoke,
        )
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self._http_port)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        await self.mammotion_broker.stop()
        await self.aliyun_broker.stop()

    # ------------------------------------------------------------------
    # Broker hooks
    # ------------------------------------------------------------------

    async def _mammotion_auth(self, _client_id: str, _username: str | None, _password: str | None) -> int:
        self.scenario.count("mammotion_mqtt_connects")
        return self.scenario.mammotion_connack_rc

    async def _aliyun_auth(self, _client_id: str, _username: str | None, _password: str | None) -> int:
        self.scenario.count("aliyun_mqtt_connects")
        return self.scenario.aliyun_connack_rc

    async def _on_aliyun_publish(self, _session: Session, topic: str, payload: bytes) -> None:
        if not topic.endswith("/app/up/account/bind"):
            return
        self.scenario.count("aliyun_binds")
        try:
            self.bind_requests.append(json.loads(payload))
        except Exception:  # noqa: BLE001
            self.bind_requests.append({"raw": payload.decode(errors="replace")})
        # topic: /sys/{pk}/{dn}/app/up/account/bind
        parts = topic.split("/")
        pk, dn = parts[2], parts[3]
        code = self.scenario.bind_reply_code
        reply = {"code": code, "id": "msgid1", "message": "success" if code == 200 else "check iotToken failed"}
        self.aliyun_broker.publish(
            f"/sys/{pk}/{dn}/app/down/account/bind_reply", json.dumps(reply).encode()
        )

    async def _on_invoke(self, iot_id: str, payload: bytes) -> None:
        self.invocations.append((iot_id, payload))

    # ------------------------------------------------------------------
    # Injection helpers (fake mower behaviour)
    # ------------------------------------------------------------------

    def publish_device_status(self, *, online: bool) -> int:
        """Publish the Mammotion flat thing/status message for the fake mower."""
        d = self.scenario.device
        payload = {
            "action": "online" if online else "offline",
            "productKey": d.product_key,
            "deviceName": d.device_name,
            "iotId": d.iot_id,
            "gmtCreate": int(time.time() * 1000),
        }
        return self.mammotion_broker.publish(
            f"/sys/{d.product_key}/{d.device_name}/app/down/thing/status",
            json.dumps(payload).encode(),
        )

    def publish_device_response(self, luba_msg_bytes: bytes) -> int:
        """Deliver a protobuf LubaMsg from the fake mower over the Mammotion broker."""
        import base64 as _b64

        d = self.scenario.device
        envelope = {"params": {"content": _b64.b64encode(luba_msg_bytes).decode()}}
        return self.mammotion_broker.publish(
            f"/sys/{d.product_key}/{d.device_name}/thing/event/device_protobuf_msg_event/post",
            json.dumps(envelope).encode(),
        )

    def aliyun_publish_device_response(self, luba_msg_bytes: bytes, *, pk: str, dn: str) -> int:
        """Deliver a protobuf from the fake mower over the Aliyun broker (down_raw envelope)."""
        import base64 as _b64

        envelope = {
            "params": {
                "iotId": self.scenario.device.iot_id,
                "value": {"content": _b64.b64encode(luba_msg_bytes).decode()},
            }
        }
        return self.aliyun_broker.publish(
            f"/sys/{pk}/{dn}/app/down/thing/model/down_raw", json.dumps(envelope).encode()
        )
