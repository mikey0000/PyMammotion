# APK Map / Hash / Line / SVG Fetch Protocol — exhaustive reference

Reverse-engineered from Mammotion 2.3.8.201 APK at `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/`, with cross-checks against 2.2.4.13 because 2.3.8.201's dispatcher method `MACarDataManager._parseReceivedDeviceData` failed JADX decompilation — its 23,844-instruction body throws `UnsupportedOperationException`.

## TL;DR — the headline finding for Luba 3 / LUBA_HM

`DeviceType.isSupportDynamicsLine()` returns **true** for `LUBA_HM` (`DeviceType.java:606-607`). This puts LUBA_HM on the YUKA-mini / Yuka-ML branch of `HashDataManager` for every `isSupportDynamicsLine` check (`HashDataManager.java:306, :368, :724, :731, :751, :1410, :1432, :1447`). That branch differs from the standard Luba 1/2 path: it triggers `sendHandler(12333, 0)` (immediate next-area request) instead of just emitting an `RxBus` event after each area completes; it sets `deleteState=2` (draft) on the persisted element; it skips the `LitePal.isExist` check and always re-saves; it uses 0 ms (not 300 ms) for the 12334 reconcile delay; and on exhaustion it issues `deleteMapElementDB(iotId, type=1)` to purge type-1 elements.

If `MapFetchSaga` is timing out on `toapp_get_commondata_ack`, the most likely root cause is **missing per-frame `subCmd=2` acks**. The APK acks every frame (including the final one) via `nav.todev_get_commondata{action=<echoed>, type=<echoed>, hash=<echoed>, subCmd=2, totalFrame=<echoed>, currentFrame=<echoed>}`, and the device waits for those acks before sending the next frame. Details in §7 and §9.

## File-of-record

```
command/app/HashDataManager.java        — central state machine (1840 lines)
command/MACommandHelper.java            — outgoing builders, top-level variant
command/app/MACommandApiHelper.java     — outgoing builders, field-mower variant (HashDataManager holds this; getDynamicsLine lives here at :941)
command/app/MACarDataManager.java       — incoming protobuf decoder (2.3.8.201 cannot decompile _parseReceivedDeviceData; use 2.2.4.13)
command/app/contract/HashDataListener.java   — single-method interface, just setHashList; the other entry points are direct calls
base_module/entity/HashListBean.java         — pver/subCmd/totalFrame/currentFrame/dataHash/path
base_module/entity/RegionalDataBean.java     — action/type/result/hash/pHashA/pHashB/totalFrame/currentFrame/path/name/createTime/modifyTime
base_module/entity/SvgDataBean.java
base_module/entity/LineInfoBean.java + PathPacketBean.java
proto/MctrlNav.java                     — NavGetHashListAck (case 31 in subNavMsgCase), NavGetCommDataAck (case 33), svg_message_ack_t, cover_path_upload_t
```

## 1. Entry points — what kicks a fetch off

The **only** way a fetch starts: a status report arrives with a new bolHash, and `HashDataManager.updateTotalHash(deviceState, breakPointType, bolHash, pathHash)` (`HashDataManager.java:1780`) decides to act.

```java
public void updateTotalHash(int i3, int i4, long j3, long j4) {
    if (i3 == DeviceWorkState.MODE_UPDATING.getValue()) return;        // never during firmware update
    // ... iotId check ...
    if (j3 == 0 && this.isUpdateMap) this.isUpdateMap = false;
    if (this.bolHash != j3) {
        if (this.isUpdateMap) this.isUpdateMap = false;
        this.hashListBeanString = "";                                   // clear dedup string
        if (this.deviceBean.type().isPureVisual()) {
            if (!this.noHashList.isEmpty()) this.noHashList.clear();
            removeHandler12333(true);
        }
    }
    if (this.bolHash != j3 && !this.isUpdateMap && j3 != 1) {           // !=1 is magic "device is wiping" sentinel
        this.bolHash = j3;
        if (j3 > 0) {
            this.isUpdateMap = true;
            maCommandHelper.getAllBoundaryHashList(0, 2);               // START AREA FETCH (subCmd=0)
        } else if (j3 == 0) {
            this.noHashIndex = 0;
            clearNoHashList();
            CommonDBHelper.getInstance().clearAllDB(...);
            RxBusSend(getHashDateEvent(14));
        }
    }
    // pathHash sanity:
    if (j4 == 0 || this.mPathHash != j4) {
        if (j3 == getDBCmHash().longValue() && this.isUpdateMap) this.isUpdateMap = false;
        this.hashListBeanString = "";
    }
    if (this.mPathHash == j4 || this.isUpdateMap || j3 != getDBCmHash().longValue()) return;
    this.mPathHash = j4;
    if (j4 <= 1) {
        clearNoLineHashList();
        MapModule.INSTANCE.getMapData().deleteLineListDBAndHashDB(this.deviceBean.getIotId());
    } else {
        this.isUpdateMap = true;
        getLineHashList(1);                                             // START LINE FETCH (subCmd=3)
        RxBusSend(getHashDateEvent(29));
    }
}
```

Things to highlight:
- **Fetch only starts on a bolHash change in the work-report.** Caller is `MACarDataManager.java:4077, :4081` from inside the work-report parser.
- **Line fetch is gated on `j3 == getDBCmHash()`** — i.e. line fetch only starts after areas have already been synced. Areas first, lines second.
- **`isUpdateMap` is the single mutex** — only one fetch (area or line) runs at a time.
- **`bolHash == 1` is a magic sentinel** for "device is wiping" — APK refuses to fetch.
- `MODE_UPDATING` blocks everything.
- For `pathHash <= 1`, APK wipes the local line DB and does not fetch.

There is **no** "user pressed refresh" button. UI gets a refresh by calling `initBolHash()` (`HashDataManager.java:920` — sets `bolHash = 0L; isUpdateMap = false;`), which primes a re-fetch on the next work-report. Similarly `initPathHash()` (`:925`) and `updateLocalBolHash()` (`:1767`).

## 2. State machine — fields and clearing

All fields on `HashDataManager`:

| Field | Init | Cleared by | Read by | Semantics |
|-------|------|-----------|---------|-----------|
| `bolHash` (long) | `getDBCmHash()` (ctor :207) | `updateTotalHash` :1806; zeroed by `initBolHash` :920, `updateLocalBolHash` :1767, `getIsUpdateMapElement` :900 if local DB hash is 0 | `updateTotalHash` mismatch test :1791, :1805 | Device's aggregate hash of zone/forbidden/channel root hashes |
| `mPathHash` (long) | `getDBPathHash()` (ctor :208) | `updateTotalHash` :1829; zeroed by `initPathHash` :925 | `routeResponse` :1099; `isLoadingLing` :946; `getHashLineNew` :443 (`<= 1` treated as nothing) | Device's aggregate line-data hash |
| `hashList` (`ArrayList<Long>`) | new (ctor) | Frame 1 + subCmd 0 → `.clear()` (:1147) | `updateMapElementDB` :683-790 compares against local DB | Root list of zone hashes from device |
| `lineHashList` | new | Frame 1 + subCmd 3 → `.clear()` (:1150) | `updateMapLineDB` :794 seeds `noLineHashList`; `getHashLineNew` :467 | Root list of line-data hashes |
| `dumpHashList` | new | Frame 1 + subCmd 4 → `.clear()` (:1153) | `updateDumpDB` :656; **also** read by `updateNoVisionDB` :819 (same field, both use `dumpHashList`!) | Dump-point root hashes |
| `noVisionList` (`:86`) | new | Frame 1 + subCmd 5 → `.clear()` (:1156) | (no reader in HashDataManager) | "Vision safety zone" hash list |
| `noHashList` | new | `clearNoHashList` :236; cleared in `updateTotalHash` `bolHash==0` :1815 and for pure-visual :1797. Populated in `updateMapElementDB` :739-744, :758-762; re-populated in `getHashAre` :357 | `getHashAre` :313 driver | Zones we still need full data for |
| `noHashIndex` (int) | 0 (:87) | Incremented `getHashAre` :335, `setRegionalData` :1228 & :1453, `updateGraphicsData` :1758. Reset in `getHashAre` exhaustion :339 and `updateTotalHash` `bolHash==0` :1814 | `getHashAre` :313, `getNoHash` :489 | Cursor into `noHashList`. **Advances only on `action==8` final frame and SVG completion** |
| `numberRegion` | 0 (:91) | Increment 12333 fire :112, empty-path action-8 :1227. Reset `removeHandler12333(true)` :585 and `setHashList` final-frame subCmd 0 :1180 | `>= 10` → stop (:108, :321) | Per-area retry counter |
| `number` | 0 (:90) | Increment 12334 fire :125. Reset `removeHandler12334` :592, `updateMapElementDB` :699, `setHashList` :1179 | `>= 10` → stop (:118) | DB-reconcile retry counter |
| `numberLine` | 0 (:92) | Increment 100001 fire :162. Reset `removeHandler100001(true)` :577, `setHashList` final-frame subCmd 3 :1186 | `>= 10` → `isUpdateFailed=true`, stop (:153) | Line-fetch retry counter |
| `areaListMap` (`HashMap<String, List<List<Double>>>`) | new | `getHashAre` :320, `setRegionalData` :1373, `recoverAreaOutDumpingData` :1043 | dedup via `containsKey`; size vs `totalFrame` for `isPerfect` :1361, :1028 | Per-area frame buffer. Key: `"<dataHash>:<currentFrame>:A"`. **One area at a time** |
| `areaGraphicsListMap` | new | `updateGraphicsData` final-frame :1705 | SVG dedup + reassembly :1684, :1693 | SVG frame buffer. Same key format |
| `dynamicsLineListMap` | new | `updateDynamicsLine` frame 1 :1600, `removeGetDynamicsLineHandler` :1084, `getDynamicsLineCommand` :884 | `updateDynamicsLine` dedup :1602 | MN231/HM dynamic-line frame buffer. Key: `"<dataHash>:<currentFrame>:L"` |
| `lineList` | new | `getHashLineNew` :425, `setRouteList` :1489 | `setRouteList` dedup + assemble :1501, :1513 | Cover-path frame buffer keyed `"<path_hash>:<path_cur>"` |
| `lineKeyStringList` | new | `getHashLineNew` :429, `updateMapLineDB` :815 | `setRouteList` :1492, :1497 | Per-batch line-frame dedup |
| `noLineHashList` | new | `clearNoLineHashList` :243; seeded in `updateMapLineDB` :795; reseeded in `getHashLineNew` :471 | `getHashLineNew`, `getHashLineList` :396 | Lines we still need to fetch |
| `mapHashOrder` (`Map<Long,Integer>`) | new | `updateMapElementDB` :686-690 | `mapElementBean.setPosition` everywhere | Display order |
| `mapHashLineOrder` | new | `updateMapLineDB` :796-800 | line `setPosition` | Line display order |
| `mapHashTime` (`Map<Long,Long>`) | new | `.put(hash, now)` in `getHashAre` :333 | `getHashAre` :317 (100 ms throttle) | **Last-sent timestamp per hash — the throttle gate** |
| `hashListBeanString` (String) | `""` | Set to `bean.toString()` in `setHashList` :1131. Reset to `""` in many places: `getHashAre` :299, `updateMapElementDB` :680 & :1795, `updateTotalHash` :1795 & :1824, `getLineHashList` :481, `getHashLineNew` :444, `routeResponse` :1279 | `setHashList` short-circuits if equal :1128 | Dedup by `.toString()` for incoming `NavGetHashListAck` |
| `isUpdateMap` (bool) | false (:205) | true in `updateTotalHash` :1808 & :1834; false on completion/clear/match | gates re-entry of `updateTotalHash` | Single fetch-in-progress mutex |
| `isUpdateFailed` | false | true on `numberLine >= 10` :154; false on completion :445, `setRouteList` :1554 | `isGetLineFailed` :942 | Sticky "line fetch gave up" |
| `isAddLine` | true (:88) | false after sending batch :437; true after reseed :475, :814; false in 100001 retry :160 | `getHashLineNew` :415 | Two-phase flag for line batches |
| `transactionId` | 0 (:89) | `now` at `getHashLineNew` send :427 | echoed back in `cover_path_upload_t.transaction_id`; checked :1477 | Identifies one line batch |
| `isPerfect` | false (:167) | true if `areaListMap.size() == totalFrame` :1029, :1362, :1694 | gates persistence :1068, :1432, :1748 | "Did we get every frame for this area?" |
| `inVisibleLineList` / `visibleLineList` | new | reset in `setLine` :614-615 | `getNoLineHash` partitioning | Lines near/far from mower for fetch priority |

## 3. Outgoing command sequence

### `getAllBoundaryHashList(subCmd, logType)` — `MACommandHelper.java:702`

```java
sendOrderMsg_Nav(MctrlNav.MctlNav.newBuilder().setTodevGethash(
    MctrlNav.NavGetHashList.newBuilder()
        .setPver(1)
        .setSubCmd(i3)                  // 0=areas, 3=lines, 4=dump-points, 5=no-vision
        .build()
).build(), 20, true, "...");
```

Field: `nav.todev_gethash`. Sub-commands:
- `0` → fetch root list of zone/area hashes
- `3` → fetch root list of line-data hashes
- `4` → fetch dump-point hashes
- `5` → fetch no-vision (vision-safe-zone) hashes

The second arg is metadata only (log-tag).

**Called from:**
- `updateTotalHash :1811` — subCmd=0 logType=2, start of area fetch
- `setRegionalData :1282` — subCmd=0 logType=1, retry after `action=6 result=1` ("re-list from top")
- `getLineHashList :484` — subCmd=3 logType=3, start of line fetch

Reply: stream of `NavGetHashListAck` frames in `nav.toapp_gethash_ack`.

### `synchronizeHashData(hash)` — `MACommandHelper.java:1785`

```java
sendOrderMsg_Nav(MctrlNav.MctlNav.newBuilder().setTodevGetCommondata(
    MctrlNav.NavGetCommData.newBuilder()
        .setPver(1)
        .setAction(8)
        .setHash(l3.longValue())
        .setSubCmd(1)
        .build()
).build(), 22, true, "...");
```

Field: `nav.todev_get_commondata`. `action=8, subCmd=1`, `type` left at default (0).

Called once per zone hash from `getHashAre :327`. Re-sent for the same hash only if `now - mapHashTime[hash] > 100 ms` (the 100 ms throttle at `:319`); otherwise the call is suppressed but the timestamp is overwritten anyway (`:333`), keeping the cursor "live" for the next 12333 tick.

Reply: stream of `NavGetCommDataAck` frames in `nav.toapp_get_commondata_ack` — multi-frame, current/total, each carrying a chunk of polygon points.

### `getRegionalData(bean)` — `MACommandHelper.java:937` — THE PER-FRAME ACK

```java
sendOrderMsg_Nav(MctrlNav.MctlNav.newBuilder().setTodevGetCommondata(
    MctrlNav.NavGetCommData.newBuilder()
        .setPver(1)
        .setAction(regionalDataBean.getAction())        // echo incoming
        .setType(regionalDataBean.getType())            // echo incoming
        .setHash(regionalDataBean.getHash())            // echo incoming
        .setTotalFrame(regionalDataBean.getTotalFrame())   // echo
        .setCurrentFrame(regionalDataBean.getCurrentFrame()) // echo
        .setSubCmd(2)                                   // ★ subCmd=2 = ack/next-frame
        .build()
).build(), 24, true, "...");
```

Same proto as `synchronizeHashData` but `subCmd=2` and echoes everything. **Sent on every incoming frame including the final one** (see `setRegionalData :1219`: `if (!this.areaListMap.containsKey(str2)) { this.maCommandHelper.getRegionalData(regionalDataBean); }`). The `areaListMap.containsKey` test means the ack is only suppressed for duplicate frames — first-arrival always acks.

After the ack, the 12333 retry timer is rearmed for 3 s **unless** this is `action=8 + type=3` (charging-pile area-to-transfer flow), which has its own timing.

If `result == 1`, the ack is re-sent once (`:1259`) and then the code takes various paths based on action/type.

### `getHashResponse(total, current)` — `MACommandHelper.java:896` — THE ROOT-LIST PER-FRAME ACK

```java
sendOrderMsg_Nav(MctrlNav.MctlNav.newBuilder().setTodevGethash(
    MctrlNav.NavGetHashList.newBuilder()
        .setPver(1)
        .setSubCmd(2)
        .setCurrentFrame(i4)
        .setTotalFrame(i3)
        .build()
).build(), 21, true, "...");
```

Same field as `getAllBoundaryHashList` (`nav.todev_gethash`), but `subCmd=2`. **Sent on every frame including the final**, unconditionally (`setHashList :1140`).

### `getLineInfoList(hashList, transactionId)` — `MACommandHelper.java:905`

```java
sendOrderMsg_Nav(MctrlNav.MctlNav.newBuilder().setAppRequestCoverPaths(
    MctrlNav.app_request_cover_paths_t.newBuilder()
        .setPver(1)
        .addAllHashList(list)                           // up to 20 hashes per batch
        .setTransactionId(j3)                           // System.currentTimeMillis()
        .setSubCmd(0)
        .build()
).build(), 34, true, "...");
```

Field: `nav.app_request_cover_paths`. **Batch size capped at 20** (see `getNoLineHash :508`). Reply: `cover_path_upload_t` frames with the same `transaction_id`.

### `sendResponseSvgDate(bean)` — `MACommandHelper.java:1355`

```java
sendOrderMsg_Nav(MctrlNav.MctlNav.newBuilder().setTodevSvgMsg(
    MctrlNav.svg_message_ack_t.newBuilder()
        .setPver(1)
        .setSubCmd(2)
        .setTotalFrame(svgDataBean.getTotalFrame())
        .setCurrentFrame(svgDataBean.getCurrentFrame())
        .setDataHash(svgDataBean.getDataHash())
        .setPaternalHashA(svgDataBean.getPaternalHashA())
        .build()
).build(), 137, true, "...");
```

There is **no separate "start SVG fetch" command** — the APK only sends acks (`subCmd=2`). SVG is pushed unsolicited by the device via the area's parent-hash relationship.

### `getDynamicsLine()` — `MACommandApiHelper.java:941`

```java
public void getDynamicsLine() throws JSONException {
    long now = System.currentTimeMillis();
    if (now - AppCache.dynamicsLineOrderTime < 3000) return;   // 3 s rate-limit
    AppCache.dynamicsLineOrderTime = now;
    sendOrderMsg_Nav(MctrlNav.MctlNav.newBuilder().setTodevGetCommondata(
        MctrlNav.NavGetCommData.newBuilder()
            .setPver(1).setAction(8).setSubCmd(1).setType(18)
            .build()
    ).build(), 231, true, "...");
}
```

LUBA_HM / Yuka-mini live-mowed-line stream. Action=8, type=18. Reply dispatches to `updateDynamicsLine`.

### NOT part of fetch (despite appearances)

- `getLineInfo(hash)` (`:900`) — `nav.todev_zigzag_ack`, used for line regeneration, not fetch
- `bidire_reqconver_path` reception — handled by `routeResponse`, that's the generation result
- `NavEdgePoints` / `updateEdgewiseMapping` — first-mapping border preview, not saved-map fetch
- `getAreaNameList(deviceId)` (`:1972`) — called after areas load (`:790, :1352, :1439`), but not part of frame state machine

## 4. Incoming handlers

### `setHashList(bean)` — `HashDataManager.java:1125`

Dispatched on `nav.toapp_gethash_ack` (2.2.4.13 `MACarDataManager.java:3171` case 13).

```java
public void setHashList(HashListBean bean) {
    if (this.hashListBeanString.equals(bean.toString())) return;       // dedup
    this.hashListBeanString = bean.toString();
    if (bean.getPver() == 0) return;                                    // ignore pver=0 frames

    int currentFrame = bean.getCurrentFrame();
    int totalFrame = bean.getTotalFrame();

    // ACK EVERY FRAME including final
    if (maCommandHelper != null) {
        maCommandHelper.getHashResponse(totalFrame, currentFrame);
    } else {
        this.hashListBeanString = "";                                   // reset dedup so we're not stuck
    }

    // Frame 1: clear the appropriate list
    if (currentFrame == 1) {
        switch (bean.getSubCmd()) {
            case 0: hashList.clear(); break;
            case 3: lineHashList.clear(); break;
            case 4: dumpHashList.clear(); break;
            case 5: noVisionList.clear(); break;
        }
    }
    // Every frame: append
    if (bean.getPath() != null) {
        switch (bean.getSubCmd()) {
            case 0: hashList.addAll(...); break;
            // (3,4,5 similar)
        }
    }
    // Final frame: kick the next phase
    if (currentFrame == totalFrame) {
        switch (bean.getSubCmd()) {
            case 0:
                updateMapElementDB(false);  // diff vs local; seed noHashList; getHashAre()
                this.number = 0; this.numberRegion = 0; return;
            case 3:
                updateMapLineDB();          // seed noLineHashList; getHashLineNew()
                this.numberLine = 0; break;
            case 4: updateDumpDB(); break;
            case 5: updateNoVisionDB(); break;
        }
    }
}
```

### `setRegionalData(bean, deviceState)` — `HashDataManager.java:1204`

Dispatched on `nav.toapp_get_commondata_ack` (2.2.4.13 `MACarDataManager.java:2797` case 5). The 2.2.4.13 dispatcher does pre-routing based on action/type **before** calling `setRegionalData`:

```java
// From 2.2.4.13 MACarDataManager.java lines 2871-2912:
if (action == 12 && type == 12) hashDataManager.recoverAreaOutDumpingData(bean); return;     // dump completion
if (action == 24)               RxBus.post(new ActionBean(action, result, type)); return;
if ((action == 19 && type == 0) || (action == 21 && type == 17))
                                 RxBus.post(new RotationBean(...)); return;
if (action == 0 && type == 5)   RxBus.post(new RotationBean(...)); return;
if (action == 8 && type == 18)  hashDataManager.updateDynamicsLine(bean); return;            // dynamic line
if (action == 12 && type == 20) RxBus.post(bean); hashDataManager.setRegionalData(bean, ds); return;
if (action == 12 || action == 13 || action == 20)
                                 bleDataUpdateListener.updateDataSynchronization(bean); RxBus.post(bean); return;
// otherwise:
hashDataManager.setRegionalData(bean, deviceState);
```

The `setRegionalData` decision tree itself:

```java
try {
    int action = bean.getAction(), type = bean.getType();
    int totalFrame = bean.getTotalFrame(), currentFrame = bean.getCurrentFrame();
    String key = bean.getHash() + ":" + currentFrame + ":A";

    // STEP 1: ACK unless duplicate. Then rearm 12333 unless action=8/type=3.
    if (maCommandHelper != null) {
        if (!areaListMap.containsKey(key)) maCommandHelper.getRegionalData(bean);
        if (!(action == 8 && type == 3)) sendHandler(12333, 3000);
    }
    // STEP 2: empty path + action 8 → skip this hash entirely
    if (bean.getPath().isEmpty() && action == 8) {
        numberRegion++; noHashIndex++; getHashAre(); return;
    }
    // STEP 3: hash-mismatch filter (UNLESS deviceState==MODE_SECOND_EDIT, OR getNoHash()==0,
    //         OR action==8/type==3, OR action==0/type==12)
    if (deviceState != MODE_SECOND_EDIT && getNoHash() != 0 && !(action == 8 && type == 3)) {
        if (!(action == 0 && type == 12)) {
            if (bean.getHash() != getNoHash()) return;   // DROP — wrong hash
        }
    }
    // STEP 4: dump completion
    if (action == 12 && type == 12) { recoverAreaOutDumpingData(bean); return; }

    // STEP 5: result != 0
    if (bean.getResult() != 0) {
        if (bean.getResult() == 1) {
            maCommandHelper.getRegionalData(bean);                  // re-ack
            if (action == 6 && type == 5) RxBus.post(event 26);     // RTK reset
            CommonDBHelper.getInstance().deleteShortTimeDumpPointDB(...);
            if (type == 12)              { RxBus(event 23, hash); return; }
            if (action == 0 || action == 1) { RxBus(event 8, bean); return; }
            if (action == 6) {
                hashListBeanString = "";
                maCommandHelper.getAllBoundaryHashList(0, 1);       // re-fetch root list!
                return;
            }
            return;
        }
        return;                                                     // silent drop
    }
    // STEP 6: result==0
    removeHandler12333(false);
    // STEP 7: dedup
    if (areaListMap.containsKey(key)) return;
    // STEP 8: action 16 (hide/show graphics) — mutate, RxBus(27), return
    if (action == 16) { /* ... */ return; }
    // STEP 9: action 6/type 5
    if (action == 6 && type == 5) RxBus.post(event 25);

    // STEP 10/11: action != 6 && action != 2 → ASSEMBLE PATH
    if (action != 6 && action != 2) {
        // 11a. First frame: start event
        if (currentFrame == 1 && !areaListMap.containsKey(key)) {
            if (bean.getSubCmd() == 2) { RxBus(event 4, bean); return; }   // generation result, not fetch
            else { RxBus(event 5, bean); mapElementBean = new MapElementBean(); }
        }
        // 11b. MODE_SECOND_EDIT + action 0 + type 0 → area-name refresh
        if (deviceState == MODE_SECOND_EDIT && action == 0 && type == 0) {
            RxBus(event 19, bean + deviceName);
            maCommandHelper.getAreaNameList(iotId);
        }
        // 11c. Store frame
        if (!areaListMap.containsKey(key)) areaListMap.put(key, bean.getPath());
        // 11d. Last frame → assemble + persist
        if (currentFrame == totalFrame) {
            ArrayList full = new ArrayList();
            if (areaListMap.size() == totalFrame) {
                isPerfect = true;
                for (int i = 1; i <= areaListMap.size(); i++)
                    full.addAll(areaListMap.get(hash + ":" + i + ":A"));
            } else { isPerfect = false; }
            areaListMap.clear();
            RxBus(event 6, full);
            if (action == 0 || action == 1) {
                if (!isPureRadar() && !isX5DeviceTyp()) RxBus(event 7);
            }
            if (action == 1 && type == 12) {
                CommonDBHelper.saveAllShortTimeDumpPoint(iotId);
                RxBus(event 22);
            }
            if ((action == 8 && type == 3) || action == 10) return;

            // Persist
            mapElementBean.setHash(...); mapElementBean.setBorder(full); /* ... */
            if (isSupportDynamicsLine()) mapElementBean.setDeleteState(2);                  // ★ LUBA_HM: draft
            else if (type == 12 && pHashA==0 && pHashB==0) mapElementBean.setDeleteState(1);
            else mapElementBean.setDeleteState(0);
            // ...
            boolean shouldSave = hash != 0 && !full.isEmpty() && isPerfect &&
                (isSupportDynamicsLine() ? true : !LitePal.isExist(MapElementDB.class, ...));
            if (shouldSave) {
                MapElementDB saved = saveMapElement(mapElementBean);
                if (saved != null && saved.getType() == 0 && !DeviceWorkState.valueof(deviceState).noAddAreaName())
                    maCommandHelper.getAreaNameList(iotId);
            } else if (type == 12) saveMapElement(mapElementBean);

            // Advance
            if (isSupportDynamicsLine()) sendHandler(12333, 0);                              // ★ LUBA_HM: immediate
            else                          RxBus(event 2);
            if (action == 8) {                                                               // ★ only action=8 advances
                noHashIndex++; getHashAre(); return;
            }
            return;
        }
        return;
    }
    // action == 6 or 2 → dump-rollback event 3
    RxBus(event 3, bean);
    if (action != 6) return;
    isUpdateMap = false;
} catch (Exception e) { /* ... */ }
```

**Two critical observations:**

1. **`noHashIndex` advances ONLY on `action == 8` final frame** (`:1452`) — the response to the explicit `synchronizeHashData` we sent. Frames with other actions (0/6/16/...) do not advance the cursor. The next area is only requested when 12333 fires OR when the dynamics-line-branch hits `sendHandler(12333, 0)` (`:1448`).

2. **The hash-mismatch filter (`:1245`) silently drops frames** for any other hash than the one currently being awaited. **But the ack at the top of the function was already sent** because the dedup key (`areaListMap.containsKey(key)`) is hash-scoped. So a stray frame for a different hash *is* acked back, *and then dropped from assembly*.

### `updateGraphicsData(svg)` — `HashDataManager.java:1653`

`nav.toapp_svg_msg` with `subCmd == 2`. (subCmd == 1 is published to RxBus, bypassing HashDataManager.)

- Hash-mismatch filter (`:1659`): if `getNoHash() != 0 && svg.dataHash != getNoHash()` → drop.
- `result == 1` → re-send `sendResponseSvgDate` once and return.
- `result == 0` → `removeHandler12333(false)`; ack; rearm 12333 for 3 s.
- Dedup `areaGraphicsListMap[key]` with `"<dataHash>:<currentFrame>:A"`.
- Final frame: reassemble, NativeLib parse, persist, **`noHashIndex++; getHashAre();`** (`:1758`). SVG completion advances cursor.

### `setRouteList(info)` — `HashDataManager.java:1475`

```java
if (this.transactionId != info.getTransaction_id()) {
    removeHandler(100001); sendHandler(100001, 10000); return;
}
if (info.getResult() != 0) return;
if (info.getCurrentFrame() == 1 && lineKeyStringList.isEmpty()) lineList.clear();
String key = info.getDataHash() + ":" + info.getCurrentFrame();
if (lineKeyStringList.contains(key)) return;
removeHandler100001(false);
lineKeyStringList.add(key);
for (PathPacketBean p : info.getPathPacketList())
    lineList.put(p.path_hash + ":" + p.path_cur, p.dataCouple);
// For each unique path_hash, check if all path_total chunks arrived; if so assemble + save
if (info.getCurrentFrame() == info.getTotalFrame()) getHashLineNew();
sendHandler(100001, 4000);
this.isUpdateFailed = false;
```

### `recoverAreaOutDumpingData(bean)` — `:1006`

`action == 12 && type == 12`. Same frame-by-frame pattern: ack, store in `areaListMap`, on final frame assemble + persist. **Does not advance `noHashIndex`.**

### `updateDynamicsLine(bean)` — `:1582`

`action=8, type=18`. Acks each frame. Buffer keyed `"<hash>:<current>:L"`. Final frame fires `HashDateEvent` type 30 only if device is working (`isWorkingStatusMN231`).

### `updateEdgewiseMapping(bean)` — `:1645`

`nav.toapp_edge_points`. Single-shot, no frame state. Fires event 28.

### `routeResponse(pathHash)` — `:1093`

`nav.bidire_reqconver_path` when subCmd==0. If pathHash matches local mPathHash, either accept or call `getLineHashList(2)`. `pathHash == 0` → `loadingLineProgress3(100,100)`.

## 5. Timers — exhaustive

| What | Initial delay | Rearm | Max | Effect |
|------|---------------|-------|-----|--------|
| `12333` | 5000 ms after `synchronizeHashData` (:328) | 3000 ms after each `getRegionalData` ack (:1222, :1677, :1022); **or 0 ms when `isSupportDynamicsLine` after final frame** (:1448) | `numberRegion >= 10` → stop (:108) | Increment `numberRegion`; `getHashAre()` |
| `12334` | 0 ms for dynamics, 300 ms otherwise (:732, :734) | one-shot | `number >= 10` → stop (:118) | Increment `number`; `updateMapElementDB(true)` |
| `100001` | 6000 ms after `getLineInfoList` (:433); 4000 ms after each `setRouteList` frame (:1553); 10000 ms on txn-id mismatch (:1479) | yes | `numberLine >= 10` → set `isUpdateFailed=true` (:153) | Increment `numberLine`; `isAddLine=false`; `getHashLineNew()` |
| `100003` (`handlerType_getDynamicsLine`) | 10000 ms after first `getDynamicsLineCommand` (:873, :133) | 10000 ms each fire | none | If working: `getDynamicsLineCommand()` and rearm |
| `86018` `DEVICE_GENERATE_LINE_PROGRESS` | 0 (sent immediately :257) | n/a | n/a | UI progress nudge |
| `86019` `DEVICE_GENERATE_LINE_TIME_OUT` | `CHECK_DEVICE_VERSION_TIME` ms (:258) | n/a | n/a | UI timeout |
| `86020` `DEVICE_GENERATE_LINE_COMPLE` | 5000 ms (:559, :965) | n/a | n/a | UI dismiss |
| `86021` `DEVICE_GENERATE_LINE_TIME_OUT_GET` | 10000 ms (:648) | n/a | n/a | UI timeout |

Only **12333, 12334, 100001, 100003** are protocol-relevant. 86018-86021 are UI.

### 12333 in detail (area-fetch heartbeat)

After `synchronizeHashData(hash)`: arm 12333 @ 5s. Each frame ack rearms to 3s. If timer fires before next frame:
- `numberRegion >= 10` → stop, **no advance**, leaves saga stuck (UI checks `isGetAreaFailed`).
- Otherwise `numberRegion++; getHashAre()`. Inside `getHashAre`:
  - If `now - mapHashTime[hash] < 100 ms`: skip (timestamp overwritten anyway).
  - Else: `areaListMap.clear(); removeHandler12333(false); synchronizeHashData(hash); arm 12333 @ 5s`.

Per-area worst-case: `5s + 9*3s ≈ 32 s` before give-up.

### 12334 (DB-reconcile loop)

Fires from `setHashList` final-frame subCmd=0 → `updateMapElementDB(false)` → if `mapElementList.size() == hashList.size()` OR `>` (`:709`) → `sendHandler(12334, 0)` for dynamics or `(12334, 300)` otherwise. Handler then calls `updateMapElementDB(true)` (skips re-stamp of `mapHashOrder`, re-checks local vs device hash). If still mismatched, seeds `noHashList` and `getHashAre()`. Single fire per arm.

### 100001 (line-fetch heartbeat)

`getLineInfoList(batch, txn)` → arm @ 6s. Each `setRouteList` frame extends to 4s. Fire:
- `numberLine >= 10`: stop, `isUpdateFailed=true`.
- Else `numberLine++; isAddLine=false; isUpdateFailed=false; getHashLineNew()`.

Transaction-ID mismatch rearms to 10s.

## 6. Retry / advance logic

### `noHashIndex` cursor

Advances:
- `getHashAre :335` when current entry is 0L (skip zero-entries).
- `setRegionalData :1228` — empty path on action 8.
- `setRegionalData :1452` — final frame on action 8.
- `updateGraphicsData :1758` — final SVG frame.

Resets:
- `getHashAre :339` — list exhausted.
- `updateTotalHash :1814` — bolHash == 0.

**The cursor does NOT advance on per-frame data, only on completion of the explicit `action=8` request, or SVG completion.**

### Give-up conditions

- `numberRegion >= 10` → `removeHandler12333(false)` (counter NOT reset). `isUpdateMap` stays true. **Potentially stuck — UI surfaces via `isGetAreaFailed`.**
- `number >= 10` → 12334 stops, also no auto-rearm.
- `numberLine >= 10` → `isUpdateFailed=true; removeHandler100001(true)`. UI surfaces via `isGetLineFailed`.

### Mid-fetch restart

Only one path: `setRegionalData` with `result==1 && action==6`:
```java
this.hashListBeanString = "";
maCommandHelper.getAllBoundaryHashList(0, 1);    // re-fetch root list
```

### The 100 ms throttle (`getHashAre :319`)

```java
long now = System.currentTimeMillis();
long last = mapHashTime.containsKey(hash) ? mapHashTime.get(hash) : 0L;
if (hash != 0) {
    if (now - last > 100) {
        areaListMap.clear();
        if (numberRegion > 10) { removeHandler12333(false); return; }
        if (maCommandHelper != null) {
            removeHandler12333(false);
            maCommandHelper.synchronizeHashData(hash);
            sendHandler(12333, 5000);
        }
    }
    mapHashTime.put(hash, now);
}
```

**This is not a rate-limit on retries** (12333 rearms cleanly). It's a **debounce on `getHashAre` being called within 100 ms of itself for the same hash**. The race it protects: a 12333 fire + a `sendHandler(12333, 0)` from `:1448` (LUBA_HM dynamics-line completion path). Without the debounce, two `synchronizeHashData` calls would fire in rapid succession.

## 7. Final-frame handling — THE relevant question for our bug

When `setRegionalData` receives `currentFrame == totalFrame` for a normal area (action != 6/2, action != 8/type 3, result == 0):

```java
// ack was sent at top of function (:1219)
removeHandler12333(false);                       // cancel pending retry
areaListMap.put(key, bean.getPath());            // store final frame
if (currentFrame == totalFrame) {
    // assemble all frames in order; clear areaListMap; persist
    if (isSupportDynamicsLine()) sendHandler(12333, 0);       // ★★ immediate next-area request
    else                          RxBus.post(event 2);
    if (action == 8) {
        noHashIndex++;
        getHashAre();                            // synchronous next-area trigger
        return;
    }
}
```

**Critical LUBA_HM observation:** because `LUBA_HM.isSupportDynamicsLine() == true`, on every area completion (action=8 always when we asked via `synchronizeHashData`), the APK does BOTH:
- `sendHandler(12333, 0)` — schedule `getHashAre` on the looper
- `noHashIndex++; getHashAre()` — call it synchronously now

The first call (synchronous) advances + sends the next `synchronizeHashData`, stamping `mapHashTime[nextHash]=now`. The second call (looper ~0 ms later) sees `now - mapHashTime[nextHash] < 100 ms` and is debounced out. **This is exactly what the 100 ms throttle exists to handle.**

For non-dynamics devices (Luba 1, Luba 2), there's no immediate `sendHandler(12333, 0)`. The advance still happens because `:1452-1454` does `noHashIndex++; getHashAre();` synchronously after persist — the 12333 timer being dead is fine since the advance is in-handler.

**Does the APK ack the final frame?** Yes — step 1 unconditionally sends `getRegionalData(bean)` (subject to `areaListMap.containsKey(key)` dedup, which is false for first-arrival). The ack has `subCmd=2` and echoes back action/type/hash/totalFrame/currentFrame. **This is true even when currentFrame == totalFrame.**

**Is the final-frame ack interpreted as "send next" by the device?** Almost certainly no — the device's state is `currentFrame == totalFrame`, it has no next frame for this hash. The ack is informational. The device decides based on its own (current,total) state. **However**: if the device retransmits the final frame (e.g. didn't hear ack on N-1), the APK sees `areaListMap.containsKey(key) == true` and does NOT re-ack. That silent ignore is fine because by then the next area's `synchronizeHashData` is already in flight via `:1452-1454`.

## 8. Per-device branches

`HashDataManager.isSupportDynamicsLine(device)` branches:
- `:306, :368` (`getHashAre` exhaustion) — also `deleteMapElementDB(iotId, 1)` and RxBus(event 2)
- `:724, :751` (`updateMapElementDB`) — `deleteMapElementDB231(...)` instead of `deleteMapElementDB(...)`
- `:731` — `sendHandler(12334, 0)` vs `(12334, 300)`
- `:1410` (`setRegionalData` final) — `setDeleteState(2)` (draft) vs `(0)`
- `:1432` — `shouldSave = isSupportDynamicsLine() ? true : !LitePal.isExist(...)` — dynamics always re-save
- `:1447` — `sendHandler(12333, 0)` immediate-fire vs `RxBus(event 2)`

`isPureVisual()` — `updateTotalHash :1796` clears `noHashList` and removes 12333 aggressively on every bolHash change.

`isPureRadar() || isX5DeviceTyp()` — `setRegionalData :1382` skips the secondary `RxBus(event 7)`.

`isLuba1()` — `MACommandHelper.getAreaNameList` returns early — Luba 1 doesn't fetch area names.

**LUBA_HM membership** (from `DeviceType.java:603-607`):
- `isSupportDynamicsLine` ⇒ **true** (along with YUKA_MINIV, YUKA_MN100, LUBA_MB, LUBA_LA, YUKA_ML, LUBA_ME, CM900, and post-1.15.3.4422 LUBA_VA)
- `isSupportNoAreaWorkDeviceModel` ⇒ **true**
- `isSupportFillLight` ⇒ true
- Not pure-visual, not pure-radar, not Luba 1

## 9. Likely root causes of the `toapp_get_commondata_ack` timeout

Most-likely-first:

1. **No per-frame ack with `subCmd=2`** — the APK acks every `toapp_get_commondata_ack` frame via `nav.todev_get_commondata{subCmd=2, action=<echo>, type=<echo>, hash=<echo>, totalFrame=<echo>, currentFrame=<echo>}`. The device's contract is "I send a frame, you tell me 'got it, send next.'" If pymammotion treats `toapp_get_commondata_ack` as a single response and waits on assembly without acking, the device stops talking after frame 1.

2. **Wrong subCmd on the ack.** Initial pull = `subCmd=1, action=8`. Ack = `subCmd=2, action=8 (echoed)`. If the saga's ack uses subCmd=1 again, the device may treat each ack as a new fetch request, or just ignore the ack and stop sending.

3. **No `getHashResponse(total, current)` on the root hash list.** Same per-frame-ack contract for `toapp_gethash_ack`. If missing, the device may not send subsequent frames of the root list — but then we'd time out on `toapp_gethash_ack`, not `toapp_get_commondata_ack`.

4. **`pver` missing.** Every map-fetch field carries `pver=1`. APK silently drops `pver=0` frames (`setHashList :1133`). The device may also silently drop our outgoing `pver=0` requests.

5. **Parallel fetch vs. action-8 cursor discipline.** APK calls `synchronizeHashData` for one hash at a time and only advances `noHashIndex` on the `action=8` final frame. If pymammotion pre-fetches multiple hashes concurrently, the device may multiplex frames and the hash-mismatch filter (`:1245`) drops most of them.

6. **Final-frame ack omitted.** APK always sends it. Removing it shouldn't hang the saga unless the saga uses the ack as its synchronisation point.

7. **LUBA_HM `sendHandler(12333, 0)` not replicated.** If the saga has long inter-area delays vs the APK's "immediate next" cadence, the device may close the stream. Unlikely as sole cause.

**Top recommendation:** verify item 1 first. The per-frame `subCmd=2` echo-ack is the contract; without it, the device stops sending after frame 1, which produces exactly the "timeout on `toapp_get_commondata_ack`" symptom.

## 10. Sequence diagram — typical area fetch

```
                    App (HashDataManager)                            Device
                            │                                          │
  updateTotalHash detects bolHash change                               │
                            │                                          │
      getAllBoundaryHashList(0, 2) ─────────────────────────────────► │
      nav.todev_gethash{pver=1, subCmd=0}                              │
                            │                                          │
                            │  ◄──── nav.toapp_gethash_ack[1/N]        │
      setHashList(f=1, sub=0, tot=N)                                   │
      hashList.clear(); hashList.addAll(path)                          │
      getHashResponse(N, 1) ────────────────────────────────────────► │
      nav.todev_gethash{pver=1, subCmd=2, current=1, total=N}          │
                            │                                          │
                            │  ◄──── nav.toapp_gethash_ack[2/N]...[N/N]│
      setHashList → ack each; on final: updateMapElementDB(false);     │
      noHashList = hashList \ localDB; getHashAre()                    │
                            │                                          │
      synchronizeHashData(H0) ──────────────────────────────────────► │
      nav.todev_get_commondata{pver=1, action=8, hash=H0, subCmd=1}    │
      arm 12333 @ 5s; mapHashTime[H0]=now                              │
                            │                                          │
                            │  ◄──── nav.toapp_get_commondata_ack      │
                            │      {action=8, type=0, hash=H0,         │
                            │       subCmd=?, total=M, current=1,      │
                            │       path=[...], pHashA, pHashB}        │
      setRegionalData(f=1)                                             │
      areaListMap["H0:1:A"] = path                                     │
      getRegionalData(echo) ─────────────────────────────────────────► │
      nav.todev_get_commondata{pver=1, action=8, type=0, hash=H0,      │
                               subCmd=2, total=M, current=1}           │
      12333 rearmed @ 3s                                               │
                            │                                          │
                            │  ◄──── ack[2/M], ..., ack[M/M]           │
      each: setRegionalData → store + getRegionalData ack              │
                            │                                          │
      on frame M/M: isPerfect=true; assemble; saveMapElement;          │
      areaListMap.clear()                                              │
      [LUBA_HM dynamics] sendHandler(12333, 0)  [other] RxBus(2)       │
      noHashIndex++; getHashAre()                                      │
                            │                                          │
      synchronizeHashData(H1) ──────────────────────────────────────► │
                            │   ...repeat for each hash...             │
                            │                                          │
      After last area: noHashList empty                                │
      getHashAre exhausted: hashListBeanString=""; isUpdateMap=false;  │
      removeHandler12333(true); [dynamics] deleteMapElementDB(type=1)  │
      RxBus event 2                                                    │
                            │                                          │
      (Later, after report shows bolHash matches local AND pathHash>1) │
      updateTotalHash → getLineHashList(1)                             │
      getAllBoundaryHashList(3, 3) ─────────────────────────────────► │
                            │   ... line root list arrives...          │
      setHashList(sub=3) → updateMapLineDB → getHashLineNew            │
      getLineInfoList([h1..h20], txn) ──────────────────────────────► │
      arm 100001 @ 6s                                                  │
                            │                                          │
                            │  ◄──── cover_path_upload[1/Q]            │
      setRouteList → store; if all path_total chunks: persist DB       │
      100001 rearmed @ 4s                                              │
                            │   ...repeat...                           │
                            │  ◄──── cover_path_upload[Q/Q]            │
      getHashLineNew (reconcile)                                       │
      if all accounted: done                                           │
```

There's **no "I'm done" message** from the device. End-of-fetch is detected on the app side by `noHashList` being empty in `getHashAre`. Likewise for lines via `getHashLineNew`.

## 12. Map sync determination — `getDBCmHash` and `getIsUpdateMapElement`

### `getDBCmHash()` (HashDataManager.java:861)

```java
public Long getDBCmHash() {
    List<MapElementDB> list = CommonDBHelper.getInstance().getMapElementList2(deviceId);
    ArrayList<Long> hashes = new ArrayList<>();
    for (MapElementDB el : list) hashes.add(el.getHash());
    return hashes.isEmpty() ? 0L : MurMurHashUtil.hashUnsigned(hashes);
}
```

Queries the **local DB** for every saved `MapElementDB` row and MurMur-hashes their hash values.
Only fully-received areas are saved (guarded by `isPerfect` — see §4); therefore `getDBCmHash()`
naturally reflects only complete areas, with no separate completeness check needed.

### `getIsUpdateMapElement()` / `getIsUpdateMapElement1()` (HashDataManager.java:923)

```java
public boolean getIsUpdateMapElement() {
    long db = getDBCmHash();
    return db != this.bolHash && this.bolHash != 0;   // true = needs update
}
public boolean getIsUpdateMapElement1() {
    long db = getDBCmHash();
    return db != this.bolHash && this.bolHash != 0;   // identical in practice
}
```

The APK's single sync gate: **`localHash != deviceBolHash && deviceBolHash != 0`**.

Because `getDBCmHash()` only counts fully-fetched areas, this one comparison encodes three things:
1. Root hash list is current (otherwise fetched hashes don't match device's set).
2. All declared areas are fully downloaded (incomplete areas never reach the DB).
3. bol_hash is valid (non-zero).

The APK does **not** separately check `area_name` hashes against the root hash list — that list
is for display only and plays no part in sync gating.

### Line fetch gate (same method, lower block)

```java
// line fetch only starts once areas are synced:
if (j3 == getDBCmHash().longValue() && this.isUpdateMap) this.isUpdateMap = false;
if (this.mPathHash == j4 || this.isUpdateMap || j3 != getDBCmHash().longValue()) return;
```

Lines are never fetched while `isUpdateMap` is true (area fetch in progress).  The bolHash must
already equal `getDBCmHash()` before path-hash changes are acted on.

### Equivalent in pymammotion

Our `HashList.computed_bol_hash` uses `area_root_hashlist` (the fetched manifest) rather than
`self.area` (the fetched geometry).  They converge once all areas are downloaded, but diverge
when the root hash list has been fetched but geometry download is still in progress —
`computed_bol_hash` would already equal `bol_hash` while the APK's `getDBCmHash()` would not.

`HashList.is_map_synced(bol_hash)` compensates with an explicit `find_incomplete_hashes(0)` check
so the combined result is equivalent to the APK's single `getIsUpdateMapElement()` call.

### `initBolHash()` — the manual re-prime

```java
public void initBolHash() { this.bolHash = 0L; this.isUpdateMap = false; }
```

Sets stored bolHash to 0 so the next work-report (any non-zero bolHash) triggers a fresh fetch.
HA-Luba's "sync maps" button is the equivalent; there is no device command involved.

## 11. Quick reference — the contract to match

To not time out on `toapp_get_commondata_ack`:

1. Send `nav.todev_get_commondata{pver=1, action=8, hash=H, subCmd=1}` (initial pull).
2. Set 5 s timeout for the *first* frame.
3. For **each** incoming `nav.toapp_get_commondata_ack` frame **including the final one**, send back `nav.todev_get_commondata{pver=1, action=<echoed>, type=<echoed>, hash=<echoed>, subCmd=2, totalFrame=<echoed>, currentFrame=<echoed>}`. Reset timeout to 3 s after each.
4. If no frame within timeout, retry the initial pull. Up to 10 retries (counter `numberRegion`).
5. Final frame = `currentFrame == totalFrame`. Ack is still sent. No additional "done" message.
6. `path` is a chunk per frame; concatenate in `currentFrame` order to get the full polygon.
7. The device may multiplex frames from in-flight requests; discard frames whose hash doesn't match the one currently requested (APK does this via `getNoHash() != bean.hash` filter at `:1245`).

For the root hash list (`toapp_gethash_ack`), the contract is identical but with `nav.todev_gethash{pver=1, subCmd=2, currentFrame, totalFrame}` as the ack.
