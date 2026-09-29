"""``MammotionClient.refresh_function_codes`` — the per-firmware function set the app gates features on.

Driven through a real ``MammotionHTTP`` (only its aiohttp session is canned) and a
real ``DeviceHandle`` over a real ``MowerDevice``, so the parse, the 401 check and
the state write are the production ones.  The ``TokenManager`` is autospecced to
prove this path never reaches it: a failed fetch must not touch the auth state.
"""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, create_autospec

from aiohttp import ClientConnectionError
import pytest

from pymammotion.auth.token_manager import TokenManager
from pymammotion.client import MammotionClient
from pymammotion.data.model.device import MowerDevice
from pymammotion.data.model.function_codes import FunctionCodes
from pymammotion.device.handle import DeviceHandle
from pymammotion.http.model.http import UnauthorizedExceptionError
from tests._helpers import make_account_session, make_bare_client
from tests.unit._helpers import make_http_posting

ACCOUNT = "acct@example.com"
DEVICE = "Luba-VSLKJX"
PRODUCT_KEY = "a1BmXWlsdbA"
FIRMWARE = "1.12.3.10"


def _functions_body(*codes: str) -> dict:
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "productKey": PRODUCT_KEY,
            "productVersion": FIRMWARE,
            "functions": [{"id": str(i), "functionCode": code} for i, code in enumerate(codes)],
        },
    }


def _reply(status: int, body: dict) -> MagicMock:
    reply = MagicMock(status=status, headers={"Content-Type": "application/json"})
    reply.json = AsyncMock(return_value=body)
    return reply


async def _client(
    *replies: tuple[int, dict],
    firmware: str = FIRMWARE,
    product_key: str = PRODUCT_KEY,
    stored: FunctionCodes | None = None,
) -> tuple[MammotionClient, DeviceHandle, MagicMock, MagicMock]:
    """A client whose one account owns *DEVICE*; consecutive POSTs answer with *replies*."""
    http, http_session = make_http_posting(HTTPStatus.OK.value, {})
    http_session.post = AsyncMock(side_effect=[_reply(status, body) for status, body in replies])
    token_manager = create_autospec(TokenManager, instance=True)
    client = make_bare_client(make_account_session(ACCOUNT, http=http, token_manager=token_manager))
    device = MowerDevice(name=DEVICE)
    device.device_firmwares.device_version = firmware
    if stored is not None:
        device.function_codes = stored
    handle = DeviceHandle(device_id="dev1", device_name=DEVICE, initial_device=device, product_key=product_key)
    await client._device_registry.register(handle, account_id=ACCOUNT)
    return client, handle, http_session, token_manager


def _stored(handle: DeviceHandle) -> FunctionCodes:
    return handle.snapshot.raw.function_codes


async def test_it_stores_the_set_for_the_current_firmware() -> None:
    client, handle, http_session, _ = await _client((HTTPStatus.OK.value, _functions_body("002.002", "003.001")))

    assert await client.refresh_function_codes(DEVICE) is True

    assert _stored(handle) == FunctionCodes(PRODUCT_KEY, FIRMWARE, ["002.002", "003.001"])
    assert handle.snapshot.raw.supports_function_code("002.002")
    assert http_session.post.await_args.kwargs["json"] == {"productKey": PRODUCT_KEY, "productVersion": FIRMWARE}


async def test_a_set_already_current_is_not_refetched() -> None:
    """The app's cache is keyed by (productKey, productVersion) with no expiry; a hit never calls out."""
    client, _, http_session, _ = await _client(stored=FunctionCodes(PRODUCT_KEY, FIRMWARE, ["002.002"]))

    assert await client.refresh_function_codes(DEVICE) is False

    http_session.post.assert_not_awaited()


async def test_force_refetches_a_current_set() -> None:
    client, handle, _, _ = await _client(
        (HTTPStatus.OK.value, _functions_body("001.006.001")),
        stored=FunctionCodes(PRODUCT_KEY, FIRMWARE, ["002.002"]),
    )

    assert await client.refresh_function_codes(DEVICE, force=True) is True

    assert _stored(handle).codes == ["001.006.001"]


async def test_a_set_for_older_firmware_is_refetched() -> None:
    client, handle, _, _ = await _client(
        (HTTPStatus.OK.value, _functions_body("002.002")),
        stored=FunctionCodes(PRODUCT_KEY, "1.11.0.0", []),
    )

    assert await client.refresh_function_codes(DEVICE) is True

    assert _stored(handle).product_version == FIRMWARE


@pytest.mark.parametrize(("firmware", "product_key"), [("", PRODUCT_KEY), (FIRMWARE, "")], ids=["no-fw", "no-pk"])
async def test_nothing_is_requested_until_firmware_and_product_key_are_known(firmware: str, product_key: str) -> None:
    client, _, http_session, _ = await _client(firmware=firmware, product_key=product_key)

    assert await client.refresh_function_codes(DEVICE) is False

    http_session.post.assert_not_awaited()


async def test_the_devices_reported_product_key_is_used_when_the_handle_has_none() -> None:
    """A BLE-discovered handle has no device-list product key; the device reports its own."""
    client, handle, http_session, _ = await _client((HTTPStatus.OK.value, _functions_body()), product_key="")
    handle.snapshot.raw.mower_state.product_key = PRODUCT_KEY

    assert await client.refresh_function_codes(DEVICE) is True

    assert http_session.post.await_args.kwargs["json"]["productKey"] == PRODUCT_KEY


async def test_a_network_error_is_not_terminal_and_leaves_the_state_alone() -> None:
    client, handle, _, token_manager = await _client()
    client._account_registry.get(ACCOUNT).mammotion_http._client_session = MagicMock(
        side_effect=ClientConnectionError("down")
    )

    assert await client.refresh_function_codes(DEVICE) is False

    assert _stored(handle) == FunctionCodes()
    assert token_manager.method_calls == [], "a failed fetch must not reach the auth layer"


async def test_an_error_code_leaves_the_state_alone() -> None:
    client, handle, _, _ = await _client((HTTPStatus.OK.value, {"code": 500, "msg": "internal", "data": None}))

    assert await client.refresh_function_codes(DEVICE) is False

    assert _stored(handle) == FunctionCodes()


async def test_a_401_propagates_without_a_refresh() -> None:
    """A rejected session is a signal, not an empty set; this path never refreshes, so it sets no flag."""
    client, handle, _, token_manager = await _client((HTTPStatus.OK.value, {"code": 401, "msg": "expired"}))

    with pytest.raises(UnauthorizedExceptionError):
        await client.refresh_function_codes(DEVICE)

    assert token_manager.method_calls == []
    assert _stored(handle) == FunctionCodes()


async def test_an_unregistered_device_is_a_no_op() -> None:
    client, _, http_session, _ = await _client()

    assert await client.refresh_function_codes("Luba-UNKNOWN") is False

    http_session.post.assert_not_awaited()
