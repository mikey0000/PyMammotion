# Backlog

Known structural debt, re-verified against the tree on 2026-09-22. Everything
here is open; fixed items are deleted rather than struck through. Rationale for
the shape of the code is in `docs/decisions.md`; this file is only what remains
to do. Re-check an item against the code before acting on it.

## Structure

- **`DeviceHandle` is the last god object** (`device/handle.py`, ~2400 lines).
  Two cohesive blocks could leave on their own terms: the report-stream
  start/keep/stop state machine (`request_report_snapshot`,
  `start_report_stream`, `_send_rpt_start_verified`, `send_report_stream_keep`,
  `send_one_shot_report`, `request_reports`, `_wait_for_report_data`, …) against
  the existing `LoopHost` port, and the subscription plumbing (`_DebouncedBus`
  plus the `subscribe_*` / `watch_field` methods). Do the report stream first.
- **`DeviceRegistry` lives at the bottom of `handle.py`.** Its sibling
  `AccountRegistry` has `account/registry.py`; anything needing a device lookup
  imports the whole handle module. Move it to `device/registry.py`.
- **`client.py` is ~2300 lines.** Six saga entry points open with the same
  `get_by_name` / warn / return block; extract `_require_handle(name, caller)`.
  `start_plan_sync` and `start_spino_plan_sync` are near-identical.

## Correctness

- **`send_command_with_args` is stringly typed.** `key` is resolved with
  `getattr` on the command builder, so a renamed builder breaks HA silently as
  an `AttributeError` inside a queue task. Constrain `key` to a `Literal[...]`
  derived from `MammotionCommand`'s public methods.
- **`DeviceRegistry.get` / `unregister` change meaning by arity.**
  `get(account_id, device_id)` is an exact key; `get(device_id)` searches across
  accounts through a parameter still named `account_id`. This already produced
  one bug (`connect_ble` passing a device name into the account slot). Split into
  `get` and an explicit `get_any_account`.
- **Nested walrus in `DeviceConfig.get_device_config`**
  (`data/model/device_capabilities.py`): the inner assignment is dead and an
  empty-dict config reads as "not found". Write it as two lines.
- **Sagas clear `self.result` inside `_run`**, so a consumer can read a stale
  result before the run starts. Reset in `__init__` or a `reset()` the queue calls.
- **`Saga.device_name` has two spellings.** The base has a class attribute
  defaulting to `""`; `map_saga`, `mow_path_saga` and `command_queue` use
  `self._device_name`; `svg_saga` uses `self.device_name`; the other sagas set
  neither, so their log lines carry an empty name.
- **`step_timeout` / `total_timeout` are class constants** with no per-instance
  override. Accept them in `Saga.__init__` for slow-network devices.
- **`skip_if_saga_active` is checked outside the lock** that guards saga
  lifecycle in `command_queue.py`. Low frequency, benign either way.
- **Log hygiene:** `_logger.warning(ex)` in `client.py` logs a bare exception;
  `token_manager.py` builds auth error messages with `str(exc)` five times,
  losing the type (`f"{type(exc).__name__}: {exc}"`).
- **Dynamics line, manual path:** `MammotionClient.get_dynamics_line` has no
  `is_support_dynamics_line` gate (the loop that replaced its polling role has
  one), its docstring says the APK enforces a 1 s gap when the APK uses 3000 ms
  and this path enforces none, and nothing clears `device.map.dynamics_line`
  when the device leaves `MODE_WORKING` — the APK drops it on that transition.

## Public surface and dead code

- **`__all__` exports the legacy BLE stack.** `pymammotion/__init__.py` lists
  `MammotionBLE` (`bluetooth/ble.py`, a standalone bleak wrapper used only by
  two examples, disjoint from `transport/ble.py`) and not `MammotionClient`.
  Coordinate the change with HA-Luba.
- **`pymammotion/event/`** defines `Event`, `MoveEvent`, `DataEvent` with no
  consumers; only `BleNotificationEvent` is used, by the legacy stack above.
  The live mechanism is `transport/base.py`'s `EventBus`. Delete with it.
- **Dead modules** with zero consumers in the package: `mammotion/control.py`
  (joystick), `utility/rocker_util.py`, `utility/movement.py`,
  `data/model/raw_data.py`, `data/model/account.py`. The joystick chain is why
  `pyjoystick` and `nest-asyncio` sit in the `extras` group;
  `examples/test_control.py` imports a package path that no longer exists.
  `data/model/mowing_modes.py` looks dead but `DetectionStrategy.for_device` is
  a documented firmware gate HA calls directly — keep it and say so in its
  docstring.
- **`device_capabilities.py` is ~2600 lines, mostly literal data.** It belongs
  in `pymammotion/resources/` as JSON, schema-validated. `docs/capabilities/`
  now holds the raw `product_params` dumps the table derives from.
- **Three modules named for the same idea:** `data/model/device_config.py`
  (`OperationSettings`), `data/model/device_capabilities.py` (`DeviceConfig`)
  and the `utility/device_config.py` shim. Rename the first to
  `operation_settings.py`.

## Tooling

- **CI lints changed files only** (`on-push.yml` passes a changed-file list to
  `ruff`). A newly enabled rule or a renamed file is never swept; the full path
  passes today, so switching costs nothing.
- **CI never runs `ty`.** It is a pre-commit-only gate; add
  `uv run ty check pymammotion/` to the build job.
- **`ty` type-checks against 3.12** (`[tool.ty.environment] python-version`)
  for a package that requires 3.13. Set it to `3.13`.
- **No `pytest-timeout` default.** `tests/fakeserver` binds real sockets, so a
  test awaiting a message the fake never sends hangs the run instead of failing.
  `timeout = 60` in `[tool.pytest.ini_options]` is cheap insurance.
- **Repo-root clutter:** untracked capture logs (`output.txt`, `*_L2.txt`,
  `online_notification.txt`), `t`, `bytes.py`, `areas.json`, and three
  `*test*.py` scripts outside `tests/`. Move what is worth keeping into
  `examples/` or `tests/`; gitignore the rest.
- **`pyproject.toml` carries an inert `[tool.setuptools.package-data]`** (the
  backend is hatchling) and there is a stray `py.typed` at the repo root beside
  the real `pymammotion/py.typed`.
