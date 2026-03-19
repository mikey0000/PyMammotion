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

### Connection Paths

The library supports three connection modes that can be used independently or together:

- **Cloud/MQTT:** `MammotionHTTP` (login + device discovery) → `AliyunMQTT` (real-time control via Alibaba Cloud IoT)
- **Bluetooth:** `MammotionBLE` (BLE scanner + GATT client via `bleak`)
- **Hybrid:** `MammotionMQTT` (direct MQTT without Aliyun gateway)

### Device Manager Hierarchy

```
MammotionDeviceManager          # top-level, holds all devices
├── MammotionMowerDeviceManager[]
│   ├── cloud: MammotionCloud   # MQTT + HTTP path
│   └── ble: MammotionMowerBLEDevice
└── MammotionRTKDeviceManager[]
    ├── cloud: MammotionCloud
    └── ble: MammotionRTKBLEDevice
```

Key files: `pymammotion/mammotion/devices/mammotion.py`, `mower_manager.py`, `rtk_manager.py`

### State Management

`MowerStateManager` (`pymammotion/data/mower_state_manager.py`) is the central hub. `MowingDevice` and `RTKDevice` wrap `betterproto2` dataclasses and use `mashumaro` with `orjson` for JSON serialization.

### Protocol Stack

- **HTTP** (`pymammotion/http/`): Login, JWT auth, device listing
- **Protobuf** (`pymammotion/proto/`): Binary protocol for device commands/state (auto-generated, do not edit manually)
- **MQTT** (`pymammotion/mqtt/`, `pymammotion/aliyun/`): Real-time comms via Alibaba Cloud IoT (paho-mqtt)
- **BLE** (`pymammotion/bluetooth/`): Direct device control via `bleak`/`bleak-retry-connector`
- **WebRTC** (`pymammotion/agora/`): Video streaming via Agora SDK + websockets

### Commands

Commands live in `pymammotion/mammotion/commands/mammotion_command.py` and `messages/`. The Home Assistant-facing API is in `pymammotion/homeassistant/mower_api.py` and `rtk_api.py`.

### Device Types

`pymammotion/utility/device_type.py` defines 25+ device variants (Luba 1, Luba 2/VS, Yuka, Yuka Mini, RTK, Spino, pool cleaners). Device capability detection uses methods like `DeviceType.has_4g()`, `is_yuka()`, `is_rtk()`.

## Key Conventions

- **Async throughout:** All I/O uses `asyncio`/`async`/`await`
- **Line length:** 120 characters
- **Python version:** 3.12+
- **Type stubs** for missing third-party types are in `stubs/`
- Ruff excludes `pymammotion/proto/`, `tests/`, and `scripts/` from linting
- mypy excludes `pymammotion/proto/`, `tests/`, `scripts/`, and `pymammotion/mqtt/linkkit/`
- Strict mypy config: `disallow_untyped_defs`, `disallow_untyped_calls`, `disallow_any_generics`
