# Mammotion APK Timers, Delays, and Periodic Loops

**Source:** Mammotion APK 2.3.8.201 at `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/`.

---

## 1. Map / Hash Fetch Timers (`command/app/HashDataManager.java`)

`HashDataManager` is the single-`Handler` state machine that orchestrates every map-fetch step. Handler in `HashDataManager.java:102-166`.

### Constants

| Constant | Value | Source |
| --- | --- | --- |
| `handlerType_12333` (area frame timeout) | 12333 | `HashDataManager.java:172` |
| `handlerType_12334` (region retry tick) | 12334 | `HashDataManager.java:173` |
| `handlerType_100001` (line frame timeout) | 100001 | `HashDataManager.java:171` |
| `handlerType_getDynamicsLine` | 100003 | `HashDataManager.java:174` |
| `DEVICE_GENERATE_LINE_PROGRESS` | 86018 | `HashDataManager.java:50` |
| `DEVICE_GENERATE_LINE_TIME_OUT` | 86019 | `HashDataManager.java:51` |
| `DEVICE_GENERATE_LINE_COMPLE` | 86020 | `HashDataManager.java:49` |
| `DEVICE_GENERATE_LINE_TIME_OUT_GET` | 86021 | `HashDataManager.java:52` |
| `AppConstants.CHECK_DEVICE_VERSION_TIME` | 120000 ms (120 s) | `utils/constants/AppConstants.java:36` |

### Timer table

| Timer | File:line | Duration | Fires what | Cancelled when |
| --- | --- | --- | --- | --- |
| `12333` after `synchronizeHashData` | `HashDataManager.java:328` (`getHashAre`) | 5000 ms | `getHashAre()` — sends next region in `noHashList`; `numberRegion++`, self-cancels at 10 | Region ack (`setRegionalData` → `removeHandler12333(false)` at `:1292`); SVG ack (`:1673`); `recoverAreaOutDumpingData` (`:1018`); save complete (`:1448`); `noHashList` empty (`:301`); `bolHash` change (`:1800`); `numberRegion > 10` (`:322`) |
| `12333` after `RegionalData` ack | `HashDataManager.java:1022` | 3000 ms | Same | Same |
| `12333` after `setRegionalData` | `HashDataManager.java:1222` | 3000 ms | Same | Same |
| `12333` after save (dynamics-line) | `HashDataManager.java:1448` | 0 ms (immediate MainLooper post-back) | Same | Same |
| `12333` after SVG ack | `HashDataManager.java:1677` | 3000 ms | Same | Same |
| `12334` region retry (dynamics-line) | `HashDataManager.java:732` | 0 ms | `updateMapElementDB(true)` — restart full area DB sync; gives up after 10 retries | `removeHandler12334()` (`:120`); implicitly cancelled on next ack |
| `12334` region retry (default) | `HashDataManager.java:734` | 300 ms | Same | Same |
| `100001` line frame timeout (after `getLineInfoList`) | `HashDataManager.java:433` (`getHashLineNew`) | 6000 ms | `getHashLineNew()` — re-send line query; `numberLine++`, self-cancels at 10 | Frame ack via `setRouteList` → `removeHandler100001(false)` (`:1496`); final completion `removeHandler100001(true)` (`:447`, `:156`) |
| `100001` line frame ID mismatch | `HashDataManager.java:1479` (`setRouteList`) | 10000 ms | Same | Same |
| `100001` next-packet watchdog | `HashDataManager.java:1553` (`setRouteList` tail) | 4000 ms | Same | Same |
| `100003` dynamics-line poll | `HashDataManager.java:133`, `:873` | 10000 ms | `getDynamicsLineCommand()` — request dynamics line; only re-arms while `isWorkingStatus()` true and `iotId` matches first device | `getDynamicsLine` exit when not in working state (`:869`); stops re-arming when `dynamics_line_status` didn't change |
| `86018` DEVICE_GENERATE_LINE_PROGRESS | `HashDataManager.java:257` (`deviceGenerateLineProgress`) | 0 ms | UI tick: mark progress visible | `dissmissProgress` (`:841`), `clearLoadingHandler` (`:221`), `progressTimeOut` (`:994`) |
| `86019` DEVICE_GENERATE_LINE_TIME_OUT | `HashDataManager.java:258` | 120000 ms (`CHECK_DEVICE_VERSION_TIME`) | `progressTimeOut()` — set progress UI to timed-out | `clearLoadingHandler` (`:224`), `loadingLineProgress*` on every line packet (`:527`, `:543`, `:954`) |
| `86021` DEVICE_GENERATE_LINE_TIME_OUT_GET | `HashDataManager.java:648` (`setLoadingTimeOut`) | 10000 ms | `progressTimeOut()` | Any new line packet re-arms; `clearLoadingHandler` (`:227`) |
| `86020` DEVICE_GENERATE_LINE_COMPLE | `HashDataManager.java:559` (`loadingLineProgress2`), `:965` (`loadingLineProgress3`) | 5000 ms | `dissmissProgress()` — fade progress UI after completion | `clearLoadingHandler` (`:230`); `dissmissProgress` itself clears (`:841`) |

### Lifecycle: 12333 / 12334 / 100001 state machines

**Area / region loop.** `updateTotalHash` (`:1780`) is the entry: when device `bolHash` differs from local DB, it calls `getAllBoundaryHashList(0,2)` (`:1811`) and sets `isUpdateMap=true`. The hash list response is processed by `updateMapElementDB` (`:677`):
1. If counts match but hashes differ → fire `12334` (0 ms for dynamics-line firmware, 300 ms for others) — re-runs `updateMapElementDB(true)` up to 10 times.
2. If local DB is missing regions → walk `noHashList` via `getHashAre` (`:296`):
   - Per-hash send throttle: only re-send the same hash if `currentTimeMillis - mapHashTime[hash] > 100 ms` (`:319`). `mapHashTime` stores wall-clock of last send per hash.
   - After each send, arm `12333` for 5000 ms (`:328`). If no response in that window, advances to next hash. `numberRegion++`; gives up at 10.
   - Every region ack removes the 5000 ms watchdog and re-arms it 3000 ms after the next fetch (0 ms for dynamics-line firmware).
3. When `noHashList` empties → `removeHandler12333(true)` (`:301`), resets `numberRegion = 0`.

**Line / path loop (`100001`).** After region sync completes, if breakpoint path hash differs → `getLineHashList(1)` (`:1835`) → `getAllBoundaryHashList(3,3)` (`:484`) → `updateMapLineDB` → `getHashLineNew` (`:411`):
1. Build batch of up to 20 hashes from `noLineHashList` (`getNoLineHash` cap at `:508`).
2. Call `getLineInfoList(arrayList, transactionId)` and arm `100001` for 6000 ms (`:433`).
3. Each `setRouteList` frame ack (`:1475`):
   - If `transactionId` mismatches (stale) → re-send with 10000 ms watchdog (`:1479`).
   - Otherwise remove watchdog, re-arm 4000 ms for next frame (`:1553`).
4. After 10 retries (`numberLine >= 10`) → give up, set `isUpdateFailed = true` (`:154`).

**Dynamics-line poll (`100003`, MN231 only).** 10 s self-rearming poll while mower is in working state and is the active device (`:130-:136`). Started by `getDynamicsLine(j)` (`:858`) when device reports non-zero pathHash; stopped when `isWorkingStatus()` becomes false (`:869`).

### Send-gating / debounce

| Where | Window | Effect |
| --- | --- | --- |
| `getHashAre` `HashDataManager.java:319` | > 100 ms since last send to same hash | Prevents multiple `synchronizeHashData(hash)` sends in <100 ms for the same hash; keyed in `mapHashTime` |
| `setLoadingStatus` `HashDataManager.java:637` | > 500 ms since `compleGetLineTime` | Prevents loading-complete → loading-again UI flicker |
| `isGetAreaFailed` `HashDataManager.java:935` | > 5000 ms since `lastPrintTime` | Log-spam throttle only; does not gate sends |

---

## 2. BLE Keep-Alive & Connection Timers (`command/app/MACarDataManager.java`)

`MACarDataManager` owns the BLE heartbeat state machine. Handler constructed in `:1513` via `createHandler()`.

### Constants

| Constant | Value | Source |
| --- | --- | --- |
| `HANDLER_0_BLUETOOTH_HEART` | 0 | `MACarDataManager.java:1282` |
| `INIT_CONNECT_SUCCESS` (1002) / `INIT_CONNECT_SUCCESS_DELAY` (10003) / `INIT_SAMSUM_PHONE` (1003) | — | `:1284-1288` |
| `HANDLER_DEVICE_SYNC` (10001) / `HANDLER_DEVICE_UPGRADE` (10002) / `HANDLER_DEVICE_OFF_DELAY` (10005) / `HANDLER_CTRL_IOT_TIMEOUT` (10006) | — | `:1286-:1290` |
| `LOOP_SEND_HEART` | 10009 (`MessageConstants.SESSION_INVALID`) | `:1294` |
| `CONNECTINT_BT` / `CRYPTUTIL_BT` / `CONNECTINT_BT_STATE_RESET` | 10011 / 10012 / 10000 | `:1295-:1297` |
| `MSG_RPT_START_TIME_OUT` | 1025 | `:162` |
| `MSG_DATA_TIME_OUT` | 1028 | `:161` |
| `OTA_TIME_OUT` | 1003 | `:1358` |
| `MSG_RPT_START_TIME_OUT_SECOND` (default) | 15000 ms (`AsyncConnectListenerWrapper.TIME_OUT`) | `:1395`, def at `com/aliyun/.../AsyncConnectListenerWrapper.java:25` |
| `MSG_RPT_START_TIME_OUT_SECOND` (after setRequestTimeout, no IoT) | IoT 20000 / BLE 5000 ms | `:5190` |
| `MSG_RPT_START_TIME_OUT_SECOND` (after iotResp) | `max(20000, iotMsgHz+1)` IoT / 5000 BLE | `:5201` |
| `MSG_RPT_START_TIME_OUT_SECOND` (getDataTimeOut) | 10000 ms | `:5366` |
| `MSG_RPT_START_TIME_OUT_SECOND` (requestTimeout) | 20000 ms | `:6123` |
| `DATA_TIMEOUT_VALUE` | 22000 ms | `:1385` |
| `DATA_IOT_TIMEOUT_VALUE` | 22000 ms | `:1386` |
| `SYNC_DEFAULT_TIME` | 20000 ms | `:1291` |
| `MTU_LENGTH_18` | 18 bytes | `:163` |
| `count1_max` (heartbeat ramp counter) | 10 | implicit in `:419` |

### Heartbeat handler (msg `0` — `HANDLER_0_BLUETOOTH_HEART`)

Three-phase BLE keepalive in `:418-:450`:
- `count1 < 3`: send `sendTodevBleSync()` every **1500 ms** (`:436`).
- `3 <= count1 < 6`: send `sendTodevBleSync()` + `sendBleAlive()` every **1500 ms** (`:448`).
- `count1 >= 10`: degraded mode — send `sendTodevBleSync()` every **3000 ms** (`:424`).
- `count1 in [6, 10)`: counter resets to 0, loop pauses until next trigger.

### Other handler timers (MACarDataManager)

| Timer | File:line | Duration | Fires what | Cancelled when |
| --- | --- | --- | --- | --- |
| msg 0 (BLE heart, fast) | `:436`, `:448` | 1500 ms | `sendTodevBleSync()` / `sendTodevBleSync()+sendBleAlive()` | When `count1` exits its band; explicitly only re-armed inside handler |
| msg 0 (BLE heart, slow) | `:424` | 3000 ms | `sendTodevBleSync()` (degraded) | Same |
| msg 5 (sysSetDateTime) | `:458` | 500 ms | `sendSysSetDateTime()` — retries 3 times | Self-stops at `dateTimeNum >= 3` (`:453`) |
| msg 5 (initial) | `:547`, `:648` | 1000 ms | First date-time send after BLE init | Same |
| msg 1025 (`MSG_RPT_START_TIME_OUT`) | `:5196`, `:5207`, `:5219`, `:6126` | 15000 / 20000 / 5000 / `iotMsgHz+1` / 10000 ms (varies — see constants above) | Verifies link is still up; switches to IoT or drops link (`:466-:494`) | `removeMSG_RPT_START_TIME_OUT()` on each fresh report (`:467`); `dispose` (`:5321`) |
| msg 1028 (`MSG_DATA_TIME_OUT`) | `:5371`, `:6481` | 10000 ms | Drop link to `LinkType_NONE` (`:496-:507`) | `removeMessages(1028)` (`:498`); IoT message arrival |
| msg 10001 (`HANDLER_DEVICE_SYNC` — feed-dog tick) | `:5236` (`startDeviceSyncSend`) | 20000 ms | `sendDeviceSyncSend(2)` → sendIotSync or sendBlueToothDeviceSync (`:1706`) | `removeMessages(10001)` in `:5235`, `:6619` |
| msg 10002 (`HANDLER_DEVICE_UPGRADE` — OTA 5s sync) | `:6564` (`startDeviceFiveSync`) | 5000 ms | `startDeviceFiveSync` again | `removeMessages(10002)` (`:6605`) `stopDeviceFiveSync` |
| msg 10003 (BLE init success delay) | post-process at handler (`:606-`) | — | Triggers map subscription | One-shot |
| msg 10006 (`HANDLER_CTRL_IOT_TIMEOUT`) | `:6168` (`sendInitIotDataSync`) | 15000 ms | Notifies IoT switch timeout to listeners (`:588-:597`) | `removeMessages(10006)` (`:6167`, `:6477`) |
| msg 10009 (`LOOP_SEND_HEART` — `startHeartLooper`) | `:5245`, `:6474` | `max(22000, DATA_IOT_TIMEOUT_VALUE)` = **22000 ms** | Feeds dog: re-checks link state, re-subscribes IoT or BLE depending on state (`:677-:716`), then re-arms itself | `removeMessages(SESSION_INVALID)` in `:5244`, `:5321` (dispose); `dispose()` (`:5319`) |
| msg 10011 (`CONNECTINT_BT`) | `:516`, `:618` | 10000 ms | Clear `isBtConnecting = false` (`:510`) | One-shot |
| msg 1002 lambda 0 (MTU set after BLE) | `:526-:531` | 1000 ms | `sendSetMtu()` | Removed on `dispose` |
| msg 1002 lambda 1 (init heart) | `:534-:539` | 1000 ms | First heart-tick | One-shot |
| msg 1002 lambda 2 (`:548-:553`) | 1200 ms | Stage-2 send | One-shot |
| msg 1002 lambda 3 (`:554-:559`) | 1500 ms | Stage-3 send | One-shot |
| msg 10003 lambda 4 (`:626-:631`) | 1000 ms | sendSetMtu post BLE-init-delay | One-shot |
| msg 10003 lambda 5 (`:635-:640`) | 1000 ms | First heart-tick | One-shot |
| msg 10003 lambdas 6/7/8 (`:649-:666`) | 500 ms / 1200 ms / 500 ms | OTA info request stages | One-shot |
| `setErrCode` lambda h (`:1755-:1760`) | 500 ms | RxBus error code post (debounce) | One-shot |
| `requestMapLocationData` lambda e (`:6083-:6088`) | `getPeriod()` ms (from `report_info_cfg.builder.getPeriod()` — device-supplied) | `startIotKeep` → `setRequestTimeout()` to re-arm 1025 | One-shot per call |

### MACarDataManager send throttles (currentTimeMillis-based)

| Where | Threshold | Effect |
| --- | --- | --- |
| `setSystemPackageListener`, `:6432` | `now - feed_dog_interval_20 >= 20000 ms` | Heartbeat / link-status fired at most every 20 s |
| `startDeviceFiveSync`, `:6555` | `now - tiem_five < 5000` → early return | OTA 5 s sync not started more than once per 5 s |
| `deviceLoactTime` checks at `:2256`, `:2624`, `:3244` | `> 3000 ms` | Location-update gating (3 s) |
| `timeDeviceRssi` checks at `:2313`, `:2676`, `:3537`, `:4987` | `<= 900 ms` early return | Device RSSI updates rate-limited to ~1.1 Hz |
| `timeRssi` at `:5773` | `> 900 ms` | RSSI ack also 900 ms |
| `lastPrintTime` (in `HashDataManager`, mentioned above) | 5000 ms | Log throttle |

### BLE init busy-wait loops

| Where | Where called | Body | Note |
| --- | --- | --- | --- |
| `sendInitBTDataSync`, `:1612-:1622` | After BLE link change | `Thread.sleep(1000)`, up to 3 iterations | Synchronous retry under `ThreadPoolManager.executeThread`; each iteration calls `sendBlueToothDeviceSync` |
| `sendInitBTDataSync_Compatible`, `:1626-:1648` | After BLE init compatible | `Thread.sleep(1000)`, up to 3 iterations, then a final send | Same pattern |
| `sendInitIotDataSync`, `:1651-:1663` | After requested IoT switch (also schedules msg 10006 watchdog at `:6168`) | `Thread.sleep(2000)`, up to 2 iterations | Calls `sendIotSync` if not connected |

---

## 3. Connect-link timers (`command/ConnectLinkManage.java`)

UI/connection orchestrator that scans, connects, and falls back. Handler `ConnectLinkHandler` defined in the class.

### Constants
| Constant | Value | Source |
| --- | --- | --- |
| `timeout` | 22000 ms | `ConnectLinkManage.java:57` |
| `MSG_HANDLER_3_DO_CONNECT` | 260 | `:51` |
| `MSG_THREAD_HANDLER_3_DO_CONNECT` | 371 | `:54` |
| `MSG_HANDLER_DISMISS_LOADING_2` | 259 | `:52` |
| `MSG_THREAD_HANDLER_DISMISS_LOADING_2` | 370 | `:55` |
| `MSG_DISMISS_LOADING_POP_46` | 281 | `:49` |
| `MSG_CONNECT_DEVICE_TIMEOUT` | 320 | `:45` |
| `MSG_CONNECT_DEVICE_IOT` | 321 | `:44` |
| `MSG_DELAY_DISS_REFRESH` | 325 | `:48` |
| `MSG_CONNECT_IOT_TIMEOUT` | 326 | `:46` |
| `MSG_CONNECT_LOADING_TIMEOUT` | 337 | `:47` |
| `MSG_DISPOSABLE` | 353 | `:50` |
| `MSG_THREAD_CONNECT_DEVICE_TIMEOUT` | 369 | `:53` |
| `Cea608Decoder.MIN_DATA_CHANNEL_TIMEOUT_MS` | 16000 ms | `com/google/android/exoplayer2/text/cea/Cea608Decoder.java:54` |

### Timer table

| Timer | File:line | Duration | Fires what | Cancelled when |
| --- | --- | --- | --- | --- |
| MSG_DISMISS_LOADING_POP_46 | `:435` (`_connectBleStep2_showLoadingAndScanOrConnect`) | 22000 ms | `dissmissReConnectLoading` + invoke onConnectFail | `removeMessages(MSG_DISMISS_LOADING_POP_46)` (`:434`); link change |
| MSG_HANDLER_DISMISS_LOADING_2 | `:456`, `:486`, `:1161` | 22000 ms | `dissmissReConnectLoading(1)` + status check (`:298`) | `removeMessages(MSG_HANDLER_DISMISS_LOADING_2)` (`:455`, `:479`) |
| MSG_HANDLER_3_DO_CONNECT | `:463`, `:1168` | 3000 ms | Scan again then connect (max 2 retries, `count3`) (`:204-:245`) | `removeMessages(MSG_HANDLER_3_DO_CONNECT)` (`:208`, `:715`); `count3 >= 2` self-stops |
| MSG_HANDLER_3_DO_CONNECT (re-scan no device) | `:238` | 5000 ms | Same | Same |
| MSG_THREAD_HANDLER_3_DO_CONNECT | `:98`, `:347`, `:461`, `:1166` | 3000 / 5000 ms (re-scan) | Same as 260, thread-based variant (`:335-:376`) | `removeMessages(371)` (`:339`, `:357`); `count3 >= 2` |
| MSG_THREAD_HANDLER_DISMISS_LOADING_2 | `:484` | 22000 ms | Loading-fail UI + status check (`:298-:334`) | Implicit on link change |
| MSG_THREAD_CONNECT_DEVICE_TIMEOUT | `:634`, `:846`, `:1022`, `:1252` | 22000 ms | Loading-fail UI + status check (`:284-:296`) | `removeMessages(369)` (`:622`, `:633`) |
| MSG_CONNECT_DEVICE_TIMEOUT | `:889` | 16000 ms (`Cea608Decoder.MIN_DATA_CHANNEL_TIMEOUT_MS`) | Same fail UI as above (`:247-:257`) | Many cancel paths (e.g. `:269`, `:325`, `:420`, `:701`, `:715`) |
| MSG_CONNECT_DEVICE_IOT | `:890` | 3000 ms | `linkManager.setAskBlueToothOpen(1)` (`:261`) | Implicit; one-shot |
| MSG_DISPOSABLE | `:984` | 22000 ms | Same as 281 fail UI (`:247`) | `removeMessages(MSG_DISPOSABLE)` (`:621`) |

### Lifecycle

Connect attempts always pair a "do connect" timer (`260`/`371` — 3 s or 5 s rescan) with a "give up" timer (`259`/`370`/`369` — 22 s). The 22 s watchdog matches the `timeout = 22000` constant. The 16 s `MSG_CONNECT_DEVICE_TIMEOUT` (Cea608 constant reused) is a secondary device-side watchdog scheduled when the connect retry counter `connect_133 != 0`. Max retries: `count3 < 2` (`:209`, `:340`) for connect, `connect_133_max` in `EspBleManager` (default 3 per `:1301`).

---

## 4. BLE scan & ESP BLE manager (`device/source/links/managers/MAScanManager.java`, `EspBleManager.java`)

| Timer | File:line | Duration | Fires what | Cancelled when |
| --- | --- | --- | --- | --- |
| Scan window | `MAScanManager.java:671` | 8000 ms | Stop scan + `_onScaned()` (`:76-:85`) | Manual `stopScan` (`:670`); next `scan()` removes and re-arms |
| Scan debounce | `MAScanManager.java:629` | `> 8000 ms` window | If `isScaning` true and `now - f10147b < 8000`, returns `ScanPermission.none` (no new scan) | Window resets each successful scan |
| Bluetooth state-change debounce | `MAScanManager.java:110`, `:118` | `> 1000 ms` | Suppress duplicate Bluetooth_On / Bluetooth_Off events | — |
| `scanDevice(i3)` next-step | `EspBleManager.java:710` | 4000 ms | Continue connect-after-scan sequence | `removeMessages(i3)` (`:709`) |
| `MessageConstants.GENERIC_SYSTEM_ERROR` connect-watchdog | `EspBleManager.java:838` | 4000 ms | Connect watchdog (system-error trigger) | `closeClient` removes |
| `connectSingleDevice` debounce | `EspBleManager.java:917` | `< 500 ms` window | Early-return — at most one connect attempt per 500 ms | — |
| `setGattWriteTimeout` | `EspBleManager.java:872` | 8000 ms | Built-in GATT write timeout on every connect | Per connection |
| `connectDevice` 133-retry delay | `EspBleManager.java:889-:894` | 300 ms | Re-attempt BlufiClient `.connect()` if `connect_133 != 0` | Self after retry |
| `lambda$onConnectionStateChange` test mode | `EspBleManager.java:464-:469` | 2000 ms | Re-trigger connect in self-test mode only | One-shot |
| `reConnectBle` queue | `EspBleManager.java:704` | 2000 ms | Reconnect (`sendMessageDelayed`, `:701-:704`) | `closeClient(true)` |
| `BlufiClientImpl` write retry sleeps | `BlufiClientImpl.java:1081-:1186` (six sites) | 10 ms each | Tight retry within blufi protocol write/read | Loop body |
| `BlufiClientImpl.sleeptime` slow path | `BlufiClientImpl.java:1042` | `this.sleeptime` | Pacing BLE writes | Loop body |
| `BleConnectThread` reconnect attempt loop | `command/bleconnect/BleConnectThread.java:77` | 10000 ms `Thread.sleep` | Try `newThreadConnectBle` every 10 s while not BT-connected | Thread `pause()` (`:53-:58`) when device becomes connected |

`EspBleManager` uses `maxConnectionNum = 3` (`MACarDataManager.java:1301`) as the per-session reconnect cap. `connect_133_max` (gatt 133 error retry cap) is set in the same constructor (default 3).

---

## 5. Subscription / IoT subscription renewal (`device/source/links/managers/SubscriptionManager.java`)

Single global singleton handler that re-issues `requestMapLocationIOTData` periodically.

| Timer | File:line | Duration | Fires what | Cancelled when |
| --- | --- | --- | --- | --- |
| Subscription renewal — working | `:144`, `:158`, `:172`, `:184` (dynamic) | `time_working` = 120000 ms (`CHECK_DEVICE_VERSION_TIME`) when device state in {10, 11} (`:180`) | Handler msg 0 → `disSubscriptionMsg` + `requestMapLocationIOTData` re-issue if link is IoT and state ≠ 16 (`:36-:48`) | `removeHandlerMsg(0)` on disSubscription (`:102`); device-title change (`:130`) |
| Subscription renewal — idle | `:182` | `time_working = 300000` ms (5 min) | Same | Same |
| Subscription send time_working (BLE link) | `:172`, `:209` | `time_working` ms (whichever bucket) | Same | Same |

Handler payload (`:33-:48`) deliberately reads the link state at fire time, so when MQTT is down it skips re-issuing.

---

## 6. MQTT keep-alive & reconnect

### Mammotion MQTT (post-2025, paho mqttv5) — `maiot_module/MQTTService.java`, `maiot_module/mqtt/MQTTClient.java`

| Setting | Value | Source |
| --- | --- | --- |
| `keepAliveInterval` | 60 s | `MQTTService.java:211` (`.setKeepAliveInterval(60)`) |
| `automaticReconnect` | true | `MQTTService.java:211` (`.setAutomaticReconnect(true)`) |
| `timeout` (connect) | 14 s | `MQTTService.java:211` (`.setTimeout(14)`) |
| `connect()` await | 15 s `CountDownLatch.await(15L, SECONDS)` | `MQTTService.java:269` |
| Reconnect path | `mqttAsyncClient.reconnect()` on disconnect (`:456`); if exception → `mQTTClient.fullReconnect()` (`:471`, `:478`) | `MQTTService.java:445-:480` |

Reconnect interval is internal to paho's `automaticReconnect` (exponential up to `maxReconnectDelay`; default 1 s → 2 → 4 → … up to 128 s). Not statically tunable in this codebase.

### Aliyun IoT MQTT (pre-2025)

No explicit handler-based keepalive in `iot_module/` — Aliyun LinkKit handles keepalive internally with default 30 s ping. Visible feed-dog gating lives at `MACarDataManager.setSystemPackageListener` (20 s) and `startHeartLooper` (22 s; see section 2).

### Token refresh
| Where | Source | Notes |
| --- | --- | --- |
| `MaIoTApp.refreshToken()` | `MaIoTApp.java:803-:805` | Manual coroutine launch — invoked on auth fail; no scheduled refresh |
| `MaIoTApp$refreshToken$1` (suspend body) | `MaIoTApp.java:454-:481` | Reads `refreshToken` from `MaIoTRequestHelper`, calls API; no periodic schedule |

No scheduled JWT/OAuth refresh in the APK — refresh is reactive (on 401/AuthError or when `MaIoTApp.refreshToken()` is invoked manually). pymammotion's TokenManager proactive-refresh schedule is more sophisticated than what the APK does.

---

## 7. Manual control / remote drive send loops

| Loop | File:line | Period | What it sends | Stops when |
| --- | --- | --- | --- | --- |
| `CarRemoteControlManage2` (Yuka-class debug RC) | `command/CarRemoteControlManage2.java:94` | `frequency * 1000 = 200 ms` (`frequency = 0.2f`, `:21`) | `send(3)` — drive command | `linearSpeed == 0 && angularSpeed == 0` → `cancelTimer()` (`:80`) |
| `CarRemoteControlManage` (older path) | `device/deploy/device/manage/CarRemoteControlManage.java:94` | Same `frequency * 1000` | Same | Same |
| `ManualLawnMowingManager` | `map/ManualLawnMowingManager.java:492` | 800 ms RxJava `Observable.interval` | `send(7)` — manual mow command | `cancel()` / `cancel2()` dispose (`:530`) |
| `OperateOnView` | `map/view/OperateOnView.java:544` | 800 ms | `send(7)` | Same pattern as ManualLawnMowingManager |
| `BaseMapFragment.disposablesChargeState` | `map/fragment/BaseMapFragment.java:2893` | 800 ms | UI charge state poll | Fragment dispose |
| `MapManualVideoActivity` charge-state poll | `map/activity/MapManualVideoActivity.java:279` | 800 ms | Same | Activity dispose |
| `MapManualActivityNew` charge-state poll | `map/activity/MapManualActivityNew.java:725` | 800 ms | Same | Activity dispose |
| `LowerThePileFragment` interval | `map/fragment/LowerThePileFragment.java:42` | `f11936g` = 5000 ms (default) or 3000 ms | Pile-lowering progress query | Disposed in `onStop` |
| `SelfRotationGuidanceFragment.disposable1` | `map/fragment/SelfRotationGuidanceFragment.java:172` | `this.time` — switches between 5000 / 60000 / 120000 ms based on state (`:118`, `:125`, `:224`, `:228`) | Position re-query | dispose |
| `RechargeRotationGuidanceLDFragment.disposable1` | `map/fragment/RechargeRotationGuidanceLDFragment.java:170` | Same dynamic `this.time` | Same | dispose |
| `KnifeDiscProgressPop` | `map/view/KnifeDiscProgressPop.java:84` | 450 ms | Knife-disc progress UI tick | Popup close |
| `PlanMapLandFragment` ant-line | `map/fragment/PlanMapLandFragment.java:4063` | 350 ms | Toggle lineDasharray on map (UI only, no send) | Fragment dispose |

`CarRemoteControlManage2` is the canonical send-loop pattern: schedule with `Timer.schedule(task, 0L, delay)` and `cancelTimer()` when both linear and angular are zero.

---

## 8. Map / planning polls

| Timer | File:line | Period | What | Stops when |
| --- | --- | --- | --- | --- |
| `BackupsMapActivity.setDisposable` (backups progress poll) | `map/activity/BackupsMapActivity.java:1357` | 3000 ms (after 0 ms initial) | `getBackupsProgress(bizId, type)` | `it >= 10` → self-stop (`:1362`), or `dispose()` (`:1365`) |
| `HomeFragmentNew` 20s refresh | `home/fragment/HomeFragmentNew.java:4458` | 20000 ms | UI refresh + (if RTK) `commandHelper.getBaseStation()` — see `HomeFragmentNew$initView$2$3.java:38` | `timer.cancel()` on fragment stop |
| `DeviceFragment` 20s refresh | `home/fragment/DeviceFragment.java:1646` | 20000 ms | Same — `commandHelper.getBaseStation()` if RTK + UI refresh | Same |
| `StatusCapsuleUtil` 1s poll | `map/utils/StatusCapsuleUtil.java:87` | 100 ms initial then 1000 ms | Emit current status capsule to RxBus | `dispose()` |
| `MyVideoView` 500 ms tick | `base_module/utils/MyVideoView.java:28` | 500 ms | UI playback time update (no device send) | Disposed |

---

## 9. OTA / firmware update timers (`device/info/OtaCorrelationViewModel.java` + views)

| Constant | Value | Source |
| --- | --- | --- |
| `MSG_OTA_UPGRADE_TIMEOUT` | 2 | `:87` |
| `OTA_TIMEOUT` | 120000 ms (120 s) | `:113` |
| `OTA_TIMEOUT_SW` | 300000 ms (5 min) | `:114` |
| `OTA_TIMEOUT_SW_SD` | 600000 ms (10 min) | `:115` |
| Swimming-pool variant timeout | 180000 ms (3 min) | branch at `:791` |

### OTA timer table

| Timer | File:line | Duration | Fires what | Cancelled when |
| --- | --- | --- | --- | --- |
| OTA progress watchdog (msg 2) | `:226`, `:791`, `:860`, `:901`, `:1023`, `:1027`, `:1029` | `OTA_TIMEOUT` (120s) / `OTA_TIMEOUT_SW` (300s) / `OTA_TIMEOUT_SW_SD` (600s) / 180000 / 50000 ms | Aborts OTA with timeout error | Each progress packet `removeMessages(2)` |
| msg 15 (post-arrival re-check) | `:301`, `:803` | 5000 ms | Re-poll OTA status | One-shot or removed |
| msg 1000 (post-failure recheck) | `:638` | 3000 ms | Retry request | One-shot |
| msg 1200 (`getDeviceOTAInfo` poll) | `:968` | 10000 ms | Poll OTA info | One-shot |
| msg 7 (channel-data wait) | `:725` | 16000 ms (`Cea608Decoder.MIN_DATA_CHANNEL_TIMEOUT_MS`) | OTA channel timeout | — |
| `FirmwareUpdateKTView.startTime` interval | `device/info/view/FirmwareUpdateKTView.java:1310` | 2 s | UI: refresh retry content on `onComplete` (one-shot effective) | `mDisposable.isDisposed()` |
| `FirmwareUpdateView` interval | `device/info/view/FirmwareUpdateView.java:843` | 2 s | Same UI helper | Same |
| `SwimmingPoolUpgradeAndUpLogHelper` post-delays | `device/info/SwimmingPoolUpgradeAndUpLogHelper.java:480, :510, :549` | Various Runnable postDelayed | UI step transitions | One-shot |
| `ErrorDetailActivity` weakHandler msg 0 | `device/info/malfunction/ErrorDetailActivity.java:591` | 5000 ms | Refresh tick | one-shot |
| `ErrorDetailActivity` weakHandler msg 1 | `:586` | 20000 ms | Timeout | one-shot |

---

## 10. Login / auth one-shot timers

| Timer | File:line | Duration | Fires what | Cancelled when |
| --- | --- | --- | --- | --- |
| `LoginsActivity.aliLoginTimeoutRunnable` | `login/activity/LoginsActivity.java:626` | 20000 ms | Login timeout fail UI | login finishes |
| `RegisterAuthCodeActivity` handler msg 0 | `login/activity/RegisterAuthCodeActivity.java:596` | 18000 ms | Auth-code resend timeout | code submitted |

No periodic OAuth refresh — see section 6.

---

## 11. Other timers

| Timer | File:line | Period | Notes |
| --- | --- | --- | --- |
| `DeviceLogService` log-server retry | `feedback/DeviceLogService.java:207` | Initial `delay = 3 s`, exponential `delay *= 3` (→ 9 → 27 s), max `retryCoint = 3` attempts | Retries socket open until 3 fails, then `onStopTime` |
| `ScanAndConBleActivity.timerTask` | `bind/device/scan/ScanAndConBleActivity.java:485-:562` | Per `Timer.schedule(timerTask, period)` | Pairing scan UI refresher |
| `AreaDBHelper.synTaskMagic` retry | `map/p097db/AreaDBHelper.java:624` | 3000 ms `Thread.sleep` | Loop processing pending tasks with 3 s gap between syncs |
| `HomeViewModel.checkLoraNum$lambda$5` | `home/viewmodel/HomeViewModel.java:940` | 5000 ms `Thread.sleep` | One-shot timeout for LoRa duplicate-name check |
| `BatchCacheLiveData.commitRunnable` | `command/message_queue/BatchCacheLiveData.java:83` | 50 ms `postDelayed` | Coalesce batched LiveData commits (50 ms debounce) |
| `DeviceStateFragment.autoWakeUpRunnable` | `home/fragment/DeviceStateFragment.java:2647` | 2000 ms | Auto-wakeup after `setShowLockState` |
| `DeviceStateSwimmingPoolSPFragment` | `:1787` | 2000 ms | Same shape |
| `BluetoothStateBroadcastReceive` (1 s debounce) | `MAScanManager.java:110`, `:118` | 1000 ms | Suppress duplicate Bluetooth on/off broadcasts |
| `ConnectLinkManage.showtime` | declared at `:77`, `0L` initial | — | Not periodic — gate variable; no schedule found |

---

## 12. Summary of cadences relevant to pymammotion sagas

For mirroring the APK's wire timing inside `pymammotion`, the most important values are:

- **Map area frame retry watchdog: 5000 ms** (`HashDataManager:328`), 100 ms per-hash send throttle, max 10 retries, then give up.
- **Map area retry tick: 0 ms (dynamics-line) or 300 ms (others)** for `12334` retries.
- **Line frame watchdog: 6000 ms** initially (`HashDataManager:433`), **4000 ms** between subsequent frames (`:1553`), **10000 ms** if transactionId mismatched (`:1479`). Batch up to 20 hashes; max 10 retries.
- **Dynamics-line poll: 10000 ms** (MN231 only, working-state only).
- **BLE heartbeat: 1500 ms** for first 6 ticks then **3000 ms** degraded; `count1` resets in `[6, 10)` band.
- **BLE feed-dog: max(22000, DATA_IOT_TIMEOUT_VALUE) = 22000 ms** (`LOOP_SEND_HEART`/10009).
- **Sys link feed-dog: 20000 ms** wall-clock gate in `setSystemPackageListener`.
- **Date-time sync retry: 500 ms × 3** attempts.
- **OTA 5 s sync: 5000 ms** (`startDeviceFiveSync`), with 5 s `tiem_five` debounce on entry.
- **IoT subscription renewal: 120000 ms while working, 300000 ms idle.**
- **MQTT keepalive: 60 s** (Mammotion direct MQTT).
- **MQTT connect timeout: 14 s** + 15 s `CountDownLatch.await`.
- **Manual control send: 200 ms** (`CarRemoteControlManage2`) / **800 ms** (`ManualLawnMowingManager`/`OperateOnView`).
- **BLE scan window: 8 s; scan debounce: 8 s.**
- **BLE connect/loading watchdog: 22 s** across the entire `ConnectLinkManage` state machine.
- **DeviceFragment / HomeFragmentNew RTK base-station refresh: 20 s** (also drives `getBaseStation()` ping on RTK devices).

Send-gating wall-clock checks (`currentTimeMillis()`-based, no Handler) live in `HashDataManager.java:319` (100 ms per-hash), `MACarDataManager.java:6432` (20 s feed-dog), `MACarDataManager.java:6555` (5 s OTA-sync entry), `MACarDataManager.java:2256/2624/3244` (3 s device-location), `MACarDataManager.java:2313/.../5773` (~900 ms RSSI), `EspBleManager.java:917` (500 ms connect debounce), `MAScanManager.java:629` (8 s scan debounce), `MAScanManager.java:110/:118` (1 s BT broadcast debounce).
