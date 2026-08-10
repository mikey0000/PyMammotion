"""Tests for the shared MQTT envelope unwrap.

Both transports receive the device's protobuf wrapped in a JSON envelope, and
both had their own byte-for-byte equivalent unwrapper — the duplication A3 flags.
The logic is genuinely common (parse JSON, find base64 content under one of two
shapes, decode); only whether the caller also wants the ``iotId`` differed.
"""

from __future__ import annotations

import base64
import json

from pymammotion.transport.envelope import unwrap_envelope


def _aliyun_shape(payload: bytes, iot_id: str = "iot-1") -> bytes:
    """``thing.events`` shape — content nested under params.value."""
    return json.dumps(
        {
            "method": "thing.events",
            "params": {
                "iotId": iot_id,
                "identifier": "device_protobuf_msg_event",
                "value": {"content": base64.b64encode(payload).decode()},
            },
        }
    ).encode()


def _direct_shape(payload: bytes, iot_id: str = "iot-2") -> bytes:
    """Mammotion direct-MQTT shape — content directly under params."""
    return json.dumps(
        {"params": {"iotId": iot_id, "content": base64.b64encode(payload).decode()}}
    ).encode()


# ---------------------------------------------------------------------------
# The two envelope shapes
# ---------------------------------------------------------------------------


def test_unwraps_the_aliyun_nested_shape() -> None:
    result = unwrap_envelope("t", _aliyun_shape(b"\x08\x01payload"))
    assert result == (b"\x08\x01payload", "iot-1")


def test_unwraps_the_direct_shape() -> None:
    result = unwrap_envelope("t", _direct_shape(b"\x08\x02payload"))
    assert result == (b"\x08\x02payload", "iot-2")


def test_nested_shape_wins_when_both_are_present() -> None:
    """params.value.content is checked first — preserves the prior ordering."""
    raw = json.dumps(
        {
            "params": {
                "iotId": "x",
                "content": base64.b64encode(b"outer").decode(),
                "value": {"content": base64.b64encode(b"inner").decode()},
            }
        }
    ).encode()
    assert unwrap_envelope("t", raw) == (b"inner", "x")


def test_missing_iot_id_yields_an_empty_string() -> None:
    """The Mammotion transport ignores iot_id; absence must not fail the unwrap."""
    raw = json.dumps({"params": {"content": base64.b64encode(b"p").decode()}}).encode()
    assert unwrap_envelope("t", raw) == (b"p", "")


# ---------------------------------------------------------------------------
# Rejections — every one must return None, never raise
# ---------------------------------------------------------------------------


def test_non_json_payload_returns_none() -> None:
    assert unwrap_envelope("t", b"not json at all") is None


def test_missing_content_returns_none() -> None:
    assert unwrap_envelope("t", json.dumps({"params": {"iotId": "x"}}).encode()) is None


def test_empty_content_returns_none() -> None:
    assert unwrap_envelope("t", json.dumps({"params": {"content": ""}}).encode()) is None


def test_params_of_the_wrong_type_returns_none() -> None:
    assert unwrap_envelope("t", json.dumps({"params": "not a dict"}).encode()) is None


def test_json_that_is_not_an_object_returns_none() -> None:
    assert unwrap_envelope("t", b"[1, 2, 3]") is None


def test_malformed_base64_returns_none_rather_than_raising() -> None:
    """Regression: this used to escape and take the MQTT connection down with it.

    ``base64.b64decode`` raises ``binascii.Error``, a ``ValueError`` subclass, which
    the old ``except (KeyError, TypeError)`` did not catch.  It propagated out of the
    unwrap, through the dispatch, into ``_run``'s catch-all — which logs and
    *reconnects*.  One corrupt message therefore dropped the connection.
    """
    # "notbase64" after the lenient decoder strips "!" — 9 chars, invalid padding.
    raw = json.dumps({"params": {"iotId": "x", "content": "!!!not base64!!!"}}).encode()
    assert unwrap_envelope("t", raw) is None


def test_malformed_base64_in_the_nested_shape_also_returns_none() -> None:
    raw = json.dumps({"params": {"iotId": "x", "value": {"content": "a"}}}).encode()
    assert unwrap_envelope("t", raw) is None


def test_base64_decoding_is_lenient_about_stray_characters() -> None:
    """Documents existing behaviour rather than asserting a preference.

    ``base64.b64decode`` defaults to ``validate=False``, which *discards* characters
    outside the alphabet instead of rejecting them — so "!!!nope!!!" decodes as
    "nope".  Garbage that survives this becomes garbage protobuf and is rejected
    downstream with its own logging.  Switching to ``validate=True`` would be a
    behaviour change beyond deduplicating the two copies, so it is left alone.
    """
    raw = json.dumps({"params": {"iotId": "x", "content": "!!!nope!!!"}}).encode()
    result = unwrap_envelope("t", raw)
    assert result is not None
    assert result[1] == "x"


def test_falls_through_to_the_direct_shape_when_nested_content_is_corrupt() -> None:
    """A bad nested payload must not mask a good one at the other path."""
    raw = json.dumps(
        {
            "params": {
                "iotId": "x",
                "value": {"content": "a"},
                "content": base64.b64encode(b"good").decode(),
            }
        }
    ).encode()
    assert unwrap_envelope("t", raw) == (b"good", "x")
