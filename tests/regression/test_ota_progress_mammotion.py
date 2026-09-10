"""Firmware progress over the Mammotion broker, which reported 0% for a whole install.

How the app does it (``maiot_module``, 2.3.8.201): ``MaIoTApp`` subscribes exactly
three topics per device — ``thing/event/+/post``, ``proto/.../thing/event/+/post`` and
``app/down/thing/status``.  ``MQTTService.messageArrived`` then reduces the topic to a
method with ``TopicUtils.getMethod`` (its last two segments), and on ``/property/post``
pulls ``params.otaProgress`` straight out of the envelope.

So OTA progress is an *event*: it arrives as ``.../thing/event/property/post`` under the
first wildcard.  There is no properties topic on this broker, and the payload carries no
device identity — the app injects ``deviceName`` from the topic, exactly as
``MQTTTransport._dispatch_mammotion_properties`` derives its ``iot_id`` from the topic.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.mqtt.properties import MammotionPropertiesMessage
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.transport.mqtt import MQTTTransport, MQTTTransportConfig

PRODUCT_KEY = "a2MoBDliJbI"
DEVICE_NAME = "Luba-TEST0001"
IOT_ID = "FAKEIOTID0000000000000000"
OTA_TOPIC = f"/sys/{PRODUCT_KEY}/{DEVICE_NAME}/thing/event/property/post"


def _transport() -> MQTTTransport:
    config = MQTTTransportConfig(host="mqtt.example.com", client_id="c1", username="u", password="p")
    return MQTTTransport(config=config, mammotion_http=AsyncMock(), token_manager=AsyncMock())


def test_the_device_topics_are_the_three_the_app_subscribes() -> None:
    """No properties topic: a property post is an event under the first wildcard."""
    topics = MQTTTransport.device_topics(PRODUCT_KEY, DEVICE_NAME)

    assert topics == (
        f"/sys/{PRODUCT_KEY}/{DEVICE_NAME}/thing/event/+/post",
        f"/sys/proto/{PRODUCT_KEY}/{DEVICE_NAME}/thing/event/+/post",
        f"/sys/{PRODUCT_KEY}/{DEVICE_NAME}/app/down/thing/status",
    )
    assert not [topic for topic in topics if topic.endswith("properties")], (
        "this broker has no properties topic — subscribing one is a wrong turn"
    )


@pytest.mark.regression
async def test_an_ota_property_post_reaches_the_properties_callback() -> None:
    """The wildcard subscription must actually route ``property/post`` to the parser.

    ``getMethod`` collapses ``.../thing/event/property/post`` to ``/property/post``, so
    the dispatcher has to match on the tail rather than treat it as a generic event.
    """
    transport = _transport()
    transport.register_device(PRODUCT_KEY, DEVICE_NAME, IOT_ID)
    seen: list[tuple[str, MammotionPropertiesMessage]] = []

    async def on_properties(iot_id: str, message: MammotionPropertiesMessage) -> None:
        seen.append((iot_id, message))

    transport.on_device_mammotion_properties = on_properties
    payload = {"params": {"otaProgress": {"otaId": "ota-1", "progress": 42, "result": 2}}}

    await transport._dispatch(OTA_TOPIC, json.dumps(payload).encode())

    assert len(seen) == 1, "the OTA property post never reached the callback"
    iot_id, message = seen[0]
    assert iot_id == IOT_ID, "the iot_id must come from the topic; the payload has none"
    assert message.params.ota_progress is not None
    assert message.params.ota_progress.progress == 42


@pytest.mark.regression
@pytest.mark.parametrize(
    "envelope",
    [
        pytest.param({"id": "1", "version": "1.0", "sys": {}}, id="full envelope"),
        pytest.param({"id": "1", "version": "1.0"}, id="no sys — @Nullable in the app's model"),
        pytest.param({"id": "1"}, id="no version"),
        pytest.param({}, id="params only"),
    ],
)
def test_a_lean_envelope_still_parses(envelope: dict) -> None:
    """``id``/``version``/``sys`` were required here but optional in the app.

    ``TopicProperty`` declares ``sys`` and ``params`` ``@Nullable`` and reads the rest
    through null-tolerant getters.  Requiring them raised ``MissingField`` inside
    ``_dispatch_mammotion_properties``'s ``except Exception``, so the post was dropped
    at DEBUG and progress stayed at 0 for the whole install.
    """
    payload = {**envelope, "params": {"otaProgress": {"otaId": "ota-1", "progress": 42, "result": 2}}}

    message = MammotionPropertiesMessage.from_json(json.dumps(payload).encode())

    assert message.params.ota_progress is not None
    assert message.params.ota_progress.progress == 42


async def test_the_progress_lands_on_the_device_state() -> None:
    """End of the chain: what a progress display actually reads."""
    payload = {"params": {"otaProgress": {"otaId": "ota-1", "progress": 42, "result": 2}}}
    message = MammotionPropertiesMessage.from_json(json.dumps(payload).encode())

    device = MowerStateReducer().apply_mammotion_properties(MowingDevice(name=DEVICE_NAME), message)

    assert device.update_check.progress == 42
    assert device.update_check.isupgrading is True
