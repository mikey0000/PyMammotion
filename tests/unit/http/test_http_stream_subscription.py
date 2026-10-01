"""``MammotionHTTP.get_stream_subscription`` — the camera slots it asks for, and that its log never carries a token."""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock

import pytest

from pymammotion.http.http import redact_secrets
from tests.unit._helpers import make_agora_token, make_http_posting

_BODY = {"code": 0, "msg": "ok", "data": None}


def _posting():  # noqa: ANN202
    http, session = make_http_posting(200, _BODY)
    session.post.return_value.text = AsyncMock(return_value=json.dumps(_BODY))
    return http, session


def _states(session) -> list[int]:
    return [slot["cameraState"] for slot in session.post.call_args.kwargs["json"]["cameraStates"]]


@pytest.mark.parametrize("has_rear_camera", [False, True])
async def test_the_default_asks_for_the_front_camera_only(has_rear_camera: bool) -> None:
    """As the app does."""
    http, session = _posting()

    await http.get_stream_subscription("iot-1", has_rear_camera)

    assert _states(session) == [1, 0, 0]


@pytest.mark.parametrize(("has_rear_camera", "states"), [(False, [1, 1, 0]), (True, [1, 1, 1])])
async def test_all_cameras_adds_the_right_one_and_the_rear_one(has_rear_camera: bool, states: list[int]) -> None:
    """Slots 1-3 are Agora uids 1-3; the third, rear slot only when the mower has one."""
    http, session = _posting()

    await http.get_stream_subscription("iot-1", has_rear_camera, all_cameras=True)

    assert _states(session) == states


class TestRedactSecrets:
    def test_blanks_every_credential_value_and_keeps_the_shape(self) -> None:
        body = (
            '{"code":0,"data":{"appid":"app-secret","license":"lic-secret","uid":64077101,'
            '"token":"tok-secret","cameras":[{"cameraId":1,"token":"cam1-secret"},{"cameraId":2,"token":"cam2-secret"}],'
            '"key":"aes-secret","salt":"salt-secret","openEncrypt":0}}'
        )

        redacted = redact_secrets(body)

        for secret in ("app-secret", "lic-secret", "tok-secret", "cam1-secret", "cam2-secret", "aes-secret", "salt-secret"):
            assert secret not in redacted
        assert '"cameras":[{"cameraId":1,"token":"<redacted>"},{"cameraId":2,"token":"<redacted>"}]' in redacted
        assert '"uid":64077101' in redacted
        assert '"openEncrypt":0' in redacted

    def test_leaves_a_body_without_secrets_unchanged(self) -> None:
        assert redact_secrets('{"code":50504,"msg":"device offline"}') == '{"code":50504,"msg":"device offline"}'

    @pytest.mark.parametrize(
        "key",
        ["token", "appid", "license", "key", "salt", "accessToken", "refreshToken", "access_token", "refresh_token"],
    )
    def test_blanks_each_credential_key(self, key: str) -> None:
        assert redact_secrets(f'{{"{key}": "secret-value"}}') == f'{{"{key}":"<redacted>"}}'

    @pytest.mark.parametrize("key", ["appId", "Token", "AccessToken", "REFRESH_TOKEN"])
    def test_matches_keys_in_any_case(self, key: str) -> None:
        assert "secret-value" not in redact_secrets(f'{{"{key}":"secret-value"}}')


async def test_the_token_debug_log_is_redacted_and_names_the_claims(caplog: pytest.LogCaptureFixture) -> None:
    """The response body reaches the log only through ``redact_secrets``; the claims line carries uids, not tokens."""
    viewer = make_agora_token(channel="chan-1", uid="64077101")
    camera = make_agora_token(channel="chan-1", uid="2")
    body = {
        "code": 0,
        "msg": "ok",
        "data": {
            "appid": "app-secret",
            "openEncrypt": 0,
            "cameras": [{"cameraId": 2, "token": camera}],
            "channelName": "chan-1",
            "areaCode": "AREA_CODE_EU",
            "token": viewer,
            "uid": 64077101,
        },
    }
    http, session = make_http_posting(200, body)
    session.post.return_value.text = AsyncMock(return_value=json.dumps(body))

    with caplog.at_level(logging.DEBUG):
        await http.get_stream_subscription("iot-1", False, all_cameras=True)

    assert viewer[10:40] not in caplog.text
    assert camera[10:40] not in caplog.text
    assert "app-secret" not in caplog.text
    assert '"token":"<redacted>"' in caplog.text
    assert "viewer uid=64077101 channel=chan-1" in caplog.text
    assert "2: uid=2 channel=chan-1" in caplog.text
