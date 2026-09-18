# Tasks and schedules

Mammotion devices store **schedule plans** (also called "tasks" / "jobs" — the app uses all
three interchangeably). The mower (Luba / Luba 2 / Yuka) and the Spino swimming-pool cleaner
use **different protobuf messages with similar but not identical semantics**. This doc is the
single source of truth for the wire format, the operations the device supports, and how the
APK decides when to (re-)fetch them.

Decompiled APK reference: `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/`.

---

## 1. Mower — `NavPlanJobSet`

Proto: `pymammotion/proto/__init__.py` `NavPlanJobSet` (38 fields).
Field path: `LubaMsg.nav.todev_planjob_set` (oneof `SubNavMsg`).
APK builders: `command/MACommandHelper.java`, `command/app/MACommandApiHelper.java`.

### 1.1 Operations and `sub_cmd`

`sub_cmd` (field 2, int32) selects the operation:

| Operation | `sub_cmd` | Required fields                                    | APK method                                                                 |
|-----------|-----------|----------------------------------------------------|-----------------------------------------------------------------------------|
| Read      | **2**     | `plan_index` (0..total_plan_num−1)                 | `readPlan(2, idx, logType)` (MACommandApiHelper:1171)                       |
| Create    | **1**     | full plan + **new** `plan_id`                      | `sendSchedule(plan)` with subCmd=1 (MACommandApiHelper:1461)                |
| Edit      | **4**     | full plan, existing `plan_id`                      | `sendSchedule(plan)` with subCmd=4                                          |
| Delete    | **3**     | `plan_id`                                           | `deletePlan(3, planId)` (MACommandApiHelper:562)                            |
| Rename    | **4**     | full plan with updated `task_name`                 | `reNameSchedule(...)` → `sendSchedule` (JobScheduleActivity:866)            |
| Enable/Disable | **4** | full plan with `reserved[2]` = 0/1                | `scheduleSwitch(...)` → `sendSchedule` (JobScheduleActivity:1342)           |
| Copy      | **1**     | clone + new `plan_id` + new `task_name`            | `editSchedule(true, cloned)` (JobScheduleActivity:227-230)                  |

`sub_cmd=0` ("NULL") is unused; values 5+ are unused on the mower.

### 1.2 `plan_id` generation

`plan_id` is a 21-character string: `<millis-timestamp>` (13 digits) + 8 random digits 0–8.
APK source: `BaseUtil.get21Random()` (`utils/BaseUtil.java:256-262`).

```text
"1622471234567" + "12345678"  →  "162247123456712345678"
```

Each operation that creates a new plan (`Create`, `Copy`) MUST generate a fresh `plan_id`.

### 1.3 The `reserved` field (8 bytes)

`reserved` is field 30 of `NavPlanJobSet`, declared `TYPE_STRING`. In practice it is an
**8-byte buffer encoded as a Python `str`** — all byte values are < 128 (ASCII-safe) so
`reserved.encode('latin-1')` round-trips losslessly. The APK constructs it as
`new String(byte[8])`.

Layout, decoded from `JobScheduleActivity.java:833-868` (rename) and `:1317-1344` (toggle):

| Index | Meaning                                  | Encoding                      |
|------:|------------------------------------------|-------------------------------|
| 0     | (unknown setting #1)                     | value + 10 on write, − 10 read|
| 1     | (unknown setting #2)                     | value + 10                    |
| **2** | **Enable flag**                           | **0 = disabled, 1 = enabled** |
| 3     | (unknown setting #3, likely edge mode)   | value + 10                    |
| 4     | (unknown setting #4, likely knife height)| value + 10                    |
| 5     | (unknown setting #5)                     | value + 10                    |
| 6     | (unknown setting #6)                     | value + 10                    |
| 7     | always 0 (null terminator)               | 0                             |

The exact meaning of bytes 0, 1, 3, 4, 5, 6 is not fully decoded. **For
enable/disable/rename/copy/edit operations, round-trip the stored `reserved` verbatim and
mutate only byte 2 (and `task_name`/`plan_id` outside the buffer).** This sidesteps the
uncertainty and matches what the APK does (it reads byte 2, rebuilds the buffer with the
other bytes preserved).

For full **create-from-scratch**, bytes 0, 1, 3, 4, 5, 6 must be derived from the plan's
explicit fields (`knife_height`, `edge_mode`, etc.) using the +10 offset. **The exact mapping
is unverified** — callers building a brand-new plan should capture an APK-issued create from
the real app via `scripts/frida/` or `scripts/mqtt_log.txt` to validate the bytes our builder
produces match the app's bytes for an equivalent plan definition.

### 1.4 Schedule recurrence

`trigger_type` (field 33, int32) drives recurrence semantics:

| `trigger_type` | Meaning  | Other fields consulted                                      |
|---------------:|----------|-------------------------------------------------------------|
| 0              | WEEK     | `weeks` (repeated int32 bitmask, 0=Sun … 6=Sat)             |
| 1              | DAY      | `day` (interval in days)                                    |
| 2              | DATE     | `start_date`, `end_date` (ISO `YYYY-MM-DD`)                 |
| 3              | RUN      | one-off, immediate                                          |

`start_time` / `end_time` are `HH:MM` strings. `week` (field 14) is legacy single-day; new
firmware uses the repeated `weeks` list.

### 1.5 Other useful fields

| Field                | Type      | Notes                                                   |
|----------------------|-----------|---------------------------------------------------------|
| `zone_hashs`         | repeated fixed64 | Area hashes selected for this job. Each hash matches a key in `device.map.area`. |
| `knife_height`       | int32     | Cutting height in mm.                                   |
| `speed`              | float     | Driving speed.                                           |
| `route_angle`        | int32     | Mowing pattern angle (0–179 degrees).                   |
| `route_spacing`      | int32     | Spacing between mow lines (cm).                          |
| `edge_mode`          | int32     | Edge handling (0/1/2 → off / once / twice).             |
| `ultrasonic_barrier` | int32     | Ultrasonic obstacle avoidance toggle.                   |

### 1.6 Starting a stored schedule on demand

"Start task" / "run schedule now" is a **separate proto message** from `NavPlanJobSet` —
it does not change the stored plan, it just triggers an immediate one-off run of it.

Proto: `NavPlanTaskExecute` (`pymammotion/proto/__init__.py`).
Field path: `LubaMsg.nav.plan_task_execute`.
APK builder: `MACommandHelper.singleSchedule(planId)` (`command/MACommandHelper.java:1673-1686`).

| Field      | Type   | Notes                                                         |
|------------|--------|---------------------------------------------------------------|
| `sub_cmd`  | int32  | `1` = execute the schedule with the given `id` (only value the APK sends) |
| `id`       | string | The `plan_id` of the stored schedule to run                   |
| `name`     | string | Populated by the device on the response                       |
| `result`   | int32  | Device's response code — `1` == success, anything else fails  |

pymammotion exposes this as `MammotionCommand.single_schedule(plan_id)`
(`navigation.py:247`), the HA-facing helper `MammotionMowerApi.start_task(...)`
(`mower_api.py:426`), and the HA-Luba coordinator method
`MammotionReportUpdateCoordinator.start_task(plan_id)`. The dynamic task-button
press triggers this; the same call is also reachable as the
`mammotion.start_task` HA service for use from automations.

**Boundary vs `NavTaskCtrl`** — `NavPlanTaskExecute` starts a *stored* schedule
by id. `NavTaskCtrl` (start/pause/resume/stop) drives the *currently running*
job regardless of how it was started. Don't confuse the two — sending
`NavTaskCtrl(action=1)` ("startJob") without a stored plan does not run a
schedule, it resumes whatever was last set.

**Worked example (mower):**

```python
# coordinator side: run an existing plan now.  The reducer's
# todev_planjob_set / plan_task_execute frames will arrive afterwards
# and surface the result via the state machine — no manual ack needed.
await coordinator.start_task(plan_id)
# pymammotion: send_order_msg_nav(
#     MctlNav(plan_task_execute=NavPlanTaskExecute(sub_cmd=1, id=plan_id))
# )
```

**Spino has no equivalent** — see § 2.6.

---

## 2. Spino (swimming-pool cleaner) — `spino_ctrl.PlanJobSet`

Proto: `pymammotion/proto/__init__.py` `PlanJobSet` (20 fields).
Field path: `LubaMsg.ctrl.plan_job_set` (oneof `LubaSubMsg`, **not** `LubaMsg.nav`).
APK builders: `command/app/MACommandApiHelper.java` — `*_SP` suffix (`sendSchedule_SP`,
`readPlan_SP`, `deletePlan_SP`).
APK envelope: `sendOrderSpino_Ctrl` → `MSG_CMD_TYPE_SPINO_CTRL` (MACommandApiHelper:342-345).

### 2.1 Operations and `cmd` (`PLAN_CMD` enum)

`cmd` (field 1, int32 — APK uses an `enum PLAN_CMD`, wire-compatible with int32):

| Operation     | `cmd` (`PLAN_CMD`) | Required fields                       | APK method                                                    |
|---------------|--------------------|---------------------------------------|---------------------------------------------------------------|
| Read          | **2** `QUERY`      | `planindex`                           | `readPlan_SP(2, idx, logType)` (MACommandApiHelper:1175)      |
| Create        | **1** `ADD`        | full plan + **new** `jobid`           | `sendSchedule_SP(plan)` with cmd=ADD (MACommandApiHelper:1465)|
| Edit          | **4** `EDIT`       | full plan, existing `jobid`           | `sendSchedule_SP(plan)` with cmd=EDIT                          |
| Delete        | **3** `DELETE`     | `jobid`                                | `deletePlan_SP(DELETE, jobid)` (MACommandApiHelper:566)       |
| Delete all    | **5** `DELETE_ALL` | —                                      | (no dedicated public method; cmd value defined)              |
| Rename        | `EDIT` (4)         | full plan with updated `jobname`      | (UI calls `sendSchedule_SP` with cmd=EDIT)                    |
| Enable/Disable| `EDIT` (4)         | `enable` field (see § 2.3)            | (UI calls `sendSchedule_SP` with cmd=EDIT)                    |
| Copy          | `ADD` (1)          | clone + new `jobid` + new `jobname`    | (UI calls `sendSchedule_SP` with cmd=ADD)                     |

`cmd=0` (`NULL`) is unused.

### 2.2 `jobid` is a **64-bit numeric ID** (not a string)

The APK uses `long jobId` and the proto declares `jobid = fixed64` (wire type 1). pymammotion's
local `spino_ctrl.proto` originally had `jobid` as `string` (wire type 2) — wire-incompatible —
and is now declared `fixed64 jobid = 13` (`pymammotion/proto/spino_ctrl.proto`), so Spino plan
commands are wire-compatible. Regenerate `*_pb2.py` if you touch the proto.

The APK does not document how new jobids are generated; the safe approach in Python is
`secrets.randbits(63) | 1` (avoid 0 and the high bit) at construction.

### 2.3 `enable` is INVERTED

`enable` (field 20, int32):

- `0` ⇒ the plan **is** enabled
- `1` ⇒ the plan **is** disabled

This is the opposite of intuition and the opposite of the mower's `reserved[2]`. Encode/decode
strictly at the wire boundary (the command builder and the reducer) so that the rest of the
Python codebase treats `PoolPlan.enabled: bool` in the natural sense (`True == enabled`).

Source: `MACommandApiHelper.java:1487` → `setEnable(!planJobSPBean.getEnabled() ? 1 : 0)`;
`PlanJobSPBean.java:332` → `this.enabled = proto.getEnable() == 0`.

### 2.4 Sub-modes are repeated

`sub_mode` (field 3) is a **repeated** `APP_WORK` list (not a single value) — used for
multi-stage cleaning (e.g. "floor then wall"). pymammotion's local `spino_ctrl.proto` originally
declared `sub_mode` as a single `int32`; it is now `repeated int32 sub_mode = 3`.

`work_mode` and `sub_mode` values mirror the `SpinoWorkMode` enum in
`pymammotion/data/model/pool_state.py` (RECHARGE=0, AUTO=1, FLOOR=2, WALL=3, ECO=4, LINE=5,
CUSTOM=6).

### 2.5 Recurrence

`triggertype` mirrors the mower's, with the same numbering (`PLAN_TYPE` enum: WEEK=0, DAY=1,
DATE=2, RUN=3). `weeks` is repeated int32, `day` is the day-interval, `startdate` / `enddate`
are ISO strings.

### 2.6 No "start schedule now" command

The Spino has **no analogue of `NavPlanTaskExecute`** (verified across the entire APK).
Stored schedules run automatically at their scheduled time; the firmware does not expose a
"run schedule #N immediately" command.

The closest thing the app does is start a **fresh live cleaning session** independent of any
stored schedule, via `MctlSys.set_work_mode` (proto `WorkModeT`):

```python
# pymammotion / HA-Luba — starts a live session in AUTO mode now.
# Does NOT reference any stored PoolPlan.
await coordinator.async_set_work_mode(SpinoWorkMode.AUTO.value)
# wire: MctlSys(set_work_mode=WorkModeT(work_mode=1))
```

APK reference: `DeviceStateSwimmingPoolSPFragment.startPC210SwimmingConmand`
(`home/viewmodel/HomeStateViewModule.java:1171`) →
`MACommandApiHelper.sendSwtichSwimmingSPWorkModule`
(`command/app/MACommandApiHelper.java:1540`).

Because of this, the HA `mammotion.start_task` service raises a translated error
(`start_task_unsupported_on_spino`) when targeted at a Spino task button rather than silently
no-op'ing — users should target the Spino vacuum entity's standard `vacuum.start` (which
hits `set_work_mode`) instead.

---

## 3. Fetch flow — the same shape for both devices

Neither device exposes a bulk "get all plans" request. The fetch is always a **loop over
`plan_index`**:

1. Send `read_plan(sub_cmd=2 or cmd=QUERY, plan_index=0)`.
2. Read the response; its `total_plan_num` (field 23 mower / field 7 Spino) tells you how
   many plans exist.
3. For `idx` in `1..total_plan_num−1`, send `read_plan(... plan_index=idx)` and collect the
   per-index response.
4. Stop. Each response is a full plan record.

pymammotion implements this loop for the **mower** in `PlanFetchSaga`
(`pymammotion/messaging/plan_saga.py`), enqueued via `MammotionClient.start_plan_sync(name)`.
The Spino equivalent is `SpinoPlanFetchSaga` (`pymammotion/messaging/spino_plan_saga.py`),
enqueued via `start_spino_plan_sync(name)`. Both saga loops `read_plan(plan_index=0)` →
read `total` → request `1..total−1`, with `max_attempts=3`, `step_timeout=2.0`.

The APK uses the same loop with a **50 ms delay between requests**
(`HomeStateViewModule.java:136-209`) — pymammotion's saga relies on the broker's
response-then-request ordering and doesn't need an explicit delay.

**Response correlation (oneof leaf field).** The Mammotion protocol has no request ID; each
reply is matched by its protobuf `oneof` field name — the broker's standard pattern. Plans are
no exception:

| Device | Request builder        | Reply leaf field                 | Decoded via                                  |
|--------|------------------------|----------------------------------|----------------------------------------------|
| Mower  | `read_plan(...)`       | `nav.todev_planjob_set`          | `which_one_of(response.nav, "SubNavMsg")`    |
| Spino  | `read_spino_plan(...)` | `ctrl.plan_job_set` (`SpinoCtrl`)| custom `_collect_frames` on `LubaMsg.ctrl`   |

The Spino reply rides the `ctrl` envelope, **not** `nav`, so `SpinoPlanFetchSaga` overrides
`_collect_frames`/`_extract_plan_job_set` to dispatch on `LubaMsg.ctrl.plan_job_set` instead of
the default `nav` path. This matches the APK, which builds Spino plans under `SpinoCtrl`
(`command/MACommandHelper.java` `sendSchedule_SP`) and mower plans under `MctlNav`.

### 3.1 What triggers a fetch?

| Trigger                                          | Mower                                                                | Spino                              |
|--------------------------------------------------|----------------------------------------------------------------------|------------------------------------|
| First connection / setup                         | HA polling layer issues `read_plan` on the first `update()`          | `MammotionSpinoCoordinator._async_setup` calls `start_spino_plan_sync` |
| Periodic re-poll                                 | `mower_api.py:95-98` — every 10 min OR if `len(map.plan) != total_plan_num` | Same condition adapted to `device.plans` |
| After area/zone delete (APK only)                | APK calls `readPlan(2, 0, 0)` (`AreaDBHelper.java:747`)              | n/a                                |
| Device reports new IDs we don't have             | Mower-only: unsolicited `all_plan_task` (id+name pairs) flips `device.map.plans_stale = True` (`state_reducer.py:343-351`); polling layer notices the mismatch on the next tick | n/a — Spino has no `all_plan_task` analogue |

### 3.2 `plans_stale` lifecycle

Set: `state_reducer.py:343-351` when a fresh `all_plan_task` frame contains IDs not present in
`device.map.plan`.
Consumed: `mower_api.py:95-98` triggers a re-fetch on the next polling tick.
Cleared: **currently never explicitly cleared in pymammotion** — relies on the count-equality
condition naturally going false after the saga populates `map.plan`. This is a small wart
worth noting for future cleanup but does not cause re-fetch storms (the count condition gates
it).

### 3.3 Keeping the device synced during the loop

The device drops out of its "synced" state ~10 s after the last `todev_ble_sync` and then
stops responding to commands (see `docs/apk_timers_and_loops.md` and
`pymammotion/device/ble_loop.py`). A plan fetch can outlast that window
(`step_timeout=2.0` × up to 3 attempts per index × N plans).

The plan sagas **deliberately do not** send their own `todev_ble_sync` before each read — and
**neither does the APK** before each `readPlan`. The APK keeps the link alive with its
connection-level sync (`sendInitBTDataSync(2)`, 3× retry) plus the ~1.5 s background heartbeat,
not a per-request sync. pymammotion mirrors this with the device-level keep-alive that runs
independently of the saga:

* **BLE** — `ble_loop.ble_activity_loop` sends `todev_ble_sync(2)` every 5 s.
* **MQTT** — `DeviceHandle._send_marked` re-syncs (`todev_ble_sync(3)`, quota-free heartbeat)
  before any send when it has been > `_MQTT_SYNC_INTERVAL` (7 s) since the last sync — debounced
  against the last *sync*, not the last command. Every per-index `read_plan` the saga emits
  therefore goes out behind a fresh sync once the window has lapsed.

This is why the plan sagas omit the explicit per-request sync that `MapFetchSaga` and
`MowPathSaga` carry: a plan read is a single request/response, so the device-level gate is
sufficient. Map/cover-path steps are multi-frame and historically lost frames mid-step
(no `toapp_gethash_ack`), so those sagas add a belt-and-suspenders `_send_ble_sync` immediately
before each major request on top of the same device-level keep-alive.

### 3.4 After a write, is the device's reply enough?

Yes for the mower: `Create`/`Edit`/`Delete` responses come back as `todev_planjob_set` frames
(or a `result` ack inside one) and the reducer (`state_reducer.py:340-342`) upserts the
updated plan into `device.map.plan`. No explicit re-fetch is needed unless the response is
missed.

For Spino: the reducer (`state_reducer.py`, `_update_plan_job_set`) mirrors this — it upserts
into `device.plans` on each `plan_job_set` frame. After `DELETE_ALL` (no `total_plan_num` echo
to disambiguate), the caller should issue an explicit refresh.

---

## 4. Worked examples

### 4.1 Mower: toggle enable on an existing plan

```python
# coordinator side: round-trip the stored plan, mutate only reserved[2]
plan = coordinator.data.map.plan[plan_id]
await coordinator.async_send_command(
    "enable_plan", plan=plan, enabled=False,
)
# pymammotion side:
#   modified = plan.with_enabled(False)          # mutates reserved[2] = 0
#   modified.sub_cmd = 4                          # EDIT
#   bytes_ = command.send_schedule(modified)      # full NavPlanJobSet on the wire
```

### 4.2 Mower: rename

```python
plan = coordinator.data.map.plan[plan_id]
await coordinator.async_send_command(
    "rename_plan", plan=plan, new_name="Front lawn",
)
# pymammotion: plan.with_renamed("Front lawn") with sub_cmd=4, sent via send_schedule.
```

### 4.3 Mower: copy

```python
existing_names = {p.task_name for p in coordinator.data.map.plan.values()}
copy_name = make_copy_name(existing_names)          # "Copy-1", "Copy-2", …
await coordinator.async_send_command(
    "copy_plan", plan=existing_plan, new_name=copy_name,
)
# pymammotion:
#   clone = dataclass.replace(existing_plan,
#                             plan_id=new_mower_plan_id(),
#                             task_name=copy_name,
#                             sub_cmd=1)
#   send_schedule(clone)
```

### 4.4 Spino: toggle enable

```python
plan = coordinator.data.plans[jobid]
await coordinator.async_send_command(
    "enable_spino_plan", plan=plan, enabled=False,
)
# pymammotion:
#   modified = plan.with_enabled(False)            # PoolPlan.enabled is a normal bool
#   wire_proto.enable = 0 if modified.enabled else 1   # INVERT at the boundary
#   send via cmd=4 (EDIT)
```

### 4.5 Spino: delete

```python
await coordinator.async_send_command(
    "delete_spino_plan", jobid=plan.jobid,
)
# pymammotion: PlanJobSet(cmd=3, jobid=jobid), wrapped in SpinoCtrl, sent as MSG_CMD_TYPE_SPINO_CTRL.
```

---

## 5. Known unknowns

1. **Mower `reserved` bytes 0, 1, 3, 4, 5, 6** — the +10-offset values are confirmed but their
   field meanings are inferred (likely knife_height / edge_mode / channel mode / etc.).
   Validate by capturing the wire frames the official app produces for a known plan via
   `scripts/frida/` or `scripts/mqtt_log.txt`.
2. **Spino `jobid` generation** — the APK uses `long` but doesn't expose a canonical generator
   in the decompiled source we've inspected. Python uses `secrets.randbits(63) | 1`; if the
   device validates a specific format (e.g. timestamp-based, like the mower), capture and
   adjust.
3. **Spino `result` codes** — both protos have a `result` field returned by the device. The
   mower's success code is `0`; non-zero values are not catalogued. Capture and document as
   they're observed.
4. **`plans_stale` is never explicitly cleared** in pymammotion (§ 3.2). Not a bug today
   because the count-equality re-fetch gate makes it self-resolving, but worth a small follow-up
   to clear it at the end of `PlanFetchSaga` / `SpinoPlanFetchSaga`.
