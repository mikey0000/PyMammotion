# APK map sync on X3/X5 models (Luba 3, Luba mini, Yuka mini …)

Reverse-engineered from Mammotion **2.3.28.31** (`/home/michael/memdex_com.agilexrobotics_20261120_174754/src/sources/com/agilexrobotics/`), cross-checked against 2.3.20.30 (`/home/michael/mammotion_dexdump/src/sources/com/agilexrobotics/`). Paths below are relative to those roots. Line numbers are 2.3.28.31 unless marked. `docs/apk_map_fetch.md` covers the legacy `HashDataManager` flow (2.3.8.201) that Luba 1/2, Yuka and RTK still use.

## TL;DR

- **X5 models have their own sync engine.** `HashDataManager` returns early for every `isX5DeviceTyp()` device (`command/app/HashDataManager.java:649` `isHorseMapDevice`, used at `:377`, `:812` "X5 skip legacy MapElementDB hash sync, handled by HorseMapHashSyncManager", `:792`, `:953`). Their maps are synced by `horse/map/data/source/sync/HorseMapHashSyncManager.java` (a Kotlin singleton) and stored in a separate table, `horsemapelementdb` (`horse/map/data/source/local/HorseMapElementStore.java`). 2.3.20.30 has no such class: X5 devices used the legacy flow there.
- `isX5DeviceTyp()` (`device/source/device/enums/DeviceType.java:984`): `YUKA_MINIV, YUKA_MN100, YUKA_MN101, YUKA_ML, LUBA_VA, LUBA_HM, LUBA_ME, LUBA_TR, LUBA_MB, LUBA_LA, LUBA_LS, LUBA_MS, YUKA_HS, LUBA_MD, LUBA_SP, CM900, CM901`. `YUKA_MINI` (non-V) is not in the list.
- The wire protocol is unchanged: `todev_gethash{pver=1, sub_cmd=0}` for the root list, `todev_get_commondata{action=8, sub_cmd=1, hash}` per element, and a `sub_cmd=2` echo ack per frame. What changed is how the app drives it: one element at a time, a single 20 s inactivity watchdog, the list checked against `bol_hash`, and an atomic DB commit.
- **Area names** come from `name_time.name` in the element's own `toapp_get_commondata_ack`, overwritten by `toapp_all_hash_name` when the map page requests it. If both are empty, the map labels the area `"<title_area><N>"`, where N is its 1-based position in the device's root hash list. Schedule screens use a different fallback (the first unused `"<title_area> N"`).
- **`paternal_hash_b` (`jobHashB`) is the area's stable identity on X5.** The sync uses it to swap a re-hashed area in place, map rendering uses it to match routes across hashes, and route generation **sends it instead of the area hash** (firmware ≥ 2.1.3.45).
- No HTTP endpoint serves area names or map geometry.

## 1. Entry points

| Trigger | Path | Effect |
|---|---|---|
| Status report `bol_hash` (every report) | `BleDataUpdateListener.onDeviceStatuseUpdate` → `HorseMapHashSyncManager.onTotalHashReported(cmHash)` (`horse/map/data/source/device/DefaultDeviceDataSource.java:94-98`) | Compare and sync, see §2 |
| Same report via the legacy manager | `HashDataManager.updateTotalHash` → `ensureHorseMapElementSync(bolHash)` (`HashDataManager.java:2066`, `:2131`) → `HorseMapHashSyncCoordinator.ensureSyncForDevice` → `syncWithKnownTotalHash` | Same |
| Device selected / connected | `HorseMapHashSyncCoordinator.syncIfSelectedAndConnected` (`horse/map/data/source/sync/HorseMapHashSyncCoordinator.java`) | Binds the singleton to the **home-selected, connected** X5 device only, then syncs |
| Map page retry / re-entry after mapping | `HorseMapActivity.retryMapLoad` (`horse/map/HorseMapActivity.java:3444`), `HorseMapEditActivity.resetToAddEntryAfterMapping` (`:3208`), `PlanMapLand231Fragment` (`:3532`) | `forceSyncWithKnownTotalHash(bolHash)`: fetches the list even when the hashes match |
| Start-job gate | `HashDataManager.getIsUpdateMapElement` (`:1107`) → `shouldBlockStartForMapLoading` (`HorseMapHashSyncManager.java:1708`) | Blocks the start while syncing; starts a sync if local ≠ reported |
| Map page resumed | `onMapPageResumed` (`:1507`) | Clears a failed `bol_hash` and retries |
| Work/pause | `setCompareSuspended(true, abortInFlight)` (`:1687`) | Suspends comparisons; aborts an in-flight sync ("device entered work or pause"). The callers are in packed native code and are not visible |

Report gating in `onTotalHashReported` (`:1621`):
- `bol_hash == 1` → ignored ("initializing").
- Suspended → ignored.
- A sync is in progress for a different hash → abort it, keeping the partial map, and restart.
- The same hash already failed → skipped until `bol_hash` changes or the map page resumes.
- `bol_hash == localTotalHash()` → in sync; nothing is sent.
- `bol_hash == 0` → delete every local element.
- Otherwise → `startHashListSync`.

`localTotalHash()` (`:750`) is `MurMurHashUtil.hashUnsigned` over the stored element hashes in `position asc` order (`base_module/helper/HorseMapElementDbStore.java:124`).

## 2. Sync sequence (`HorseMapHashSyncManager`)

1. **`startHashListSync(bolHash)`** (`:1112`): clears all buffers, sets phase `WAITING_HASH_LIST`, sends `getAllBoundaryHashList(0)`, which becomes `MACommandApiHelper.getAllBoundaryHashList(0, 2)` once the helper is ready (`DefaultDeviceDataSource.java:266`, `:351`). Only sub_cmd 0 is requested; dump (4), line (3) and no-vision (5) lists are never asked for.
2. **`onHashListAck`** (`:1411`):
   - Accepts frames only with `sub_cmd == 0`, `pver != 0` and `1 ≤ current ≤ total`.
   - Ignores frames while fetching elements.
   - When idle, accepts a late list only if the local map is empty or the cached hash ≠ the pending one.
   - Frames are buffered by `current_frame`. A changed `total_frame` restarts the buffer, but only on frame 1.
   - Once every frame is present, the list is `distinct()`-ed and **verified**: `hashUnsigned(list) == bolHash`. On a mismatch it is dropped as stale and the list is re-requested once.
   - **No `sub_cmd=2` ack is sent for hash-list frames**: the `CommandSender.getHashResponse` hook exists (`:196`) but nothing calls it. Legacy `HashDataManager.setHashList` dropped its ack too (`:1370`; 2.3.20.30 still acks at `HashDataManager.java:1253`). The dispatcher `MACarDataManager._parseReceivedDeviceData` was not decompiled ("Method dump skipped, 29818 instruction units", `command/app/MACarDataManager.java:1661`), so a dispatcher-level ack cannot be ruled out.
3. **`compareAndSync(remote)`** (`:450`):
   - Empty list while `bol_hash > 1` → stop and keep the local map.
   - `toFetch` = remote hashes not stored locally, **plus** stored type-2 (channel) elements whose `jobHashA == jobHashB == 0`. Those are always re-fetched.
   - `toDelete` = local hashes not in the remote list.
   - With an empty local map, each element is drawn as it arrives (`drawEachFetchedElement`).
   - Otherwise `keepMatchedAreasAndDeleteLocalExtras` (`:690`) deletes the extras at once, **except type-0 areas with `jobHashB != 0`**. Those are held in `pendingDeleteHashes` until a replacement arrives (§5).
4. **`requestNextHash`** (`:990`): one element at a time, `synchronizeHashData(hash)` → `todev_get_commondata{pver=1, action=8, sub_cmd=1, hash}`. A 20 s inactivity watchdog is (re)armed on every send and every accepted frame (`SYNC_INACTIVITY_TIMEOUT_MS`, `:62`, `:1083`).
5. **`onCommonDataAck`** (`:1322`), during `FETCHING_ELEMENTS` only:
   - Frames with `action != 8` are ignored.
   - Every `action=8` frame is acked with `getRegionalData` (`sub_cmd=2`, echo), **before** the hash check and the duplicate check.
   - A frame for a hash other than the one requested is logged and dropped.
   - `result != 0` → retry the element.
   - Duplicates are dropped by the key `hash:current:total`. Frames are buffered by `hash:current`.
   - The element completes as soon as frames `1..total` are all present (not only on the last frame); an empty assembled path means retry.
   - The element is built by `buildElement` (`:317`): `type`, `jobHashA/B` = `paternal_hash_a/b`, `areaName = name_time.name`, `createTime`, `modifyTime`, `hasNameTime`, `position = index in remote list`.
   - Then `replaceWorkingAreaWithSameId` runs, then `advanceFetch`.
6. **`onSvgDataAck`** (`:1522`): the same shape for `toapp_svg_msg`. Only `sub_cmd == 2` frames are handled and acked (`sendResponseSvgDate`). The SVG's own `data_hash` is the hash in the fetch list. The concatenated `svg_file_data` becomes a type-13 pattern element (`buildPatternElement`, `:337`, `jobHashA = paternal_hash_a`).
7. **Retries** (`retryCurrentElementOrStop`, `:1025`):
   - Normal case: up to 2 re-sends of `synchronizeHashData` per element, then `stopSyncOnElementFailure`.
   - First load (local map empty): a failed hash is deferred and the pass moves on; deferred hashes are retried after the pass, giving up after 10 failures per hash (`deferFailedElementFetch`, `:505`).
   - A 20 s stall does the same for the current hash; otherwise it stops the sync.
8. **`finishSync`** (`:519`): on a DB executor it checks `remote ⊆ (local − deletes) ∪ fetched`, otherwise stops with "staged data incomplete". It then commits additions, deletions and positions (index in the remote list) in one transaction (`HorseMapElementStore.commitHashSyncReplacement`, `:432`) and persists `cachedTotalHash` under the SharedPreferences key `horse_map_total_hash_<deviceName>` (`:381`, `:851`).
9. **Stop** (`stopSyncKeepingCurrentMap`, `:1164`): keeps the current map and records `failedBolHash`, so the same hash is not retried until it changes or the map page resumes.

There is no difference between BLE and cloud here: commands go through `MACommandApiHelper.sendOrderMsg_Nav(..., iotable=true)` on whatever link is active.

## 3. Area names

### Sources

| Source | Where it lands |
|---|---|
| `toapp_get_commondata_ack.name_time.{name, create_time, modify_time}` | Parsed only when `hasNameTime()` (`command/MACarDataManagerAPI.java:1106-1110`); stored on the element (`HorseMapHashSyncManager.buildElement`, `:317`) |
| `toapp_all_hash_name` (reply to `toapp_map_name_msg{hash=0, rw=0, deviceId}`) | Replaces `CarWorkingStateMachineBean.areaNameMap` wholesale and saves it to SharedPreferences `<deviceTitle>AREA_HASH_NAME` (`MACarDataManagerAPI.java:1273-1300`) |
| Rename echo `toapp_map_name_msg` | `AreaNameChangedListener.onAreaNameChanged(hash, name)`; the dispatcher is not decompiled |

The request: `MACommandApiHelper.getAreaNameList(deviceId)` (`command/app/MACommandApiHelper.java:974`) first fills `defAreaNameMap` with generated names, then sends `toapp_map_name_msg{hash=0, result=0, deviceId, rw=0}`; it skips the send on Luba 1. A rename is `areaRename(deviceId, hash, name, rw)` → `toapp_map_name_msg{hash, name, deviceId, rw}` (`:568`).

On X5, `HorseMapViewModel.startAreaNameSync` (`horse/map/HorseMapViewModel.java:3442`) is called from `HorseMapActivity` with `requestImmediately=true` (`HorseMapActivity.java:4394`) and from the edit screen with `false`. It requests the full list. The reply, and every rename callback (`:1584`), goes to `applySyncedAreaNames` (`:2838`, body `:385-465`). That **overwrites `areaName`** on each listed element, in memory (`MapDataManager.updateAreaName`, `:3598`) and in `horsemapelementdb`, with the list's value, **even an empty one**. A rename callback also re-requests the full list.

The sync itself never requests names; only the map screens do. Legacy `HashDataManager` requests them after `updateMapElementDB` (`:923`) and after saving a type-0 element (`:1676`).

### (a) Labelling an area with no name

There are three fallbacks, one per screen. None of them uses hash order, `paternal_hash_b` or creation time.

| Screen | Order of precedence | Fallback text |
|---|---|---|
| X5 map labels, area picker (`MapDataManager.resolveAreaDisplayName`, `horse/map/data/source/MapDataManager.java:1474`; callers `buildMapAreaLabels` `:1626`, `getAreaDisplayName` `:3000`) | `areaName.trim()` (which is `name_time.name`, unless overwritten by `toapp_all_hash_name`) | `getString(title_area) + index`, **no space**; `index` = 1-based position in `getSortedAreaList()` (`:3311`), i.e. type-0 elements in `position asc` order = **order in the device's root hash list** |
| X5 create-plan sheet (`HorseMapActivity.java:2540-2565`) | `areaName`, then `getRealAreaNameMap()[hash]` | `title_area + " " + i`, 1-based position in `getAreaList()` (same order) |
| Schedules (`work/setting/viewmodel/JobScheduleViewModel.getAreaNameMap`, `:78-117`) and `MACommandApiHelper.getAreaNameList` (`:991-1029`) | `toapp_all_hash_name` (`CarWorkingStateMachineBean.getRealAreaNameMap`, `device/source/device/bean/CarWorkingStateMachineBean.java:183`: names from the list override `defAreaNameMap` for keys already in it), then `name_time.name`, then the generated name | `title_area + " " + N`, N = **smallest number not already used** by another name, assigned in position order. In `getAreaNameList` the decompiled loop condition reads inverted next to the `JobScheduleViewModel` copy; the "first unused" reading is (inferred) from that copy |

`title_area` is a localized resource (`resource/R.java:5184`); its English value was not decoded from `resources.arsc`.

Legacy (non-X5) `MapEditingViewModel` (`map/viewmodel/MapEditingViewModel.java:542-550`) uses `areaNameMap[hash]`, otherwise `title_area + " " + (i+1)` by list index.

### (b) `create_time`, `modify_time`, `paternal_hash_b`

- `create_time`: stored and copied between DB models only. **Never read** for ordering, identity or display.
- `modify_time`:
  - A cache key for projected area geometry (`MapDataManager.areaGeometry`, `:755-788`).
  - Diagnostics (`base_module/utils/MapLocateSnapshot.java:223`).
  - Legacy `BaseMapFragment.dedupeOverlappingAutoMappingBoundaries` (`map/fragment/BaseMapFragment.java:4284`): when auto-mapped boundaries overlap, it keeps the newest by `modifyTime`.
  - Not used for display order.
- `hasNameTime`: persisted only. No reader found.
- `paternal_hash_b` (`jobHashB`), the X5 **area identity**:
  - `HorseMapHashSyncManager.areaIdOf` (`:306`): for type 0, a `jobHashB != 0` is the area id. Used by `sameAreaHashes` and `replaceWorkingAreaWithSameId` (§5).
  - `MapDataManager.rebuildZoneAliasGroups` (`:1383`): unions `{hash, jobHashA, jobHashB}` of every type-0 element into alias groups. `expandZoneHashAliases` (`:2463`) lets `CoverPathRouteManager` (`horse/map/data/source/CoverPathRouteManager.java:810-860`, `:898`, `:992`, …) match a stored route to the selected areas when their hashes differ.
  - `WorkingAreaStateController` (`horse/map/data/source/working/WorkingAreaStateController.java:155`): the working-area match accepts `jobHashB`, `hash` or `jobHashA`.
  - **Route generation on X5**: `WorkSettingViewModel.toGetPreAirLine` (`work/setting/viewmodel/WorkSettingViewModel.java:724-753`) and `HomeStateViewModule` start-now (`home/viewmodel/HomeStateViewModule.java:828-860`) put each selected area's **`jobHashB`** into `NavReqCoverPath.zone_hashs` when it is > 0, otherwise the area hash. This applies only when `isX5DeviceTyp()` and firmware ≥ `Constants.BUNDLE_ID = "2.1.3.45"`; logged as "区域下发优化" (area dispatch optimisation). It is also present in 2.3.20.30.
  - Legacy: action-16 (hide/show) falls back to looking up the element by `pHashB` (`HashDataManager.java:1518-1530`); `TaskPreviewRouteHelper` (`horse/map/taskpreview/TaskPreviewRouteHelper.java:305-341`) maps hashes to `jobHashB`.

## 4. Other element types

- Every type in the root list is fetched with the same `action=8` request; the frame's `type` decides the kind. Type 13 (SVG pattern) arrives as `toapp_svg_msg`.
- `HorseMapElementStore.TYPE_CHANNEL = 2`: on X5, type 2 is a **channel** (`MapDataManager.getChannelList`), not a Luba 1 path.
- Dump and no-vision lists (sub_cmd 4/5) are never requested by the X5 sync. Legacy `updateDumpDB` / `updateNoVisionDB` return early for X5 (`HashDataManager.java:792`, `:953`).
- Live streams sit outside the sync and run while working:
  - Dynamic line: `getDynamicsLine`, `action=8, type=18`, 10 s timer 100003.
  - **Edge line** (new): `MACommandApiHelper.getEdgeLine` (`:1187`) sends `action=8, sub_cmd=1, type=31` with a 3 s throttle. `HashDataManager.getEdgeLine` / timer 100004 (`:1073`, `:174`) re-polls every 10 s while working. Frames are acked and buffered under the key `hash:current:E` (`updateEdgeLine`, `:1880`).

## 5. Re-hash reconciliation (c)

When an edit or re-save gives an area a new hash:

- The old hash drops out of the list and the new one is fetched. If the old element is type 0 with `jobHashB != 0`, it is **not** deleted up front (`keepMatchedAreasAndDeleteLocalExtras`, `:690`).
- When the new element arrives, `replaceWorkingAreaWithSameId` (`:927`) looks for local elements with the same `jobHashB`, saves the new one, and deletes the old ones on the main handler. It announces this as one added hash plus the deleted old hashes, so the area is replaced on screen rather than removed and re-added.
- Name: nothing is carried across. The new element takes `name_time.name` from its own frame, and the next `toapp_all_hash_name` overwrites it.
- Position: taken from the new remote list.
- Route/selection matching: survives through the alias groups and `jobHashB` (§3b).
- Schedules: plan `zone_hashs` hold area hashes (`horse/map/createplan/HorseCreatePlanHelper.java:302`). No code that rewrites or deletes them after a re-hash was found. The create-plan sheet preselects only the plan hashes still present (`HorseMapActivity.java:2524-2540`).

## 6. Cloud / HTTP (d)

No newer-model path reads area names or map geometry over HTTP. Map-related endpoints in `map/api/MapApiService.java`:

- `/device-server/v1/map/backup/*`: opaque whole-map backup, restore and rename.
- `/device-server/v1/device/point/cloud/map` and its progress endpoint: point cloud (`LUBA_LD`).
- `/device-server/v1/lawn-pattern/list`: the SVG pattern catalogue.
- `/device-server/v1/texture-layer/find`.
- `spino/map`: pool maps.

The React Native bundle (`extracted/base/assets/index.android.bundle`) only routes to native map activities (`/map/JOB_HISTORY_ACTIVITY`, `/map/SPMapActivity`, …) and holds the mapping-guide pages. It contains no hash, area-name or `name_time` handling.

## 7. Legacy `HashDataManager` changes in 2.3.28.31

These still apply to Luba 1/2, Yuka and RTK:

- `setHashList` no longer acks root-list frames (`:1370`).
- `getHashAre` / `updateMapElementDB` skip hashes already stored and mark them visible (`existsMapElement` `:326`, `ensureExistingElementVisible` `:298`).
- When the list is exhausted, the local hash is recomputed **in device list order** (`hashUnsignedInCarOrder`, `:633`). `getDBCmHash` (`:1001`) uses that order when the local and remote sets are equal.
- `updateMapElementDB` always ends with `getAreaNameList` (`:923`).

## 8. Differences from what pymammotion does today

1. **Fallback labels** (resolved). `HashList.computed_areas` is the one place that labels an unnamed area: `"Area N"`, N its 1-based position among the areas of `area_root_hashlist` (areas the list does not hold follow in arrival order). The reducer and `MapFetchSaga` store only the names the device reported (`fill_area_names_from_frames`), empty for an unnamed area. The app's localized `title_area`, with or without a space, is not reproduced.
2. **Fallback text** (resolved, see 1).
3. **Area identity** (resolved). `HashList.area_id(hash)` returns `paternal_hash_b` when non-zero, else `name_time.create_time` when no other stored area shares it, else None. Observed: X5 (Luba 3 `LUBA_VA`, Luba mini 2 `LUBA_MS`) areas carry `paternal_hash_b` 1..n, unchanged with `create_time` across a whole-map re-hash; Yuka, Yuka Mini and Luba 2 areas carry 0, and their `create_time` survives an edit (Yuka "Front yard"). Some Luba 2 areas have `create_time` 0, so they have no id. Luba 1 is unverified. Home Assistant keys the area switch's re-hash match on it; routes still send area hashes (item 4).
4. **Route zone ids.** pymammotion sends area hashes in `zone_hashs` (`pymammotion/messaging/mow_path_saga.py:96`, `:254`; `pymammotion/homeassistant/mower_api.py:391`). On X5 firmware ≥ 2.1.3.45 the app sends each area's `paternal_hash_b` when it is non-zero (§3b).
5. **Plans dropped on re-hash.** `update_hash_lists` deletes any local plan whose `zone_hashs` reference a hash missing from `area` (`hash_list.py:648-653`). The app keeps plans (no equivalent found).
6. **Root list not checked against `bol_hash`.** The app rejects an assembled list whose MurMur hash ≠ the reported `bol_hash` and re-requests it once. `MapFetchSaga` accepts whatever arrives (`map_saga.py:197-216`). Related (inferred): `update_root_hash_list` matches lists by `(total_frame, sub_cmd)` (`hash_list.py:890-902`), so a list whose `total_frame` changed sits beside the stale one when `invalidate_maps` was skipped (`bol_hash` unknown); `hashlist`/`area_root_hashlist` then concatenate both.
7. **No `bol_hash == 1` guard.** `_on_map_state_changed` (`pymammotion/device/auto_fetch.py`) and `invalidate_maps` (`hash_list.py:1245`) treat 1 as an ordinary hash. Both app paths ignore it.
8. **Requests the dump list on every run** (`map_saga.py:231-248`). The X5 sync never sends `sub_cmd=4`.
9. **Acks root-list frames** (`map_saga.py:204-216`). 2.3.28.31 sends no such ack from either manager. The dispatcher could not be decompiled, so whether the ack is still sent elsewhere is undetermined. Harmless unless a device rejects it (inferred).
10. **Channel re-fetch.** The X5 sync always re-fetches type-2 elements whose parent hashes are both 0. pymammotion trusts its cache by hash. `PathType.PATH` is documented as "Luba 1 path-mode" (`hash_list.py:39-40`); on X5, type 2 is a channel.
11. **Timeouts.** App: 20 s inactivity, 2 retries per element, then keep the current map and do not retry that `bol_hash` until it changes. pymammotion: 5 s step timeout, a 10-step no-progress limit and `max_attempts = 2` (`map_saga.py:49-53`, `:278`, `:368-369`).
12. **Type 31 (edge line)** has no `PathType` entry. Its frames land in `unknown_type_frames` (`hash_list.py:1038-1041`), keyed by hash, and are never cleared.
13. **Work/pause suspension** (resolved). Automatic syncs wait while `sys_status` is in `MOWING_ACTIVE_MODES` and run once when the job ends, on every link (`MowerDevice.map_sync_due`, `docs/decisions.md` D16). The app suspends through `setCompareSuspended` (callers not visible; its abort message names work or pause) and re-checks `lastReportedBolHash` on resume.

## Not determined

- Whether `MACarDataManager._parseReceivedDeviceData` acks `toapp_gethash_ack` frames, and which incoming message fires `AreaNameChangedListener` (the method is not decompiled).
- Where `setCompareSuspended` and `onMapPageResumed` are called from (packed native code).
- The English value of `title_area`.
