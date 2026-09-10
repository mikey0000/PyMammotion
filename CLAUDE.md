# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PyMammotion is a Python library (published as `pymammotion`) for controlling Mammotion robot mowers (Luba, Luba 2, Yuka) over MQTT/Cloud, Bluetooth (BLE), and HTTP. It serves as the backend for the [Mammotion Home Assistant integration](https://github.com/mikey0000/Mammotion-HA).

## Development Setup

```bash
uv sync
```

## Commands

```bash
# Linting and formatting
uv run ruff check --fix pymammotion/
uv run ruff format pymammotion/

# Type checking (excludes proto/, tests/, scripts/ — configured in pyproject.toml [tool.ty])
uv run ty check pymammotion/

# Additional linting
uv run pylint pymammotion/

# Run pre-commit hooks on all files
uv run pre-commit run --all-files

# Run a single test file
uv run python tests/login_test.py

# Regenerate protobuf Python code from .proto files
# (CI verifies this output matches the checked-in *_pb2.py / __init__.py — see .github/workflows/on-push.yml)
uv run protoc -I=. --python_out=. --python_betterproto2_out=pymammotion/proto ./pymammotion/proto/*.proto

# Version bump (patch/minor/major)
uv run bumpver update --patch

# Pre-release bump: 0.9.0 -> 0.9.1b0 -> 0.9.1b1 -> ... -> 0.9.1
uv run bumpver update --patch --tag beta   # open a new beta series
uv run bumpver update --tag-num            # next beta of the same series
uv run bumpver update --tag final          # promote the beta to the release

# bumpver does not touch uv.lock, which records the workspace version.
# Re-lock after every bump or `uv sync --frozen` fails in CI.
uv lock
```

Releases are cut by pushing a `v<version>` tag; `release.yml` compares the tag
against the built package after PEP 440 normalisation (so `v0.9.0-beta1` and
`v0.9.0b1` both match a `0.9.0b1` package) and marks the GitHub release as a
pre-release when the version is one.

## Architecture

The refactored architecture is a **layered, composable system** replacing the earlier monolithic god-object pattern.

The full structural guide — module inventory, the four flows (inbound message,
outbound command, saga, credentials), the single-home table, and extension
recipes — is `docs/architecture.md`. The summary below plus the invariants that
follow it are the rules; that file is the map.

```
┌──────────────────────────────────────────────────────────┐
│  MammotionClient  (pymammotion/client.py)                │
│  HA-facing stable API; owns DeviceRegistry +             │
│  AccountRegistry + BLETransportManager                   │
├──────────────────────────────────────────────────────────┤
│  DeviceHandle  (pymammotion/device/handle.py)            │
│  Per-device facade integrating:                          │
│  ├─ DeviceMessageBroker  (messaging/broker.py)           │
│  │   request/response correlation via protobuf oneof     │
│  │   field names; also hosts the unsolicited EventBus    │
│  ├─ DeviceCommandQueue  (messaging/command_queue.py)     │
│  │   priority queue; saga exclusivity                    │
│  ├─ StateReducer  (device/state_reducer.py)              │
│  │   pure function: LubaMsg → updated MowingDevice       │
│  ├─ DeviceStateMachine  (device/state.py)                │
│  │   immutable snapshots; debounced state_changed_bus    │
│  └─ Transport[]  (one or more, see below)                │
├──────────────────────────────────────────────────────────┤
│  Transport layer  (pymammotion/transport/)               │
│  ├─ CloudTransport  (cloud.py)  — broker-only surface:   │
│  │   send quota, terminal auth flags, thing/* callbacks  │
│  │   ├─ AliyunMQTTTransport  (aliyun_mqtt.py)            │
│  │   │   pre-2025 devices; HMAC-SHA1, paho, port 8883    │
│  │   └─ MQTTTransport  (mqtt.py)                         │
│  │       post-2025 devices; aiomqtt, JWT password        │
│  │       send() raises AuthError on HTTP 401/460         │
│  └─ BLETransport  (ble.py)  — straight off Transport     │
│      bleak + bleak-retry-connector; all device types     │
├──────────────────────────────────────────────────────────┤
│  Saga layer  (pymammotion/messaging/)                    │
│  Restartable multi-step operations:                      │
│  ├─ Saga  (saga.py)  — base class with retry logic       │
│  ├─ MapFetchSaga  (map_saga.py)                          │
│  ├─ MowPathSaga  (mow_path_saga.py)                      │
│  └─ Plan/Spino/Svg/EdgeMapping sagas (messaging/)        │
├──────────────────────────────────────────────────────────┤
│  Auth  (pymammotion/auth/token_manager.py)               │
│  TokenManager: one instance per account                  │
│  Proactive refresh with asyncio.Lock mutex:              │
│  ├─ HTTP OAuth (refresh 5 min before expiry)             │
│  ├─ Aliyun IoT token (refresh 1 h before expiry)         │
│  └─ Mammotion MQTT JWT (refresh 30 min before expiry)    │
│  NO automatic password login — refresh tokens only       │
│  Terminal flags: reauth_required (account-wide) /        │
│  aliyun_unavailable / mqtt_unavailable (transport-only)  │
├──────────────────────────────────────────────────────────┤
│  HTTP + Cloud Gateway                                    │
│  ├─ MammotionHTTP  (http/http.py)                        │
│  └─ CloudIOTGateway  (aliyun/cloud_gateway.py)           │
└──────────────────────────────────────────────────────────┘
```

### Key Patterns

**Message flow** (incoming):
```
Transport.on_message(raw bytes)
  → DeviceHandle._on_raw_message()
      1. Decode bytes → LubaMsg
      2. StateReducer.apply(current, msg) → new MowingDevice  (pure)
      3. DeviceStateMachine.apply(new_device) → snapshot + changed
      4. Emit snapshot to state_changed_bus (HA subscribes here)
      5. DeviceMessageBroker.on_message(luba_msg)
           ├─ solicited  → resolve pending future
           └─ unsolicited → EventBus.emit (sagas / subscribers)
```

**Request/response correlation:** protobuf `oneof` field name (e.g. `toapp_gethash_ack`) is used as the key — no explicit request ID in the Mammotion protocol. `ConcurrentRequestError` is raised if the same field is already pending.

**Sagas** use `subscribe_unsolicited()` — registering the handler *before* sending the command to avoid the race where the device responds before the handler is registered. The RAII `Subscription` auto-unsubscribes on context exit.

**TokenManager** holds a single `asyncio.Lock` to prevent concurrent refresh races. Both getters (`get_aliyun_credentials`, `get_mammotion_mqtt_credentials`) check expiry under the lock and refresh proactively.

**One account is one login session is one TokenManager, and the login comes first.** `restore_credentials` rebuilds the account's `MammotionHTTP` from the cache (`MammotionHTTP.from_cache` — pure, no I/O, returns `None` on a corrupt cache rather than raising), validates it once (`validate_login` = local expiry check, then one real authenticated call), and only then hands that one instance to `_restore_aliyun` and `_restore_mammotion_mqtt`. Neither restorer decodes cached credentials or builds a login of its own; `CloudIOTGateway.from_cache` is *given* the http. `MammotionClient._ensure_token_manager` is the only place a `TokenManager` is constructed — a second manager for one account is never harmless, because the first keeps its refresh scheduler running (two schedulers then rotate the same refresh token concurrently) and any transport built earlier still holds it, so the terminal flags it sets land on an object the session no longer points at. The Aliyun gateway is attached to the existing manager (`attach_cloud_gateway`), never used to construct a replacement.

**A 401 is a signal, not a return value.** Endpoints that carry the access token raise `UnauthorizedExceptionError` on a 401 — checking *both* the HTTP status and the in-body `code`, since the server uses either (`mqtt_invoke`, `get_user_device_list`). Handing a `Response(code=401)` back instead makes a rejected session indistinguishable from an empty result, and every caller then treats a dead login as "no devices". The same reasoning governs the best-effort `try/except` blocks around those calls in `restore_credentials`: they step over network blips and malformed payloads, but re-raise `_AUTH_REJECTED` — swallowing that would let a restore finish and report success on a session the server has already invalidated, leaving a healthy-looking integration whose every command fails.

This is why `validate_login` ends in a real call rather than a local expiry check alone: a token revoked server-side (logged out, signed in elsewhere) keeps its `exp` weeks in the future, so nothing computed locally can see it. Use an endpoint that is known to exist and is needed anyway — `get_user_device_list`, which the restore fetches moments later regardless. Do not reintroduce `/user/oauth/check`: it 404s on live accounts, and treating that as a rejection made every restore refresh (spending the cached refresh token) and then re-login anyway.

**Never log in with a stored password automatically.** `login_v2` is the only password grant in the library, and exactly one path may reach it: `MammotionClient.login_and_initiate_cloud`. `restore_credentials` falls back to it only when the cache cannot produce a usable *login* — `MammotionHTTP.from_cache` returns `None`, or `MammotionHTTP.validate_login` finds the server no longer accepts it. An unusable cached *Aliyun* session is not one of those: `_restore_aliyun` rebuilds the gateway from the healthy login via `connect_iot`, because that authCode chain is what mints an Aliyun session in the first place. Every automatic renewal uses a refresh token (`refresh_token_v2`) or, for Aliyun, the existing login's authCode chain (`connect_iot`). An automatic password login bypasses the host's re-auth prompt and, during a server-side outage, fires one password grant per queued request — the shape of the oauth2/token hammering Mammotion reported. If you add a refresh path, it must not be able to call `login_v2`; `tests/unit/http/test_token_refresh.py` asserts this against the AST.

**Failures are scoped, and a rejection is terminal.** There are no retry timers or cooldowns in the auth layer: a rejected refresh token does not become valid by waiting, so retrying it only adds load.
- **Account-scoped** — `refresh_token_v2` rejected → `TokenManager.reauth_required` is set, `ReLoginRequiredError` propagates to the host, and `MammotionClient.on_unrecoverable_auth_error` fires so the user is prompted to re-authenticate. Every later call fails fast with no network.
- **Transport-scoped** — the Aliyun IoT session or Mammotion MQTT JWT is unrenewable while the HTTP login is still healthy → `aliyun_unavailable` / `mqtt_unavailable` is set and only that transport is given up. Its mowers are signalled via the per-device error bus, but the global callback does **not** fire: the login, the cached credentials, and the account's *other* transport must survive.
- **Transient network errors are neither.** They propagate as their own type (`is_transient_network_error` classifies them) so callers back off, and they must never set a terminal flag — a blip would otherwise strand a working login behind a re-auth prompt the user cannot satisfy.

**Recovery is one attempt, scoped to the failing transport.** `MammotionClient._send_with_auth_retry` does one targeted refresh and one retry, then propagates. Note that `AuthError` subclasses `TransportError`, so its `except AuthError: raise` clause must stay ahead of the `except TransportError` catch — otherwise the terminal signal is swallowed into a log line.

**Reactive refreshes are deduplicated by access token.** `TokenManager.refresh_invoke_token(stale_token=...)` compares the token the failed request actually used against the live one and returns early if they differ — another caller already refreshed, so the caller just retries. Without this, a burst of commands that all 401 on the same dead token produces one refresh *each* (serialized by the lock), and every refresh rotates the refresh token server-side, so the later rotations race the earlier ones. Ported from the Android app's `SpecialCodeIntercepter.refreshToken`, which guards identically by comparing the request's `Authorization` header against its stored token. Any new reactive-refresh caller should pass the token it sent.

**Credential renewal is clock-driven, not traffic-driven.** `TokenManager.start_refresh_scheduler()` runs one task per account that sleeps until the earliest credential is within its lead window (5 min HTTP / 30 min MQTT JWT / 1 h Aliyun — the same thresholds the lazy getters use), renews just that one, and sleeps again. It does not poll. `MammotionClient` starts it from the two public entry points (`login_and_initiate_cloud`, `restore_credentials`) and stops it in `_sign_out_session` and `stop()`.

This exists because every other refresh path is lazy — it runs because something asked for a credential. When all of an account's devices are offline, `mqtt_activity_loop` skips sending (`has_usable_transport` is False), so no HTTP call is made, `ensure_token_valid` never fires, and the in-band Aliyun expiry check *inside* `send_cloud_command` never runs. Without the scheduler nothing renews anything and the credentials rot until the refresh tokens themselves expire, at which point recovery needs the user. Refresh order matters: HTTP goes first, because both the Mammotion JWT and the Aliyun session are minted using the HTTP access token.

**A user-initiated command does not queue.** `Priority.USER` and `Priority.EMERGENCY` are *direct-send* levels: `MammotionClient` dispatches them on the caller's own task and `DeviceCommandQueue.enqueue` raises `ValueError` if given one. Ranking them inside the queue cannot work — the processor is strictly sequential, so an item behind an in-flight saga waits for that saga's `work()` to return no matter how it sorts. A direct command still picks its transport through `send_raw`/`active_transport()` and is still classified by `messaging.command_queue.execute_command` (the same gateway-timeout retry and demotion buckets the queue uses), but with `reraise=True` so the host learns it did not land — including `NoTransportAvailableError`, where the queued path returns silently.

**The send quota paces polling, not people.** `CloudTransport` separates the two block sources: `is_cloud_banned` (the broker answered 429; `set_rate_limited()` started a fixed 12 h timer) and `is_quota_exhausted` (our own 600-per-12 h rolling window, which exists to avoid ever provoking that 429). `is_send_blocked(fw, user_initiated=True)` honours the ban and skips the quota, and `CloudTransport.send_user()` is the verb that carries it. What actually spends the budget is library-internal traffic, not people: `transfers.ack_stream` sends one ack **per received frame** (a single map fetch is easily hundreds of sends), the MQTT poll loop fires a one-shot report every 5–60 min per device mode, `auto_fetch` watchers trigger whole map/plan sagas on a state change, and the host's own periodic refresh adds more. None of that is ever `Priority.USER`, so exempting genuine button presses does not meaningfully loosen the budget. `Priority.USER` is still opt-in per call site, but for an ordering reason rather than a budget one — see the rule in `docs/decisions.md` D14. BLE has no quota; `_send_marked` routes only cloud transports to `send_user`.

**Cloud error codes live in one table.** `pymammotion/aliyun/exceptions.py` holds `DEVICE_OFFLINE_CODES`, `DEVICE_UNBOUND_CODES`, `GATEWAY_TIMEOUT_CODES` (plus the pairing-flow codes, currently unused). Both cloud send paths — `CloudIOTGateway.send_cloud_command` and `MQTTTransport._invoke` — classify against them, so a newly-observed code is added once. Don't pattern-match a raw code inline in a send path.

**BLE is a per-device transport; accounts are cloud-only.** `DeviceRegistry` is keyed by `(account_id, device_id)` — one `DeviceHandle` per account per device. A handle no account has claimed (BLE-only) sits under the sentinel key `BLE_ONLY_ACCOUNT` (`"__ble__"`), which is a registry key only: no `AccountSession` is ever registered under it, and `AccountSession.device_ids` lists cloud-bound devices alone. Every registration goes through `MammotionClient._ensure_device_handle`: a cloud login for a device that has a sentinel handle **re-keys that same object** onto the account (BLE transport, state and `prefer_ble` intact) rather than building a second handle; account sign-out re-keys a BLE-owning handle back to the sentinel with the cloud transports detached, so BLE keeps running. Exactly one handle owns a device's `BLETransport` (`DeviceRegistry.find_ble_owner`); it stays with its holder until `move_ble_to_account` hands it over. Cloud transports are account-shared objects — a handle detaches them (`detach_transport`, which also removes its availability listener) and never disconnects them; the session does that once. Name-only public methods take an optional `account_id`; without it the unique holder is used, else the BLE owner, else the first cloud holder with a warning.

**Never send *background* MQTT to an offline device.** When the cloud has reported a device offline (`DeviceAvailability.mqtt_reported_offline = True`, set by `DeviceOfflineException` and "offline" `thing/status` messages), no automatic path should fire a send at that device — not periodic polls, not heartbeats, not sagas, not queued coordinator refreshes. Nobody is waiting on that traffic, so it has no reason to spend sends probing a device the cloud says is away. Gates that enforce this:
- `DeviceHandle._cloud_transport_usable()` is the one gate; `active_transport()` raises `NoTransportAvailableError` through it when MQTT is the only registered transport and `mqtt_reported_offline` is True.
- `DeviceHandle._mqtt_activity_loop` pre-flights `active_transport()` and skips when it raises.
- `MammotionClient.send_command_with_args` short-circuits with a debug log when offline-and-no-BLE.
- Any new *background* send path you add must follow the same gate, or route via `send_raw` / `send_command_with_args` which already check it.

**A user command is the exception: it passes the offline flag and is sent immediately.** `Priority.USER` / `EMERGENCY` thread `user_initiated=True` down `send_raw` → `active_transport` → `_cloud_transport_usable`, which then ignores `mqtt_reported_offline` — and *only* that flag; a terminal auth failure (`is_usable`) still refuses everyone. Such commands also bypass the queue entirely (`Priority.is_direct` → `execute_command` on the caller's task), so they are never held behind a saga or TTL-dropped. BLE is unaffected and still wins when connected, so this only ever decides MQTT-or-nothing.

This reverses an earlier "the gate is uniform, no exceptions" rule. The reasoning that supported it does not survive contact with the send path:

1. **There is no queued-delivery hazard on this path.** The old rule's decisive point was that the cloud may hold a payload and deliver it when the device returns, so a `start_job` could arrive hours later unattended. A send is not a publish into a broker queue — it is a synchronous HTTPS POST (`CloudIOTGateway.send_cloud_command` → `/thing/service/invoke`, `cloud_gateway.py`; `MQTTTransport._invoke` → `mqtt_invoke`). An offline device is **rejected** with a `DEVICE_OFFLINE_CODES` code, which raises `DeviceOfflineException`, re-arms the flag and propagates to the caller. The cloud declines it; nothing is left queued to act on the mower later. MQTT carries the *replies*, which is why its state is a poor proxy for whether a command can be delivered at all.
2. **The flag is advisory, not an observation.** It is only ever as fresh as the last thing the cloud chose to push. Refusing on it converts a possibly-stale cloud opinion into a hard failure for someone standing next to a mower they can see is running. One bounded round trip settles it, and self-reports either way.
3. **"The flag clears only on an inbound frame" is still false**, and is still not the justification. Six paths clear it and five need nothing from us: `on_status_message` on an "online" `thing/status` (its comment notes this lands "even before the first protobuf frame"), `on_device_properties`, `on_mammotion_properties`, `on_device_event`, `on_raw_message` on any inbound frame, plus `add_transport` clearing a stale flag. That refutes a specific deadlock claim; it is not the reason for the exception. Points 1 and 2 are.

Still true: a *sleeping* device is woken over HTTP via `wake_device`, never by firing MQTT at it.

**BLE reaches the mower through Home Assistant's bluetooth stack, in practice ESP32 (ESPHome) proxies.** Everything about `BLETransport` follows from that:

- **HA owns discovery.** `self_managed_scanning` stays off; HA pushes each advertisement's `BLEDevice` via `set_ble_device()` (`ble_inventory.update_ble_device`). The pointer matters because the proxy that hears the mower changes over time, so `establish_connection` gets `ble_device_callback=lambda: self._ble_device` to re-read it on every attempt. Never cache a `BLEDevice` anywhere else.
- **bleak's service cache is per address and lives for the whole process.** `establish_connection(..., use_services_cache=True)` reuses the cached GATT table across client objects *and* across proxies. A link that connects and then fails with `Characteristic 0000ff02-… was not found` (`BleakCharacteristicNotFoundError`) is a stale table, not a device change — the Yuka/ESPHome report that motivated this. `connect()` clears the cache (`client.clear_cache()`, which reaches the BlueZ and ESPHome backends) and reconnects once; only the second miss counts as a failure. Nothing else clears that cache short of restarting HA, so any new setup step that touches a characteristic must stay inside that retry block.
- **Cooldown is the fallback signal, not a retry policy.** `connect_failure_threshold=1`, `connect_cooldown_seconds=120`: one real failure makes `is_usable` False for two minutes, `active_transport()` routes to MQTT, and HA's movement buttons go unavailable (they gate on `is_usable`). `BleakOutOfConnectionSlotsError` trips it immediately — an ESP32 proxy has only a few connection slots. Only a successful connect or `clear_ble_device()` resets the counter; a stream of advertisements does not.
- **`min_rssi=-90` gates usability too.** HA passes the advertisement RSSI with the device; below the floor the transport is unusable and sends fall back to MQTT. Expect availability to flap for a mower at the edge of a proxy's range.
- **Reconnects are never started from the disconnect callback** (`_on_disconnect_async` only clears state). The MQTT/BLE loops, user commands and fresh advertisements decide when to revive the link; doing it in the callback caused reconnect storms.
- **`establish_connection` runs with `timeout=2, max_attempts=1`.** That is deliberate for snappy manual control, but it also disables the retry connector's own service-change recovery (which only runs between its attempts), which is why the cache retry above lives in our code. Proxies often need more than 2 s to bring a link up; revisit if proxy users report connect timeouts.
- **habluetooth logs `Removing a non-existing connecting …`** when we tear a link down within milliseconds of connecting (the setup-failure path). It is slot accounting noise, not a fault to chase.
- **Diagnosing a BLE report:** ask for debug logs around the *first* disconnect (device-, proxy- or slot-originated?) and which proxy the reconnect went through; look for `BLE setup after connect failed`, `in cooldown`, `out of connection slots`, and the RSSI in the report frame (`connect.bleRssi`).

### Connection Paths

- **Cloud/MQTT (Aliyun, pre-2025):** `MammotionHTTP` login → `CloudIOTGateway` setup → `AliyunMQTTTransport`
- **Cloud/MQTT (Mammotion direct, post-2025):** `MammotionHTTP` login → `MQTTTransport` with JWT
- **Bluetooth:** `BLETransport` (bleak), usable standalone or alongside MQTT
- Device handles support multiple simultaneous transports; `_active_transport()` picks the best (MQTT default, BLE when `prefer_ble=True`)

### Commands and Device Types

Commands: `pymammotion/mammotion/commands/mammotion_command.py` and `messages/`.
HA-facing API: `pymammotion/homeassistant/mower_api.py`.
Device variants (25+): `pymammotion/utility/device_type.py` — `DeviceType.has_4g()`, `is_yuka()`, `is_rtk()`, etc.

## APK Reference Source

Decompiled APK source (Mammotion 2.3.18.21) is available at:
```
/home/michael/Downloads/Mammotion_2.3.18.21/com.agilexrobotics/java_src/com/agilexrobotics/
```

Decompiled APK source (Mammotion 2.3.8.201) is available at:
```
/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/
```

Key files for protocol/logic research:
- `mvp/fieldmower/device/HashDataManager.java` — map/hash/line/cover-path fetch logic, clearing conditions, retry logic
- `mvp/fieldmower/device/MACarDataManager.java` — incoming message parsing, device state callbacks, calls to HashDataManager
- `mvp/fieldmower/device/MACommandHelper.java` — outgoing command builders (field-mower variant)
- `command/MACommandHelper.java` — outgoing command builders (top-level variant)
- `proto/MctrlNav.java` — nav protobuf definitions
- `proto/MctrlSys.java` — sys/report protobuf definitions (device status, work report fields)

## Key Conventions

- **Async throughout:** All I/O uses `asyncio`/`async`/`await`
- **Line length:** 120 characters
- **Python version:** 3.12+
- **Type stubs** for missing third-party types are in `stubs/`
- Ruff excludes `pymammotion/proto/`, `tests/`, and `scripts/` from linting
- ty excludes `pymammotion/proto/**`, `tests/**`, `scripts/**`, and `examples/**`
- **No local imports inside function bodies** — always use top-level imports. Exception: `TYPE_CHECKING` guards for type-hint-only imports that would cause circular imports at runtime.
- **Walrus operator (`:=`)** — prefer it wherever it removes a separate assignment line: guards (`if x := foo()`), loop conditions (`while chunk := f.read()`), and inline captures inside comprehensions or `match` arms. Only avoid it when the binding would make the expression harder to read than two lines would.

## Working in this codebase (rules for Claude)

Before adding code, look for what's already there. The architecture is layered and most concerns already have a single home — duplicating logic in a second place is almost always wrong, even when it's "just a quick check."

**Search before you write:**
- Grep for the concept (`grep -rn "concept_name" pymammotion/`).
- Grep for the data shape you'd be checking (`mqtt_reported_offline`, `is_usable`, `is_connected`, `_prefer_ble`, …).
- Grep for similar patterns you'd be following (`grep -rn "active_transport\b"`, `watch_field`, `subscribe_unsolicited`, …).
- Read the existing implementation top-to-bottom before proposing a new one.

**Consolidate, don't proliferate.** If you find yourself writing the same check (offline gate, transport-usable test, mode classification, retry policy, …) in a second place, stop and look for the existing one. Examples currently in the codebase:
- "Is anything sendable right now?" → `DeviceHandle.has_usable_transport` / `active_transport()`. Don't add another offline check.
- "Is BLE in a usable state?" → `BLETransport.is_usable`. Don't re-derive from `_ble_device` and `_connect_cooldown_until`.
- "What kind of state is the mower in for cadence?" → `DeviceHandle._device_mode()` + `_MQTT_POLL_INTERVAL` / `_BLE_POLL_INTERVAL` tables. Don't pattern-match `sys_status` inline.
- "Should the queue treat this exception as expected?" → the demotion buckets in `DeviceCommandQueue._process` (`NoTransportAvailableError` / `DeviceOfflineException` are DEBUG; auth/saga/rate-limit are WARNING). Don't add a try/except in callers to swallow expected errors — let them propagate to the queue.

**SOLID, applied here:**
- **Single responsibility:** each file owns one concern. Transport selection lives on `DeviceHandle`; cooldown/scan logic lives on `BLETransport`; cadence tables live in `handle.py`. Don't smear logic across layers.
- **Open/closed:** prefer extending tables (e.g. `_MQTT_POLL_INTERVAL[mode]`) over adding `if mode == ...` branches in send paths.
- **Dependency direction:** `pymammotion` doesn't know HA exists. HA-Luba consumes `pymammotion` via the `MammotionClient` and `DeviceHandle` public APIs. If you find yourself reaching into `_private` attributes from HA-Luba, surface a public property instead.
- **Substitutability:** all `Transport` implementations satisfy the same interface. New default behavior goes on the *narrowest* base that needs it — `base.py` only if BLE genuinely has it too, otherwise `cloud.py`. Putting a broker concern on `Transport` is how BLE ended up inheriting a send quota, an auth-failure API and four `thing/*` callbacks it never used; giving BLE no-op stubs to keep one flat interface is the wrong repair (see `docs/decisions.md` D13).

**When proposing changes, lead with the audit.** "Where does this concern live today? Can the existing site cover the new requirement?" If the answer is yes, extend the existing site. If no, explain why a new site is needed and where it sits in the architecture before writing.

**When fixing bugs, fix the root, not the symptom.** If a check is missing in three places, the right fix is usually one centralized check (a property, a helper, a base-class method), not three copies. The `has_usable_transport` consolidation is the canonical example: one property replaced loose offline gates scattered across `send_command_with_args`, `_mqtt_activity_loop`, and the queue's warning bucket.

## Good practices

- When validation guarantees a dict key exists, prefer direct key access (`data["key"]`) instead of `.get("key")` so contract violations are surfaced instead of silently masked.
- Keep comments concise. Prefer one short line stating the non-obvious constraint, or no comment at all.
- Do not add comments that just restate the code on the following line(s) (e.g. `# Check if initialized` above `if self.initialized:`). Comments should only explain why (non-obvious constraints, surprising behavior, or workarounds), never what. Never add comments that justify a change by referencing what the code looked like before. Comments in tests that explain why a function call or assertion is made are ok.
- Do not add section or divider comments (e.g. `# --- XYZ Triggers ---`) inside or outside of functions, since those can easily become stale and be misleading.

## Testing (rules for Claude)

`docs/testing.md` is the testing constitution — layout, naming, doubles,
fixtures, time, regression contracts, legacy debt. Read it before writing or
editing anything under `tests/`. The rules below are the ones that most often
get broken; the document is the authority.

- **Tier by what it touches.** `tests/unit/` — one module, no sockets, no real
  clock, no `tests/fakeserver`. `tests/integration/` — several components, the
  fake cloud over loopback. `tests/live/` — real account or hardware, marked
  `live`, skips silently. A unit test that imports `tests.fakeserver` is an
  integration test in the wrong directory.
- **`tests/unit/` mirrors the package.** `pymammotion/device/handle.py` →
  `tests/unit/device/test_handle.py`. Split a module past ~600 lines by concern
  (`test_handle_transport_selection.py`), never by number.
- **A builder used by a second module moves to `_helpers.py`.** Package-local
  `tests/unit/<pkg>/_helpers.py` for `make_*` builders, `_fakes.py` for
  hand-written fakes, `tests/_helpers.py` across tiers, `tests/conftest.py`
  only for global autouse safety nets. Four copies of `_make_handle` is the
  failure this rule exists to stop.
- **Spec every mock; prefer not to mock.** Real object > hand-written fake >
  `create_autospec`/`MagicMock(spec=…)`. A bare `MagicMock()` answers every
  attribute truthily forever, so a renamed method keeps passing. Never mock the
  unit under test. Assert on outcomes, not on call plumbing — unless the call
  *is* the contract ("does not send to an offline device").
- **`await asyncio.sleep(0.15)` is not synchronisation.** Wait on an
  `asyncio.Event`, a future, `queue.join()`, or `asyncio.sleep(0)` for exactly
  one loop turn. Freeze the clock with `time_machine.travel(..., tick=False)`
  for anything reading `time()`/`monotonic()`. Bound every wait with
  `asyncio.wait_for`. `asyncio_mode = "auto"` — no `@pytest.mark.asyncio`.
- **A regression test must have been seen red.** Write it against the broken
  code, watch it fail, then fix. Mark it `@pytest.mark.regression`, name it for
  the behaviour (not the ticket), and let its docstring say what the code did
  wrong. It lives with the module it pins; only cross-module pins go in
  `tests/regression/`.
- **Every test you write gets reviewed.** Launch the `test-reviewer` agent over
  the tests you touched and fix its blocking findings before reporting the work
  complete. A `PostToolUse` hook queues the files and the `Stop` hook refuses
  the first stop while the queue is non-empty; the reviewer clears it. The
  author fixes — the reviewer does not rewrite.
- **`tests/meta/test_conventions.py` asserts the mechanical rules** and carries
  a frozen baseline of pre-existing offenders. The baseline may shrink, never
  grow: fix the violations your change touches and delete their entries.
