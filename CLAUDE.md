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

# Type checking (excludes proto/, tests/, scripts/, linkkit/)
uv run mypy pymammotion/

# Additional linting
uv run pylint pymammotion/

# Run pre-commit hooks on all files
uv run pre-commit run --all-files

# Run a single test file
uv run python tests/login_test.py

# Regenerate protobuf Python code from .proto files
uv run protoc -I=. --python_out=. --python_betterproto_out=. ./pymammotion/proto/*.proto

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
│  └─ MowPathSaga  (mow_path_saga.py)                      │
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
- mypy excludes `pymammotion/proto/`, `tests/`, `scripts/`, and `pymammotion/mqtt/linkkit/`
- Strict mypy config: `disallow_untyped_defs`, `disallow_untyped_calls`, `disallow_any_generics`
- **No local imports inside function bodies** — always use top-level imports. Exception: `TYPE_CHECKING` guards for type-hint-only imports that would cause circular imports at runtime.
