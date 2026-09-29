"""The remote-drive control-token model and the app's grant classification.

``FpvControl`` mirrors the app's Kotlin data class of the same name (every field nullable);
``fpv_control_outcome`` ports ``ControlTokenRepository.handleTokenResponse`` (2.3.20.30):
envelope ``code != 0`` or no data is unavailable, ``deviceResult`` 0 with a non-blank token is
a grant, 9 is "occupied by ``preemptUser``", anything else is unavailable.
"""

from __future__ import annotations

import pytest

from pymammotion.http.model.fpv_control import FpvControl, FpvControlOutcome, fpv_control_outcome
from pymammotion.http.model.http import Response
from pymammotion.http.model.response_factory import response_factory


def _parse(body: dict) -> Response[FpvControl]:
    return response_factory(Response[FpvControl], body)


def test_every_field_the_app_reads_maps_from_its_camelcase_key() -> None:
    wire = {
        "deviceResult": 0,
        "token": "ctl",
        "issuedTimestamp": 1_700_000_000_000,
        "expireTimestamp": 1_700_000_600_000,
        "expireIn": 600,
        "timeoutExit": 15,
        "preemptUser": "someone",
        "latencyThreshold": 1500,
        "fps4G": 12.5,
    }

    control = FpvControl.from_dict(wire)

    assert control == FpvControl(
        device_result=0,
        token="ctl",
        issued_timestamp=1_700_000_000_000,
        expire_timestamp=1_700_000_600_000,
        expire_in=600,
        timeout_exit=15,
        preempt_user="someone",
        latency_threshold=1500,
        fps_4g=12.5,
    )


def test_absent_nulled_and_unknown_keys_all_parse() -> None:
    """Every field is optional in the app's model, and the server may add keys."""
    control = FpvControl.from_dict({"deviceResult": 9, "token": None, "somethingNew": {"x": 1}})

    assert control.device_result == 9
    assert control.token is None
    assert control.expire_in is None


def test_an_integral_fps_value_parses() -> None:
    assert FpvControl.from_dict({"fps4G": 15}).fps_4g == 15


def test_a_grant_is_device_result_zero_with_a_token() -> None:
    response = _parse({"code": 0, "msg": "ok", "data": {"deviceResult": 0, "token": "ctl"}})

    assert fpv_control_outcome(response) is FpvControlOutcome.GRANTED


def test_device_result_nine_is_occupied_by_another_user() -> None:
    response = _parse({"code": 0, "msg": "ok", "data": {"deviceResult": 9, "preemptUser": "a@b.c"}})

    assert fpv_control_outcome(response) is FpvControlOutcome.OCCUPIED


@pytest.mark.parametrize(
    "body",
    [
        {"code": 0, "msg": "ok", "data": {"deviceResult": 0, "token": "   "}},
        {"code": 0, "msg": "ok", "data": {"deviceResult": 0}},
        {"code": 0, "msg": "ok", "data": {"deviceResult": 2, "token": "ctl"}},
        {"code": 0, "msg": "ok", "data": {"deviceResult": 7, "token": "ctl"}},
        {"code": 0, "msg": "ok", "data": {"deviceResult": 42, "token": "ctl"}},
        {"code": 0, "msg": "ok", "data": {"token": "ctl"}},
        {"code": 0, "msg": "ok"},
        {"code": 1001, "msg": "no", "data": {"deviceResult": 0, "token": "ctl"}},
    ],
    ids=["blank-token", "no-token", "result-2", "result-7", "result-other", "no-result", "no-data", "envelope-code"],
)
def test_everything_else_is_unavailable(body: dict) -> None:
    assert fpv_control_outcome(_parse(body)) is FpvControlOutcome.UNAVAILABLE
