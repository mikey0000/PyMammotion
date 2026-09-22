"""Builders shared across the unit and integration tiers.

Plain functions rather than fixtures, matching the tests/unit/transport/_fakes.py
and tests/unit/messaging/_helpers.py precedent: call sites stay terse and the
helpers stay greppable.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import partial
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt

from pymammotion.account.registry import AccountRegistry, AccountSession
from pymammotion.client import MammotionClient
from pymammotion.device.auto_fetch import AutoFetchWatchers
from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.device.inbound_router import InboundRouter
from pymammotion.state.device_state import TransportAvailability
from pymammotion.transport.base import TransportType
from pymammotion.transport.ble import BLETransport
from pymammotion.transport.cloud import CloudTransport

#: Signing key for test JWTs.  The library decodes with verify_signature=False,
#: so the key is irrelevant — it just has to satisfy pyjwt's minimum length.
JWT_TEST_KEY = "x" * 32


def encode_jwt(claims: dict[str, Any] | None = None, **extra: Any) -> str:
    """Encode a test JWT with the given claims (dict and/or keywords)."""
    payload = dict(claims or {})
    payload.update(extra)
    return pyjwt.encode(payload, JWT_TEST_KEY, algorithm="HS256")


def make_bare_client(session: AccountSession | None = None) -> MammotionClient:
    """A MammotionClient with only the registries and the inbound router initialised.

    For tests that exercise one client method in isolation: ``__new__`` skips
    the constructor's transports/loops, and *session* (if given) is registered
    directly — ``AccountRegistry.register`` is async and its lock is never
    contended here.  The device registry, inbound router and auto-fetch watchers are
    set up because the client's own methods delegate straight into them.
    """
    client = MammotionClient.__new__(MammotionClient)
    client._account_registry = AccountRegistry()
    client._device_registry = DeviceRegistry()
    client._inbound = InboundRouter(client._device_registry)
    client._watchers = AutoFetchWatchers(
        client._device_registry,
        start_map_sync=client.start_map_sync,
        start_plan_sync=client.start_plan_sync,
        start_mow_path_saga=client.start_mow_path_saga,
    )
    if session is not None:
        client._account_registry._sessions[session.account_id] = session
    return client


def make_mock_transport(
    transport_type: TransportType = TransportType.CLOUD_ALIYUN,
    *,
    connected: bool = True,
    usable: bool = True,
    **overrides: Any,
) -> MagicMock:
    """A MagicMock shaped like a Transport, superset of every per-file variant.

    Every attribute a DeviceHandle/queue/poll-loop code path may touch is set
    explicitly, so a new gate reading an unset attribute fails loudly instead
    of passing on a truthy auto-created MagicMock.
    """
    t = MagicMock()
    # isinstance() honours a Mock's __class__, and the send paths now narrow on it:
    # the quota and terminal-auth API live on CloudTransport, not on Transport.
    t.__class__ = BLETransport if transport_type is TransportType.BLE else CloudTransport
    t.transport_type = transport_type
    t.is_connected = connected
    t.availability = TransportAvailability.CONNECTED if connected else TransportAvailability.DISCONNECTED
    t.is_usable = usable
    t.is_rate_limited = False
    t.is_send_blocked = MagicMock(return_value=False)
    t.seconds_until_send_available = MagicMock(return_value=0.0)
    if transport_type is not TransportType.BLE:
        t.is_cloud_banned = False
        t.is_quota_exhausted = False
        # Bind the *real* refusal so a double cannot quietly neuter the gate: it is a
        # method now, and a plain MagicMock attribute would return a Mock and let every
        # blocked send through.  Bound to the mock, so it reads the mock's
        # is_send_blocked / is_cloud_banned / seconds_until_send_available.
        t.raise_if_send_blocked = partial(CloudTransport.raise_if_send_blocked, t)
    t.last_send_monotonic = 0.0
    t.last_received_monotonic = 0.0
    t.send = AsyncMock()
    t.send_heartbeat = AsyncMock()
    t.connect = AsyncMock()
    t.disconnect = AsyncMock()
    t.on_message = None
    t.set_rate_limited = MagicMock()
    t.add_availability_listener = MagicMock()
    for name, value in overrides.items():
        setattr(t, name, value)
    return t


def make_mock_mowing_device(**overrides: Any) -> MagicMock:
    """A MagicMock shaped like a MowingDevice.

    Explicit ``charge_state = 0`` because ``int(MagicMock())`` returns 1, which
    would push DeviceHandle._device_mode into DOCKED_CHARGING and surprise
    tests that don't otherwise care about charge state.
    """
    device = MagicMock()
    device.online = True
    device.enabled = True
    device.report_data.dev.battery_val = 75
    device.report_data.dev.charge_state = 0
    device.report_data.dev.sys_status = "idle"
    device.report_data.work.knife_height = 40
    for name, value in overrides.items():
        setattr(device, name, value)
    return device


def make_mock_handle(
    device_id: str = "dev1",
    device_name: str = "Luba-Test",
    *,
    prefer_ble: bool = False,
    device: Any | None = None,
    mqtt_transport: MagicMock | None = None,
    ble_transport: MagicMock | None = None,
) -> DeviceHandle:
    """A real DeviceHandle backed by a mock MowingDevice."""
    return DeviceHandle(
        device_id=device_id,
        device_name=device_name,
        initial_device=device if device is not None else make_mock_mowing_device(),
        prefer_ble=prefer_ble,
        mqtt_transport=mqtt_transport,
        ble_transport=ble_transport,
    )


def make_device_record(
    device_name: str = "Yuka-TEST",
    iot_id: str = "iot-yuka",
    product_key: str = "pk1",
) -> MagicMock:
    """A MagicMock shaped like a DeviceRecord."""
    record = MagicMock()
    record.device_name = device_name
    record.iot_id = iot_id
    record.product_key = product_key
    return record


def make_mock_http(
    *,
    device_records: list[MagicMock] | None = None,
    share_records: list[MagicMock] | None = None,
    mqtt_creds: MagicMock | None = None,
) -> MagicMock:
    """A MagicMock shaped like MammotionHTTP, carrying the given fixture data.

    ``get_user_device_page`` both returns its data and updates ``http.device_records``
    as a side effect, so both are set.  ``validate_login`` answers True because
    ``restore_credentials`` checks it before touching any transport.
    """
    http = MagicMock()
    http.get_user_device_list = AsyncMock(return_value=MagicMock(data=[]))
    http.get_user_shared_device_page = AsyncMock(return_value=MagicMock(data=MagicMock(records=share_records or [])))
    page = MagicMock()
    page.data = MagicMock()
    page.data.records = device_records or []
    http.get_user_device_page = AsyncMock(return_value=page)
    http.get_mqtt_credentials = AsyncMock()
    http.confirm_share = AsyncMock()
    http.mqtt_credentials = mqtt_creds or MagicMock()
    http.login_info = MagicMock()
    http.validate_login = AsyncMock(return_value=True)
    http.device_records = MagicMock(records=[])
    return http


def make_account_session(
    account_id: str = "test@example.com",
    *,
    email: str | None = None,
    password: str = "password123",
    http: Any | None = None,
    token_manager: Any | None = None,
) -> AccountSession:
    """An AccountSession with its HTTP client and token manager already mocked.

    The defaults are the skeleton every caller needs; rig the specific collaborators
    a test cares about on the returned session rather than growing this signature.
    """
    session = AccountSession(
        account_id=account_id,
        email=account_id if email is None else email,
        password=password,
    )
    session.mammotion_http = MagicMock() if http is None else http
    session.token_manager = MagicMock() if token_manager is None else token_manager
    return session


async def wait_until(
    predicate: Callable[[], object],
    *,
    timeout: float = 2.0,
    message: str = "",
) -> None:
    """Yield to the event loop until *predicate* is true, or fail the test.

    The replacement for ``await asyncio.sleep(0.1)`` as a synchronisation device
    (docs/testing.md section 6).  A fixed sleep is both slower than it needs to be and
    a flake on a loaded runner; this returns the moment the condition holds and
    only spends the timeout when something is genuinely wrong.

    The first turns are pure ``sleep(0)`` yields, which settle a task that merely
    needs to be scheduled in microseconds.  After that it falls back to a short
    timed wait, because a condition gated on a real timer in the code under test
    cannot be reached by spinning — this is the one place in the suite where a
    timed sleep is the right tool, which is why it lives here rather than being
    retyped at call sites.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    turns = 0
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError(message or f"condition not met within {timeout}s")
        await asyncio.sleep(0 if turns < 50 else 0.001)
        turns += 1


async def block_forever() -> None:
    """Await something that never completes, for stubs whose point is to hang.

    An ``asyncio.Event`` nobody sets, rather than ``sleep(3600)``: no timer is
    armed, and the intent — this never finishes, cancel it — is on the tin.
    """
    await asyncio.Event().wait()


async def let_others_run(turns: int = 10) -> None:
    """Yield the event loop *turns* times so every other ready task can make progress.

    What ``await asyncio.sleep(0.02)`` inside a stub is usually reaching for: stay
    inside the critical section long enough that an unsynchronised caller would
    overlap it, so the test can tell a working lock from a missing one.  Spending
    loop turns instead of wall-clock keeps that discriminating power without
    depending on how fast the machine is.
    """
    for _ in range(turns):
        await asyncio.sleep(0)


async def advance_real_time(seconds: float) -> None:
    """Let *seconds* of real time pass, when the passage of time is the stimulus.

    Not a synchronisation device — ``wait_until`` is that.  This is for the rare
    test whose subject *is* a production timer: a debounce window that must
    genuinely age, a cooldown that must genuinely expire.  Naming it keeps those
    cases greppable and separates them from the fixed sleeps section 6 bans.
    Prefer injecting a clock over calling this; reach for it only when the timer
    is driven by the event loop's own clock, which ``time_machine`` cannot move.
    """
    await asyncio.sleep(seconds)
