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
./bin/bumpver update --patch
```

## Architecture

The refactored architecture is a **layered, composable system** replacing the earlier monolithic god-object pattern.

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
│  ├─ AliyunMQTTTransport  (aliyun_mqtt.py)                │
│  │   pre-2025 devices; HMAC-SHA1, paho-mqtt, port 8883  │
│  ├─ MQTTTransport  (mqtt.py)                             │
│  │   post-2025 devices; aiomqtt, JWT password            │
│  │   send() raises AuthError on HTTP 401/460             │
│  └─ BLETransport  (ble.py)                               │
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

**Cloud error codes live in one table.** `pymammotion/aliyun/exceptions.py` holds `DEVICE_OFFLINE_CODES`, `DEVICE_UNBOUND_CODES`, `GATEWAY_TIMEOUT_CODES` (plus the pairing-flow codes, currently unused). Both cloud send paths — `CloudIOTGateway.send_cloud_command` and `MQTTTransport._invoke` — classify against them, so a newly-observed code is added once. Don't pattern-match a raw code inline in a send path.

**Never send MQTT to an offline device.** When the cloud has reported a device offline (`DeviceAvailability.mqtt_reported_offline = True`, set by `DeviceOfflineException` and "offline" `thing/status` messages), no code path should fire an MQTT send to that device — not user commands, not periodic polls, not heartbeats, not sagas. The cloud will queue the message and either drop it or deliver it when the device returns, neither of which we want, and the broker side raises `DeviceOfflineException` again, so the round-trip is wasted. Gates that enforce this:
- `DeviceHandle.active_transport()` raises `NoTransportAvailableError` when MQTT is the only registered transport and `mqtt_reported_offline` is True.
- `DeviceHandle._mqtt_activity_loop` pre-flights `active_transport()` and skips when it raises.
- `MammotionClient.send_command_with_args` short-circuits with a debug log when offline-and-no-BLE.
- `mqtt_reported_offline` clears automatically as soon as any MQTT frame arrives via `on_raw_message`, so no manual reset is needed — natural device traffic re-arms sending. Any new send path you add must follow the same gate, or route via `send_raw` / `send_command_with_args` which already check it.

### Connection Paths

- **Cloud/MQTT (Aliyun, pre-2025):** `MammotionHTTP` login → `CloudIOTGateway` setup → `AliyunMQTTTransport`
- **Cloud/MQTT (Mammotion direct, post-2025):** `MammotionHTTP` login → `MQTTTransport` with JWT
- **Bluetooth:** `BLETransport` (bleak), usable standalone or alongside MQTT
- Device handles support multiple simultaneous transports; `_active_transport()` picks the best (MQTT default, BLE when `prefer_ble=True`)

### Commands and Device Types

Commands: `pymammotion/mammotion/commands/mammotion_command.py` and `messages/`.
HA-facing API: `pymammotion/homeassistant/mower_api.py` and `rtk_api.py`.
Device variants (25+): `pymammotion/utility/device_type.py` — `DeviceType.has_4g()`, `is_yuka()`, `is_rtk()`, etc.

## APK Reference Source

Decompiled APK source (Mammotion 2.2.4.13) is available at:
```
/home/michael/Downloads/Mammotion_2.2.4.13_APKPure/com.agilexrobotics/java_src/com/agilexrobotics/
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
- **Substitutability:** all `Transport` implementations satisfy the same interface. New default behavior goes on the base class (`base.py`); overrides go on the concrete class.

**When proposing changes, lead with the audit.** "Where does this concern live today? Can the existing site cover the new requirement?" If the answer is yes, extend the existing site. If no, explain why a new site is needed and where it sits in the architecture before writing.

**When fixing bugs, fix the root, not the symptom.** If a check is missing in three places, the right fix is usually one centralized check (a property, a helper, a base-class method), not three copies. The `has_usable_transport` consolidation is the canonical example: one property replaced loose offline gates scattered across `send_command_with_args`, `_mqtt_activity_loop`, and the queue's warning bucket.
