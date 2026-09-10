"""Invariants that were documented in prose but not asserted anywhere.

Each test here was written against the *unfixed* code and observed to fail, so it
catches the defect rather than restating the fix.
"""

from __future__ import annotations

from unittest.mock import MagicMock


from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.auth.token_manager import TokenManager
from tests._helpers import make_mock_handle


# CloudIOTGateway.from_cache must not touch the caller's dict


async def test_from_cache_does_not_mutate_the_callers_cache() -> None:
    """It is documented as pure — the host may re-persist the dict it passed in.

    ``data["connect_data"] = data["connect_response"]`` wrote a second key into the
    caller's credential cache, so a host that saved it back stored both.
    """
    cache = {"connect_response": {"data": {}}}
    before = {k: dict(v) for k, v in cache.items()}

    await CloudIOTGateway.from_cache(cache, MagicMock())  # returns None: cache is incomplete

    assert cache == before, "from_cache mutated the caller's dict"


# TokenManager.subscribe_handle must key on the device, not object identity


def test_subscribe_handle_keys_on_the_device_not_the_object() -> None:
    """One subscription per device, replaced when the device gets a new handle.

    Keying on ``id(handle)`` leaked an entry per handle and — because nothing holds a
    reference to the handle — let CPython address reuse silently short-circuit the
    subscribe for a re-registered device, so its auth errors stopped triggering a
    reactive refresh.
    """
    manager = TokenManager("a@example.com", MagicMock())
    first = make_mock_handle("dev1", "Luba-1")
    second = make_mock_handle("dev1", "Luba-1")  # same device, fresh handle

    manager.subscribe_handle(first)
    manager.subscribe_handle(second)

    assert len(manager._handle_subscriptions) == 1, (
        f"expected one subscription for dev1, got {len(manager._handle_subscriptions)}"
    )


def test_subscribing_the_same_handle_twice_is_idempotent() -> None:
    manager = TokenManager("a@example.com", MagicMock())
    handle = make_mock_handle("dev1", "Luba-1")

    manager.subscribe_handle(handle)
    manager.subscribe_handle(handle)

    assert len(manager._handle_subscriptions) == 1


def test_two_devices_get_their_own_subscriptions() -> None:
    manager = TokenManager("a@example.com", MagicMock())
    manager.subscribe_handle(make_mock_handle("dev1", "Luba-1"))
    manager.subscribe_handle(make_mock_handle("dev2", "Luba-2"))

    assert len(manager._handle_subscriptions) == 2


# stop_polling() must survive a reconnect


async def test_stop_polling_is_not_undone_by_a_reconnect() -> None:
    """``_on_ble_connected``'s comment claims this; ``update_availability`` broke it.

    The BLE CONNECTED edge spawns ``restart_keep_alive``, which restarts the loop
    whenever ``_keep_alive_task is None`` — exactly the state ``stop_polling()``
    leaves behind, so a host's explicit stop was undone by the next reconnect.
    """
    handle = make_mock_handle("dev1", "Luba-1")
    handle._skips_activity_loops = False

    await handle.stop_polling()
    assert handle._keep_alive_task is None

    await handle.restart_keep_alive()

    assert handle._keep_alive_task is None, "restart_keep_alive resurrected a stopped poll loop"
    await handle.stop()


async def test_start_re_enables_polling_after_stop_polling() -> None:
    """The stop is explicit, so ``start()`` is what clears it — not a reconnect."""
    handle = make_mock_handle("dev1", "Luba-1")
    handle._skips_activity_loops = False

    await handle.stop_polling()
    await handle.start()

    assert handle._keep_alive_task is not None
    await handle.stop()
