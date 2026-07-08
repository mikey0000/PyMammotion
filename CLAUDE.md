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
│  force_refresh() re-checks all active credential types   │
│  ReLoginRequiredError raised on unrecoverable failure    │
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

**TokenManager** holds a single `asyncio.Lock` to prevent concurrent refresh races. All three getters (`get_valid_http_token`, `get_aliyun_credentials`, `get_mammotion_mqtt_credentials`) check expiry under the lock and refresh proactively. `force_refresh()` is the watchdog entry point when `AuthError` is detected.

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
