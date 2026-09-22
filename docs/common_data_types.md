# NavGetCommData Type Field Reference

This document describes every known numeric value for the `type` field in
`NavGetCommData` / `NavGetCommDataAck` messages.  These are the values that
flow in the `todev_get_commondata` request (app → device) and the matching
`toapp_get_commondata_ack` response (device → app).

The `type` field is an `int32` in the protobuf definition.  The corresponding
Python enum is `PathType` in `pymammotion/data/model/hash_list.py`.

---

## How the request/response works

```
App → device:  todev_get_commondata
                  NavGetCommData {
                      pver     = 1
                      action   = <action>   # see Action table below
                      sub_cmd  = 1          # 1 = fetch, 2 = re-request frame
                      type     = <type>     # this document
                      hash     = <hash>     # 0 when not hash-specific
                  }

Device → app:  toapp_get_commondata_ack
                  NavGetCommDataAck {
                      type         = <same type>
                      total_frame  = N        # how many frames in the response
                      current_frame = K       # this frame (1-based)
                      data_couple  = [...]    # CommDataCouple(x, y) points
                      hash         = <hash>   # non-zero for hash-keyed types
                      result       = 0        # 0 = success
                  }
```

Multi-frame responses: when `total_frame > 1` the device sends frames
sequentially.  For hash-keyed types (0–13, 25–26) the app must request any
missing frames via `get_regional_data` (sub_cmd=2).  For dynamics line
(type=18) the device pushes all frames automatically — no re-request needed.

---

## Type values

### Type 0 — AREA (mowing-zone boundary)

**`PathType.AREA = 0`**

Boundary polygon for a single mowing zone (area).  Each `CommDataCouple`
entry is one vertex of the closed polygon in the device's local coordinate
system (metres from the RTK base).

**Keyed by hash:** Yes — one `FrameList` entry per area hash in
`HashList.area`.

**Fetched by:** `synchronize_hash_data(hash_num=<area_hash>)` during
`MapFetchSaga` step 4.

**APK source:** `HashDataManager.lineList`, `MACarDataManager` case
`toapp_get_commondata_ack` type==0.

---

### Type 1 — OBSTACLE (keep-out zone boundary)

**`PathType.OBSTACLE = 1`**

Boundary polygon for a keep-out / no-go obstacle zone.  Same coordinate
format as type 0.

**Keyed by hash:** Yes — `HashList.obstacle`.

**Fetched by:** `synchronize_hash_data` during `MapFetchSaga` step 4.

---

### Type 2 — PATH (recorded travel path)

**`PathType.PATH = 2`**

Recorded travel-path segments, used by Luba 1 path-mode mowing.  The
device records the path the operator drove during path recording and
replays it during auto-mow.

**Keyed by hash:** Yes — `HashList.path`.

**Staleness indicator:** `work.ub_path_hash` in `toapp_report_data`; see
`hash_guide.md` for details.

**APK source:** `MACarDataManager` type==2 branch.

---

### Type 10 — LINE (mowing-line / breakpoint segments)

**`PathType.LINE = 10`**

Pre-computed mowing-line segments associated with the current job plan.
Also used to store breakpoint resume data (the exact line the mower was
on when interrupted).  Related to the `sub_cmd=3` hash list.

**Keyed by hash:** Yes — `HashList.line`.

**Note:** This is distinct from the live dynamics line (type 18).  Type 10
is a *static* snapshot of the planned lines; type 18 is the *live* path
driven so far.

**APK source:** `HashDataManager.lineList` (path segments), `MACarDataManager`
type==10 branch.

---

### Type 12 — DUMP (clippings-collection zone)

**`PathType.DUMP = 12`**

Boundary for a dump / grass-clippings collection zone (models with a
catcher or dedicated drop zone).

**Keyed by hash:** Yes — `HashList.dump`.

**Also associated with sub_cmd=4** in some request variants.

---

### Type 13 — SVG (pre-rendered map tile)

**`PathType.SVG = 13`**

A pre-rendered SVG image of the map, sent by the device as a binary blob.
Allows the app to display a raster overview without having to render all
boundary polygons client-side.

**Keyed by hash:** Yes — `HashList.svg` (stores `SvgMessage` objects rather
than `FrameList`).

**Response message:** `toapp_svg_msg` (not `toapp_get_commondata_ack`) — the
device uses a separate message type for SVG data, handled alongside
`toapp_get_commondata_ack` in `MapFetchSaga`.

---

### Type 18 — DYNAMICS_LINE (live mow-progress path)

**`PathType.DYNAMICS_LINE = 18`**

The path the mower has actually driven during the **current** work session.
This is the "real-time breadcrumb trail" — the visual overlay that shows
which parts of the lawn have been mowed so far.

**Not keyed by hash:** The device always returns the current session's data
with no hash identifier.  There is only ever one dynamics line at a time.

**Request:** `NavGetCommData(pver=1, action=8, sub_cmd=1, type=18, hash=0)`  
No hash is needed; the device returns whichever session is active.

**Frame assembly:** Frames arrive sequentially; frame 1 signals a fresh
session (clear previous data).  Each frame's `data_couple` list is
appended in order.  When `current_frame == total_frame` the path is
complete for this fetch.

**Storage:** `HashList.dynamics_line: list[CommDataCouple]`  
Updated atomically via `HashList.update_dynamics_line(points)` once all
frames are assembled.

**Rate limit:** The APK rate-limits this to once per 1000 ms and triggers it
every ~10 seconds while the mower is in a working state.

**Trigger:** Call `MammotionClient.get_dynamics_line(device_name)` while
`device.report_data.dev.sys_status == WorkMode.MODE_WORKING`.

**APK source:**
- Request: `MACommandHelper.getDynamicsLine()` line 974–981
- Assembly: `HashDataManager.updateDynamicsLine()` (action=8, type=18 branch)
- Comment on line 980: `"发送指令--动态航线"` ("Send command--dynamic route")

---

### Type 25 — VISUAL_SAFETY_ZONE (vision safety zone)

**`PathType.VISUAL_SAFETY_ZONE = 25`**

Safety zone boundary detected by the onboard vision camera (Luba 2 Vision
/ Pro models only).  Areas the vision system has flagged as hazardous.

**Keyed by hash:** Yes — `HashList.visual_safety_zone`.

---

### Type 26 — VISUAL_OBSTACLE_ZONE (vision obstacle zone)

**`PathType.VISUAL_OBSTACLE_ZONE = 26`**

Dynamic or static obstacle boundary detected by the onboard vision camera
(Luba 2 Vision / Pro models only).

**Keyed by hash:** Yes — `HashList.visual_obstacle_zone`.

---

## Action field values (NavGetCommData.action)

The `action` field controls *how* the device interprets the request.  The
type field identifies *what* data is requested.

| Action | Meaning | Notes |
|--------|---------|-------|
| 0 | List / query | Request a listing or status for the given type |
| 1 | Download / fetch | Fetch data for the given type/hash |
| 4 | Delete | Delete data identified by hash |
| 5 | Upload | Upload data from app to device |
| 6 | Upload with hash | Upload data for a specific hash |
| 7 | Cancel | Cancel an in-progress operation |
| 8 | Fetch / sync | Fetch data for hash (map sync) or type (dynamics line) |
| 12 | Restore / synchronise | Trigger a full data-restore for the given type |
| 14 | List names | Request named entity list (area names etc.) |
| 15 | Rename | Rename an entity identified by hash |

Action 8 is the most commonly used fetch action.  It appears in:
- `synchronize_hash_data(hash_num)` — action=8 with hash (fetch one area/obstacle/path chunk)
- `get_area_to_be_transferred()` — action=8, type=3 (charging-pile transfer area)
- `get_dynamics_line()` / `CommonDataSaga` — action=8, type=18 (live mow path)

---

## sub_cmd field values

| sub_cmd | Meaning |
|---------|---------|
| 0 | Root hash list request |
| 1 | Fetch data (used in get_common_data) |
| 2 | Re-request a specific missing frame (get_regional_data) |
| 3 | Line hash list (post route-planning; used by MowPathSaga) |
| 4 | Dump/clippings zone variant |

---

## Summary table

| Type | Name | Hash-keyed | Storage | Notes |
|------|------|-----------|---------|-------|
| 0 | AREA | Yes | `HashList.area` | Zone boundary polygon |
| 1 | OBSTACLE | Yes | `HashList.obstacle` | Keep-out zone |
| 2 | PATH | Yes | `HashList.path` | Luba 1 recorded path |
| 10 | LINE | Yes | `HashList.line` | Planned mow lines / breakpoint |
| 12 | DUMP | Yes | `HashList.dump` | Clippings collection zone |
| 13 | SVG | Yes | `HashList.svg` | Pre-rendered map tile |
| 18 | DYNAMICS_LINE | No | `HashList.dynamics_line` | Live mow-progress path |
| 25 | VISUAL_SAFETY_ZONE | Yes | `HashList.visual_safety_zone` | Vision safety zone |
| 26 | VISUAL_OBSTACLE_ZONE | Yes | `HashList.visual_obstacle_zone` | Vision obstacle zone |
