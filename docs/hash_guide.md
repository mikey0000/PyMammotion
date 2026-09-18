# Mammotion Hash Types Guide

This document explains the hash IDs exchanged between the app and the device
during map synchronisation. Each hash is a 64-bit integer that uniquely
identifies a chunk of persistent data stored on the device.

---

## bol_hash (boundary list hash)

**What it is:** A MurMur hash of the concatenated `area_root_hashlist` — the
ordered list of all root-level area boundary hashes.

**Source:** `toapp_report_data` → `locations[]` → `bol_hash` field.

**How it is used:** Every `toapp_report_data` message includes the current
`bol_hash`.  The app compares it against a locally computed hash of its cached
`area_root_hashlist`.  A mismatch means the map has changed since the last sync
(new area added, area edited/deleted) and a full `MapFetchSaga` must be run.

**Code reference:** `HashList.invalidate_maps(bol_hash)` in
`pymammotion/data/model/hash_list.py`.

---

## ub_zone_hash (uploaded zone hash)

**What it is:** The device's own MurMur hash of all zone/area data currently
stored in its persistent memory.  Sent in every `toapp_report_data` →
`work.ub_zone_hash`.

**"ub" prefix:** stands for "upload buffer" — the hash covers what the device
has committed to its internal flash storage.

**How the APK uses it:** `HashDataManager` maintains a local `bolHash` (its
own MurMur hash of all synced zone hashes from the local database).  On each
report it compares `local_bolHash != ub_zone_hash`.  A mismatch triggers
`getAllBoundaryHashList(sub_cmd=0)` — the same zone re-sync that `bol_hash`
triggers.  The two checks are complementary: `bol_hash` verifies the root hash
list structure; `ub_zone_hash` verifies the full zone content.

**Real-world values seen:**

```
work.ub_zone_hash: 9020024042630121170   # during active mowing
work.ub_zone_hash: 7112427778541378167   # Luba 1 at rest
```

**Suggested check:** If `ub_zone_hash` changes between two consecutive
`toapp_report_data` messages (transitions to a new non-zero value), the device
has modified its zone data on-device and a `MapFetchSaga` should be triggered.
Unlike `bol_hash` we cannot locally re-compute `ub_zone_hash`, so transition
detection is the practical approach.

---

## ub_path_hash (uploaded path hash)

**What it is:** The device's MurMur hash of all recorded travel-path / mowing-
line data currently in its persistent memory.  Sent in `toapp_report_data` →
`work.ub_path_hash`.

**How the APK uses it:** `HashDataManager.mPathHash` tracks the last-seen
value.  When `mPathHash != ub_path_hash` (and zone data is in sync) the APK
calls `getLineHashList(sub_cmd=1)` to re-fetch all stored path segments.  This
covers recorded paths (type 2) used by Luba 1 path-mode mowing.

**Real-world value:**

```
work.ub_path_hash: 1623055749216062189
```

**Suggested check:** If `ub_path_hash` changes, path data is stale and a
re-sync of `HashList.path` entries is warranted.  The APK only triggers this
when zone data is already confirmed in sync (so the two checks are sequential,
not parallel).

---

## ub_ecode_hash (uploaded error-code / e-code hash)

**What it is:** A hash covering the device's current error-code configuration
or extended diagnostic state.  Sent in `toapp_report_data` → `work.ub_ecode_hash`.

**"ecode":** stands for error-code (the device's internal fault/event log
structure that it can upload to the cloud).

**How the APK uses it:** Not used for any detected map-sync trigger in the APK
source analysed.  Likely used by the cloud diagnostic pipeline to detect when
the device has new error events to upload.  Can be treated as informational for
now.

**Real-world value:**

```
work.ub_ecode_hash: 2802447217087617234
```

---

## init_cfg_hash (initialisation configuration hash)

**What it is:** A hash of the device's initialisation / boot configuration
block.  Stable across reboots; changes when firmware is updated or the device
is factory-reset.  Sent in `toapp_report_data` → `work.init_cfg_hash`.

**How it is used:** The APK can detect firmware updates or configuration resets
by watching for a change in this value.  Not used for map-sync triggering.

**Real-world values:**

```
work.init_cfg_hash: 9134504257019276730   # Yuka Mini 600
work.init_cfg_hash: 8537412012428359726   # Luba 1
```

---

## bp_hash (break-point hash)

**What it is:** Hash of the device's "break-point" (resume-position) record —
the last saved position + job state that allows the mower to resume after an
interruption.  Sent in `toapp_report_data` → `work.bp_hash`.

**How it is used:** The APK stores this alongside `bp_info`, `bp_pos_x`, and
`bp_pos_y` to offer the user a "resume mowing" option.  When `bp_hash`
is non-zero a valid break-point exists.

**Real-world value:**

```
work.bp_hash: 2569571509620940977
```

---

## path_hash (active route plan hash)

**Two usages — do not confuse:**

### 1. In `bidire_reqconver_path` (route planning)

`bidire_reqconver_path.path_hash` is the hash of the navigation route plan
that the device just computed.  This is non-zero while a mow plan is active
and returns to 0 when the job ends or is cancelled.

- Transition `0 → non-zero`: device has a computed route; fetch the cover path
  via `MowPathSaga(skip_planning=True)`.
- Transition `non-zero → 0`: job ended; clear `current_mow_path` and
  `generated_mow_path_geojson`.

**Code reference:** `StateReducer._update_nav_data` `bidire_reqconver_path`
case; `HomeAssistantMowerApi.setup_device_watchers`.

**Real-world value:**

```
bidire_reqconver_path.path_hash: 7020285182841243984
```

### 2. In `rpt_work` (work report)

`work.path_hash` in `toapp_report_data` reflects the current job's route-plan
hash.  Non-zero while a job is active.  Can be used as a secondary indicator
that a route plan exists on the device, but `bidire_reqconver_path.path_hash`
is the authoritative signal for `MowPathSaga` triggering.

---

## Area hashes (type 0)

**What they are:** Each bounded mowing area (zone) has one hash ID.

**How they are stored:** `HashList.area: dict[int, FrameList]` — mapping from
hash ID to a list of coordinate frames that make up the area boundary polygon.

**Fetched by:** `synchronize_hash_data(hash_num=<area_hash>)` during
`MapFetchSaga` step 4.

---

## Obstacle hashes (type 1)

**What they are:** Each obstacle (keep-out zone, no-go area) drawn on the map
has one hash ID.

**How they are stored:** `HashList.obstacle: dict[int, FrameList]`

**Fetched by:** Same as area hashes — `synchronize_hash_data` during
`MapFetchSaga`.

---

## Path hashes (type 2)

**What they are:** Recorded travel paths (used for path-mode mowing on Luba 1).

**How they are stored:** `HashList.path: dict[int, FrameList]`

**Staleness indicator:** `ub_path_hash` (see above).

---

## Line hashes / cover path hashes (sub_cmd=3)

**What they are:** After calling `generate_route_information` the device
computes the optimal mowing coverage lines (the zigzag/grid pattern).  Each
line segment group is assigned a hash ID.  These are the hashes you need to
download to display the planned mow path overlay in the app.

**How they are obtained:**
1. Send `get_all_boundary_hash_list(sub_cmd=3)`.
2. Device replies with `toapp_gethash_ack` frames containing the line hash list.
3. Call `get_line_info_list(line_hashs, transaction_id)`.
4. Device pushes `cover_path_upload` frames which form the drawable path.

**Code reference:** `MowPathSaga` in
`pymammotion/messaging/mow_path_saga.py`, `HashList.current_mow_path`.

**Trigger:** When `device.work.path_hash` transitions from 0 to non-zero and
`device.work.job_id` changes, a new mow plan is active.  `HomeAssistantMowerApi`
auto-triggers `MowPathSaga(skip_planning=True)` to fetch the path for display.

**Cleared:** When `bidire_reqconver_path.path_hash == 0` the device signals that
the job has ended.  `StateReducer` automatically clears
`device.map.current_mow_path` and `device.map.generated_mow_path_geojson`.

---

## Dump hashes (type 12)

**What they are:** Dump/clippings-collection zone boundaries (used on models
with a grass catcher).

**How they are stored:** `HashList.dump: dict[int, FrameList]`

---

## SVG hashes (type 13)

**What they are:** Pre-rendered SVG map tiles sent by the device.  Used to
display a raster overview of the map without rendering each boundary polygon
client-side.

**How they are stored:** `HashList.svg: dict[int, SvgMessage]`

**Fetched by:** `MapFetchSaga` handles `toapp_svg_msg` responses alongside
`toapp_get_commondata_ack`.

---

## Visual safety zone hashes (type 25)

**What they are:** Visual-camera-detected safety zones (Luba 2 Vision / Pro
models only).  Areas the vision system has identified as hazardous.

**How they are stored:** `HashList.visual_safety_zone: dict[int, FrameList]`

---

## Visual obstacle zone hashes (type 26)

**What they are:** Visual-camera-detected obstacles (Luba 2 Vision / Pro only).
Dynamic or static obstacles detected by the onboard camera.

**How they are stored:** `HashList.visual_obstacle_zone: dict[int, FrameList]`

---

## Plan hashes

**What they are:** Scheduled job plans (recurring mow schedules, with zone
selection and timing).  Stored separately from map geometry.

**How they are stored:** `HashList.plan: dict[int, Plan]`

**Fetched by:** `read_plan` command (`sub_cmd=2, plan_index=0`) — not via
`MapFetchSaga`.  Device replies with `todev_planjob_set` messages.

---

## Integrity check summary

| Hash field | Source message | What it covers | Triggers |
|---|---|---|---|
| `bol_hash` | `locations[]` in `toapp_report_data` | Root area hash list | `MapFetchSaga` (implemented) |
| `ub_zone_hash` | `work` in `toapp_report_data` | All zone data on-device | `MapFetchSaga` (on change, suggested) |
| `ub_path_hash` | `work` in `toapp_report_data` | All path/line data on-device | Path re-sync (on change, suggested) |
| `ub_ecode_hash` | `work` in `toapp_report_data` | Error-code log | Cloud diagnostic (informational) |
| `init_cfg_hash` | `work` in `toapp_report_data` | Boot/firmware config | Firmware-change detection (informational) |
| `bp_hash` | `work` in `toapp_report_data` | Break-point resume state | "Resume mowing" UI indicator |
| `path_hash` | `bidire_reqconver_path` | Active route plan | `MowPathSaga` (implemented) |

### Suggested code changes

#### 1. Track `ub_zone_hash` transitions → additional map-staleness signal

In `HashList` (or a new helper), compare the last-seen `ub_zone_hash` against
the new one received from `work`.  On change, return `True` so the caller
(state reducer or the HA watcher) can enqueue a `MapFetchSaga`.  This catches
cases where the device modified its zones without the `bol_hash` changing (e.g.
via Bluetooth from another client).

```python
# pymammotion/data/model/hash_list.py

def invalidate_zones(self, ub_zone_hash: int) -> bool:
    """Return True if zone data appears stale (ub_zone_hash changed).

    Unlike bol_hash we cannot locally re-compute ub_zone_hash, so
    we detect changes by tracking the last-seen value.
    """
    if ub_zone_hash != 0 and ub_zone_hash != self._last_ub_zone_hash:
        self._last_ub_zone_hash = ub_zone_hash
        self.root_hash_lists = []   # force full map re-fetch
        return True
    return False
```

#### 2. Track `ub_path_hash` transitions → path re-sync signal

Similar pattern.  When `ub_path_hash` changes, stale path (type 2) data
should be discarded:

```python
def invalidate_paths(self, ub_path_hash: int) -> bool:
    """Return True if recorded-path data is stale."""
    if ub_path_hash != 0 and ub_path_hash != self._last_ub_path_hash:
        self._last_ub_path_hash = ub_path_hash
        self.path = {}
        return True
    return False
```

These are **additive** checks — they do not replace `bol_hash` but complement
it, catching edge cases where zone content changes without the root list
structure changing.
