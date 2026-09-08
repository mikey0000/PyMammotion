"""Routes inbound cloud messages to the DeviceHandle they belong to.

A cloud transport is shared by every device on an account, so each frame arrives
labelled with an ``iotId`` rather than pre-addressed to a handle.  This owns that
one lookup — ``(account_id, iot_id) -> DeviceKey`` — and the six per-message-kind
callbacks the transports fire, so ``MammotionClient`` doesn't carry a routing
table alongside everything else it does.

The router resolves through :class:`~pymammotion.device.handle.DeviceRegistry`
rather than holding handles itself: a handle can be re-keyed between accounts
(BLE-only sentinel <-> cloud account) while the registry stays authoritative.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pymammotion.data.mqtt.status import StatusType

if TYPE_CHECKING:
    from pymammotion.data.mqtt.event import ThingEventMessage
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage, ThingPropertiesMessage
    from pymammotion.data.mqtt.status import ThingStatusMessage
    from pymammotion.device.handle import DeviceHandle, DeviceKey, DeviceRegistry

_logger = logging.getLogger(__name__)


class InboundRouter:
    """Maps ``(account_id, iot_id)`` to a handle and forwards messages to it."""

    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry
        self._iot_id_to_device_key: dict[tuple[str, str], DeviceKey] = {}

    def bind(self, account_id: str, iot_id: str, device_key: DeviceKey) -> None:
        """Route future frames for *iot_id* on *account_id* to *device_key*."""
        self._iot_id_to_device_key[(account_id, iot_id)] = device_key

    def unbind(self, account_id: str, iot_id: str) -> None:
        """Stop routing frames for *iot_id* on *account_id*.  Safe if not bound."""
        self._iot_id_to_device_key.pop((account_id, iot_id), None)

    def handle_for(self, account_id: str, iot_id: str, caller: str) -> DeviceHandle | None:
        """Look up a handle by ``(account_id, iot_id)``, logging a miss and returning None."""
        key = self._iot_id_to_device_key.get((account_id, iot_id))
        if key is None:
            _logger.debug("%s: unknown iot_id=%s for account %s, dropping", caller, iot_id, account_id)
            return None
        return self._registry.get(*key)

    async def route_message(self, account_id: str, iot_id: str, payload: bytes) -> None:
        """Route an incoming protobuf frame to the correct DeviceHandle."""
        if (handle := self.handle_for(account_id, iot_id, "route_message")) is None:
            return
        await handle.on_raw_message(payload)

    async def route_status(self, account_id: str, iot_id: str, msg: ThingStatusMessage) -> None:
        """Update a handle's MQTT availability and status_properties from a thing/status message."""
        if (handle := self.handle_for(account_id, iot_id, "route_status")) is None:
            return
        online = msg.params.status.value is StatusType.CONNECTED
        await handle.on_status_message(msg)
        _logger.info("Device '%s' is now %s (thing/status)", handle.device_name, "online" if online else "offline")

    async def route_notification(
        self, account_id: str, iot_id: str, identifier: str, value: dict[str, Any] | None = None
    ) -> None:
        """Forward a Mammotion-MQTT thing/event notification to the correct DeviceHandle."""
        if (handle := self.handle_for(account_id, iot_id, "route_notification")) is None:
            return
        await handle.on_device_notification(identifier, value)

    async def route_event(self, account_id: str, iot_id: str, event: ThingEventMessage) -> None:
        """Forward a non-protobuf thing.events message to the correct DeviceHandle."""
        if (handle := self.handle_for(account_id, iot_id, "route_event")) is None:
            return
        await handle.on_device_event(event)

    async def route_properties(self, account_id: str, iot_id: str, properties: ThingPropertiesMessage) -> None:
        """Forward a thing.properties message to the correct DeviceHandle."""
        if (handle := self.handle_for(account_id, iot_id, "route_properties")) is None:
            return
        await handle.on_device_properties(properties)

    async def route_mammotion_properties(
        self, account_id: str, iot_id: str, properties: MammotionPropertiesMessage
    ) -> None:
        """Forward a Mammotion MQTT flat property/post message to the correct DeviceHandle."""
        if (handle := self.handle_for(account_id, iot_id, "route_mammotion_properties")) is None:
            return
        await handle.on_mammotion_properties(properties)
