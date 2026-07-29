"""Shared MQTT envelope unwrapping.

Both cloud transports receive the device's protobuf wrapped in a JSON envelope,
and both carried their own byte-for-byte equivalent unwrapper.  The logic is
genuinely common — parse JSON, find the base64 ``content`` under one of two
shapes, decode it — so it lives here once.

A module-level function rather than a shared base class: the two transports
differ substantially in credential handling and reconnect policy (see A3), and
this is the part that is actually the same.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging

_logger = logging.getLogger(__name__)


def unwrap_envelope(topic: str, raw: bytes) -> tuple[bytes, str] | None:
    """Extract the protobuf payload and ``iotId`` from a broker envelope.

    Two shapes are accepted, in this order::

        # Aliyun thing.events
        {"params": {"iotId": "...", "value": {"content": "<base64>"}}}

        # Mammotion direct-MQTT event
        {"params": {"iotId": "...", "content": "<base64>"}}

    Args:
        topic: Topic the message arrived on — logging only.
        raw:   Raw bytes of the JSON envelope.

    Returns:
        ``(payload, iot_id)``, where *iot_id* is ``""`` when the field is absent
        (the Mammotion transport routes by topic and ignores it).  ``None`` when
        the envelope can't be unwrapped.

    Never raises.  That matters more than it looks: callers invoke this from the
    receive loop, whose catch-all responds to an unexpected exception by tearing
    the connection down and reconnecting with backoff.  A single corrupt message
    must not cost the connection — which it previously did, because
    ``base64.b64decode`` raises ``binascii.Error`` (a ``ValueError``) and the
    guard only caught ``(KeyError, TypeError)``.

    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _logger.debug("Non-JSON payload on topic %s, skipping", topic)
        return None

    if not isinstance(parsed, dict):
        _logger.debug("Envelope on topic %s is not a JSON object, skipping", topic)
        return None

    params = parsed.get("params")
    if not isinstance(params, dict):
        _logger.debug("No params object in envelope on topic %s", topic)
        return None

    iot_id = params.get("iotId") or ""
    if not isinstance(iot_id, str):
        iot_id = ""

    nested = params.get("value")
    candidates = [
        nested.get("content") if isinstance(nested, dict) else None,  # Aliyun thing.events
        params.get("content"),  # Mammotion direct-MQTT
    ]
    for content in candidates:
        if not content or not isinstance(content, str):
            continue
        try:
            return base64.b64decode(content), iot_id
        except (binascii.Error, ValueError):
            # Try the other shape rather than giving up — a corrupt payload at one
            # path must not mask a good one at the other.
            _logger.debug("Undecodable base64 content in envelope on topic %s", topic)

    _logger.debug("No usable base64 content field in envelope on topic %s", topic)
    return None
