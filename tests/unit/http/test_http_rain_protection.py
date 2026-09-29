"""``MammotionHTTP.save_rain_protection_config`` — the weather server's copy of the setting.

After the device acknowledges a rain-protection write, the app POSTs the same values
to ``/weather-server/v1/device/rain-protection/config`` (``CommonApiService
.saveRainProtectionConfig``, APK 2.3.20.30), on the same domain as device-server.
A dead token must raise rather than come back as ``Response(code=401)``.
"""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import pytest

from pymammotion.const import MAMMOTION_API_DOMAIN
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import UnauthorizedExceptionError
from pymammotion.http.model.rain_protection import RainProtectionConfig
from tests.unit._helpers import make_http_posting

DEVICE = "Luba-VAME9R5S"
_SAVED = {
    "code": 0,
    "msg": "success",
    "data": {"deviceName": DEVICE, "rainProtectionMode": 2, "customDelayHours": 24},
}


async def test_the_request_is_the_one_the_app_sends() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _SAVED)

    await http.save_rain_protection_config(DEVICE, 2, 24)

    assert session.post.await_args.args[0] == f"{MAMMOTION_API_DOMAIN}/weather-server/v1/device/rain-protection/config"
    assert session.post.await_args.kwargs["json"] == {
        "deviceName": DEVICE,
        "rainProtectionMode": 2,
        "customDelayHours": 24,
        "pushToDevice": False,
    }
    assert session.post.await_args.kwargs["headers"]["Authorization"] == "Bearer tok"


async def test_the_saved_config_parses() -> None:
    http, _ = make_http_posting(HTTPStatus.OK.value, _SAVED)

    response = await http.save_rain_protection_config(DEVICE, 2, 24)

    assert response.code == 0
    assert response.data == RainProtectionConfig(device_name=DEVICE, rain_protection_mode=2, custom_delay_hours=24)


@pytest.mark.parametrize("data", [None, True, {}], ids=["null", "bool", "empty"])
async def test_other_success_shapes_still_parse(data: object) -> None:
    """The app reads nothing from the response bean, so an unexpected shape must not fail the save."""
    http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 0, "msg": "success", "data": data})

    response = await http.save_rain_protection_config(DEVICE, 0, 0)

    assert response.code == 0


async def test_a_401_status_raises() -> None:
    http, _ = make_http_posting(HTTPStatus.UNAUTHORIZED.value, {"code": 401, "msg": "unauthorized"})

    with pytest.raises(UnauthorizedExceptionError):
        await http.save_rain_protection_config(DEVICE, 1, 0)
    assert http.reauth_required is None, "a 401 is a refresh signal; only a rejected refresh is terminal"


async def test_a_401_in_the_body_raises_even_under_a_200() -> None:
    http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 401, "msg": "token expired", "data": None})

    with pytest.raises(UnauthorizedExceptionError):
        await http.save_rain_protection_config(DEVICE, 1, 0)


async def test_the_token_is_checked_before_the_request_like_its_siblings() -> None:
    http, _ = make_http_posting(HTTPStatus.OK.value, _SAVED)

    with patch.object(MammotionHTTP, "ensure_token_valid", autospec=True) as ensure:
        await http.save_rain_protection_config(DEVICE, 2, 24)

    ensure.assert_awaited_once()
