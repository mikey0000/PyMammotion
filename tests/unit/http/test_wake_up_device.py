"""MammotionHTTP.wake_up_device — the only route back from MODE_SLEEPING.

Mirrors the app's ``POST device/wakeup`` (HomeApiService.java:130 in APK
2.3.8.201): the device *name* goes in the body and the answer is a bare boolean
under ``data``.
"""

from __future__ import annotations

from http import HTTPStatus

from tests.unit._helpers import make_http_posting


async def test_posts_device_name_and_bearer_token() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, {"code": 0, "msg": "success", "data": True})

    response = await http.wake_up_device("Luba-VATEST")

    assert response.data is True
    assert session.post.call_args.args[0].endswith("/device-server/v1/device/wakeup")
    # The endpoint keys off deviceName, not iotId.
    assert session.post.call_args.kwargs["json"] == {"deviceName": "Luba-VATEST"}
    assert session.post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"


async def test_cloud_refusal_is_surfaced_not_swallowed() -> None:
    """The app treats data=False as an outright failure; callers must be able to."""
    http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 0, "msg": "success", "data": False})

    assert (await http.wake_up_device("Luba-VATEST")).data is False


async def test_http_error_reports_the_status() -> None:
    http, _ = make_http_posting(500, {"code": 500, "msg": "boom"})

    response = await http.wake_up_device("Luba-VATEST")

    assert response.code == 500
    assert response.data is None
