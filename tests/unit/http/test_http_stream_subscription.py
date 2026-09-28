"""``MammotionHTTP.get_stream_subscription`` — which camera slots the token request asks for."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from tests.unit._helpers import make_http_posting

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
