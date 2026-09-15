"""A minimal MQTT 3.1.1 broker for integration tests.

Speaks just enough of the protocol for aiomqtt/paho clients: CONNECT/CONNACK
(with a pluggable auth hook so tests can reject with rc 4/5), SUBSCRIBE/SUBACK,
UNSUBSCRIBE/UNSUBACK, PUBLISH (QoS 0 and 1 inbound; QoS 0 delivery outbound),
PINGREQ/PINGRESP, and DISCONNECT.  No retained messages, no persistence, no
QoS 2 — none of which the pymammotion transports use.

The broker exposes:
- ``publish(topic, payload)``     — inject a message to matching subscribers.
- ``on_client_publish``           — async hook fired for every inbound PUBLISH
                                    (how the fake cloud reacts to e.g. the
                                    Aliyun bind message).
- ``authenticate``                — async hook (client_id, username, password)
                                    → CONNACK return code (0 accepts).
- ``sessions``                    — live sessions, for asserting connect counts.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
import logging
import ssl
from typing import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)

# Packet types (MQTT 3.1.1, table 2.1)
CONNECT = 0x10
CONNACK = 0x20
PUBLISH = 0x30
PUBACK = 0x40
SUBSCRIBE = 0x80
SUBACK = 0x90
UNSUBSCRIBE = 0xA0
UNSUBACK = 0xB0
PINGREQ = 0xC0
PINGRESP = 0xD0
DISCONNECT = 0xE0

CONNACK_ACCEPTED = 0
CONNACK_BAD_CREDENTIALS = 4
CONNACK_NOT_AUTHORIZED = 5


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value % 128
        value //= 128
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_string(buf: bytes, offset: int) -> tuple[str, int]:
    length = int.from_bytes(buf[offset : offset + 2], "big")
    end = offset + 2 + length
    return buf[offset + 2 : end].decode("utf-8", errors="replace"), end


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT topic-filter matching with ``+`` and ``#`` wildcards."""
    p_parts = pattern.split("/")
    t_parts = topic.split("/")
    for i, p in enumerate(p_parts):
        if p == "#":
            return True
        if i >= len(t_parts):
            return False
        if p != "+" and p != t_parts[i]:
            return False
    return len(p_parts) == len(t_parts)


@dataclass
class Session:
    """One connected client."""

    client_id: str
    username: str | None
    writer: asyncio.StreamWriter
    subscriptions: list[str] = field(default_factory=list)
    connected: bool = True

    def send_packet(self, first_byte: int, body: bytes) -> None:
        if self.connected:
            self.writer.write(bytes([first_byte]) + _encode_varint(len(body)) + body)


class FakeMQTTBroker:
    """Async MQTT 3.1.1 broker bound to 127.0.0.1 on an ephemeral port."""

    def __init__(self, tls_context: ssl.SSLContext | None = None) -> None:
        self._server: asyncio.Server | None = None
        self._tls_context = tls_context
        self.port: int = 0
        self.sessions: list[Session] = []
        self.connect_attempts: list[tuple[str, str | None, str | None]] = []
        #: (client_id, username, password) -> CONNACK code.  Default accepts all.
        self.authenticate: Callable[[str, str | None, str | None], Awaitable[int]] | None = None
        #: Fired for every inbound PUBLISH: (session, topic, payload).
        self.on_client_publish: Callable[[Session, str, bytes], Awaitable[None]] | None = None
        self._tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0, ssl=self._tls_context)
        self.port = self._server.sockets[0].getsockname()[1]
        _LOGGER.info("fake MQTT broker listening on 127.0.0.1:%d", self.port)

    async def stop(self) -> None:
        # Stop accepting first, so no new handler can appear after the cancellations below.
        if self._server is not None:
            self._server.close()
        for session in list(self.sessions):
            session.connected = False
            with contextlib.suppress(Exception):
                session.writer.close()
        # Since 3.12.1 Server.wait_closed() waits for the client handlers to finish, so
        # they have to be cancelled before it is awaited rather than after it: a handler
        # parked on a read whose peer never closed would otherwise wait on the very
        # cancellation that comes next.  Only sessions that finished CONNECT are in
        # self.sessions, so closing writers alone does not cover every handler.
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._server is not None:
            await self._server.wait_closed()

    # Public injection API

    def publish(self, topic: str, payload: bytes, *, to_client_id: str | None = None) -> int:
        """Deliver *payload* to every session subscribed to *topic*.

        Returns the number of sessions it was delivered to.  Delivery is QoS 0,
        which is a valid downgrade for QoS 1 subscriptions.
        """
        delivered = 0
        topic_bytes = topic.encode()
        body = len(topic_bytes).to_bytes(2, "big") + topic_bytes + payload
        for session in self.sessions:
            if to_client_id is not None and session.client_id != to_client_id:
                continue
            if any(topic_matches(pattern, topic) for pattern in session.subscriptions):
                session.send_packet(PUBLISH, body)
                delivered += 1
        return delivered

    def drop_all_clients(self) -> None:
        """Hard-close every live connection (simulates a broker-side kick)."""
        for session in list(self.sessions):
            session.connected = False
            with contextlib.suppress(Exception):
                session.writer.close()

    # Protocol handling

    async def _read_packet(self, reader: asyncio.StreamReader) -> tuple[int, bytes]:
        first = await reader.readexactly(1)
        remaining = 0
        multiplier = 1
        for _ in range(4):
            byte = (await reader.readexactly(1))[0]
            remaining += (byte & 0x7F) * multiplier
            if not byte & 0x80:
                break
            multiplier *= 128
        body = await reader.readexactly(remaining) if remaining else b""
        return first[0], body

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        session: Session | None = None
        try:
            first, body = await asyncio.wait_for(self._read_packet(reader), timeout=10)
            if first & 0xF0 != CONNECT:
                return
            session = await self._handle_connect(body, writer)
            if session is None:
                return
            while True:
                first, body = await self._read_packet(reader)
                ptype = first & 0xF0
                if ptype == SUBSCRIBE:
                    self._handle_subscribe(session, body)
                elif ptype == UNSUBSCRIBE:
                    self._handle_unsubscribe(session, body)
                elif ptype == PUBLISH:
                    await self._handle_publish(session, first, body)
                elif ptype == PINGREQ:
                    session.send_packet(PINGRESP, b"")
                elif ptype == DISCONNECT:
                    return
        except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.TimeoutError, ssl.SSLError):
            pass
        except Exception:  # noqa: BLE001 — a broken client must not kill the broker
            _LOGGER.debug("fake broker: client handler error", exc_info=True)
        finally:
            if session is not None:
                session.connected = False
                if session in self.sessions:
                    self.sessions.remove(session)
            with contextlib.suppress(Exception):
                writer.close()
            if task is not None:
                self._tasks.discard(task)

    async def _handle_connect(self, body: bytes, writer: asyncio.StreamWriter) -> Session | None:
        _, offset = _read_string(body, 0)  # protocol name ("MQTT")
        offset += 1  # protocol level
        flags = body[offset]
        offset += 1 + 2  # flags + keepalive
        client_id, offset = _read_string(body, offset)
        if flags & 0x04:  # will flag: skip will topic + message
            _, offset = _read_string(body, offset)
            will_len = int.from_bytes(body[offset : offset + 2], "big")
            offset += 2 + will_len
        username: str | None = None
        password: str | None = None
        if flags & 0x80:
            username, offset = _read_string(body, offset)
        if flags & 0x40:
            password, offset = _read_string(body, offset)

        self.connect_attempts.append((client_id, username, password))
        rc = CONNACK_ACCEPTED
        if self.authenticate is not None:
            rc = await self.authenticate(client_id, username, password)
        writer.write(bytes([CONNACK, 2, 0, rc]))
        await writer.drain()
        if rc != CONNACK_ACCEPTED:
            writer.close()
            return None
        session = Session(client_id=client_id, username=username, writer=writer)
        self.sessions.append(session)
        return session

    def _handle_subscribe(self, session: Session, body: bytes) -> None:
        packet_id = body[0:2]
        offset = 2
        granted = bytearray()
        while offset < len(body):
            topic_filter, offset = _read_string(body, offset)
            qos = body[offset]
            offset += 1
            session.subscriptions.append(topic_filter)
            granted.append(min(qos, 1))
        session.send_packet(SUBACK, packet_id + bytes(granted))

    def _handle_unsubscribe(self, session: Session, body: bytes) -> None:
        packet_id = body[0:2]
        offset = 2
        while offset < len(body):
            topic_filter, offset = _read_string(body, offset)
            if topic_filter in session.subscriptions:
                session.subscriptions.remove(topic_filter)
        session.send_packet(UNSUBACK, packet_id)

    async def _handle_publish(self, session: Session, first: int, body: bytes) -> None:
        qos = (first & 0x06) >> 1
        topic, offset = _read_string(body, 0)
        if qos:
            packet_id = body[offset : offset + 2]
            offset += 2
            session.send_packet(PUBACK, packet_id)
        payload = body[offset:]
        if self.on_client_publish is not None:
            await self.on_client_publish(session, topic, payload)
        # Route to other subscribers too (a real broker would); the fake cloud
        # hook above is the primary consumer.
        for other in self.sessions:
            if other is session:
                continue
            if any(topic_matches(pattern, topic) for pattern in other.subscriptions):
                topic_bytes = topic.encode()
                other.send_packet(PUBLISH, len(topic_bytes).to_bytes(2, "big") + topic_bytes + payload)
