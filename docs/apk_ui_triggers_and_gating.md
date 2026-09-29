# APK 2.3.8.201 — UI Triggers and Send Gating

APK root: `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/`. All paths below are relative to that root.

---

## Part A — Send Gating

This section is listed first because every UI trigger in Part B passes through these gates.

### A.1 Transport selection (LinkType)

`device/source/links/MALinkManagerAPI.java:97-128` defines:

```
LinkType_NONE      // not sendable
LinkType_IOT       // Aliyun MQTT / IoT
LinkType_BLUETOOTH // BLE (esp blufi)
```

The current value is read via `getDeviceLinkStatus()` (`MALinkManagerAPI.java:158`) and `getCurrentLinkStatus()` (`:153`).

There are two parallel helpers, both with identical structure:
- `command/MACommandHelper.java` — older / per-call link-passing variant. `isSupportIOT(MALinkManager)` (`:174-178`).
- `command/app/MACommandApiHelper.java` — newer "API" variant used by `HomeStateViewModule`. `isSupportIOT()` no-arg (`:194-198`).

The unified send path (using `MACommandApiHelper` as canonical):

`command/app/MACommandApiHelper.java:224-248`
```java
private void sendMsg(LubaMsg.Builder builder, int logtype, boolean iotable, String tag) {
    byte[] bytes = builder.build().toByteArray();
    if (!iotable)                  postCustomeDateByte(bytes, tag);     // force BLE
    else if (isSupportIOT())       setDeviceIotService(bytes, logtype, tag); // IoT/MQTT
    else                           postCustomeDateByte(bytes, tag);     // fall back to BLE
}
```

`iotable=false` means **always BLE**. Examples: `addDrawCorridorPoint()` (`MACommandApiHelper:379`), `cancelLogUpdate()` (`:465`), `noticeReportRoutes()` (`:1081`), `stopAndNotSaveTask()` (`:1843`), `saveTask()` (`:1370`).

`sendOrderMsg_Sys2()` (`MACommandApiHelper:294-331`) is a specialised dispatcher: it inspects `IotResp.iotEnabled()` and forces BLE when IoT is not yet active, regardless of `iotable`.

Nav/Media/Video sends short-circuit early on Spino devices (`isSpino()` check at `:257`, `:266`, `:334`): a non-Spino command sent to a Spino device is silently dropped at the helper.

### A.2 Transport-state preconditions on `MALinkManager`

`device/source/links/managers/MALinkManager.java`:

| Condition | Source | Effect |
|---|---|---|
| `isCarPowerOff() == true` | `trySwitchToIOT` (`:555-561`) | Forces `LinkType_NONE`; sends become BLE writes to a no-op client. Effectively blocked. |
| `singleState.netUsedType == 3` (no IoT entitlement) | `trySwitchToIOT` (`:563`), `setBlueToothDisConnect` (`:461`) | Forces `LinkType_NONE`. App will never select IoT for this device. |
| `NetUtils.isNetworkConnected() == false` | `trySwitchToIOT` (`:567-569`) | Forces `LinkType_NONE`. |
| `iotId` empty or `getDeviceIotState(iotId) == false` | `trySwitchToIOT` (`:576-580`) | Forces `LinkType_NONE`. |
| BLE off | `setBlueToothOff()` (`:481-487`) | Closes BLE client and calls `trySwitchToIOT("bt_off")`. |
| BLE disconnect, device online, not power-off | `setBlueToothDisConnect()` (`:453-479`) | Sets `LinkType_IOT` and calls `onIotPrepared(3)`. Otherwise `LinkType_NONE` and `trySwitchToIOT`. |
| WiFi off | `setWiFiClose()` (`:523-525`) | Calls `_trySwitchToBT("wifiClosed", false)` to flip back to BLE. |
| WiFi on | `setWiFiOpen()` (`:528-535`) | Only acts when current is `LinkType_NONE`. |

`deviceIsConnect()` (`MALinkManagerAPI.java:178`) returns `currentLinkStatus != LinkType_NONE`. This is the canonical "is anything sendable?" check.

The lowest layer (`MALinkManager.sendData`, `:435-442`) silently no-ops if `espBleManager == null`, even when `LinkType_BLUETOOTH`. Commands are not queued or retried at this layer.

### A.3 Device-online and "is sendable" checks used by the UI

The UI does not call `MALinkManager` directly; it consults the per-device state machine:

| Field | Where |
|---|---|
| `getStateMachine().getDeviceOnline()` | `CarStateMachineBean`; consumed by every viewmodel send entry |
| `getStateMachine().getConnectState()` | Mirrors `LinkType` (`BLUETOOTH` / `IOT` / `NONE`) |
| `getStateMachine().getSingleState().getNetUsedType()` | 1=4G, 2=WiFi, 3=no IoT entitlement |
| `getStateMachine().getSingleState().getBatteryValue()` | Used by start-job gate (`< 15` blocks) — `HomeStateViewModule.toStartWork:1234-1245` |
| `AppCache.getDeviceOnline(iotId)` | Aliyun-pushed online status |
| `MADataReceiverCallback.isCarPowerOff()` | True when device reported OFF |

`setAskBlueToothOpen()` (`MALinkManager.java:445`) is the explicit user-driven re-scan path used when the gate says "no transport".

### A.4 Capability matrix (`DeviceType` enum predicates)

Source: `device/source/device/enums/DeviceType.java:403-779`. Every predicate is a gate that hides the corresponding action in the UI.

#### A.4.1 Connectivity / hardware

| Predicate | Returns | Notes |
|---|---|---|
| `has4G()` (`:403`) | `getValue() >= LUBA_2.value` | All from Luba 2 onward. |
| `isSupportIOT()` (`:618`) | `!isSwimmingPool() && this != UNKNOWN` | Spino/Spion have no IoT. |
| `isSupportRtkService()` (`:662`) | `YUKA_MINI/MINI2/VP, LUBA_MN/VP/YUKA/2, CM900, LUBA_HM/ME/VA` | Paid RTK service entry. |
| `isSupportNRTK()` (`:630`) | not `LUBA / LUBA_YUKA / LUBA_2 / isRTK()` | Network RTK switch. |
| `isSupportRadarRTKSwitch()` (`:650`) | `LUBA_LD, LUBA_MD, LUBA_LA` | Radar/RTK position toggle. |
| `isPureRadar()` (`:535`) | `LUBA_LD, YUKA_ML, YUKA_MN101, LUBA_MD/LA/HM/ME/VA` | No GNSS positioning UI. |
| `isPureVisual()` (`:539`) | `YUKA_MINIV, YUKA_MN100, LUBA_MB` | Camera-only positioning. |
| `isSupportPositioning()` (`:642`) | `isPureVisual() || LUBA_LD` | Positioning-calibration flow. |
| `isSupportRadar()` (`:646`) | `LUBA_LD, LUBA_VA/HM/ME, YUKA_ML, YUKA_MN101, LUBA_MD/LA` | Radar device. |
| `isSupportRadarSelfCheck()` (`:654`) | `LUBA_VA, YUKA_ML, LUBA_LA` | Self-check button. |
| `isSupportVision()` (`:674`) | `YUKA_MINI/MINI2/VP, LUBA_MN/VP/2, CM900, LUBA_YUKA, LUBA_MB` | Camera/AI features. |
| `isSupportVideo()` (`:670`) | `LUBA_YUKA, YUKA_VP` | FPV livestream entry. |
| `isSupportPointCloud()` (`:638`) | `LUBA_LD` only | Point-cloud preview. |
| `isSupportFillLight()` (`:610`) | Yuka mini family + LUBA_MN/VP/VA/HM/ME/LA/MD/MB/LD, CM900 | Headlamp UI. |
| `isSupportBladeSpeed()` (`:587`) | All "new" devices | Blade-speed slider. |
| `isNotSupportCameraWiper()` (`:523`) | LUBA_2, CM900, LUBA_VP/VA/HM/ME/MN, Yuka mini variants, LUBA_MB | Hides wiper button. Wiper visible only on `LUBA_YUKA` and `YUKA_VP`. |

#### A.4.2 Drive train

| Predicate | Returns |
|---|---|
| `isSupport2wd()` (`:571`) | `YUKA_MINIV, YUKA_ML, isYuKaType()` |
| `isSupport4wd()` (`:575`) | `LUBA_VA, LUBA_MB, LUBA_HM, LUBA_ME, !isYuKaType()` |
| `isX5Support2wd()` (`:714`) | `YUKA_MINIV, YUKA_ML` |
| `isX5Support4wd()` (`:718`) | `LUBA_VA, LUBA_MB, LUBA_HM, LUBA_ME, LUBA_LA, LUBA_MD, CM900` |

#### A.4.3 Mapping / area features

| Predicate | Allowed devices |
|---|---|
| `isSupportAllArea()` (`:579`) | `LUBA_LD, LUBA_VP, CM900, YUKA_VP, LUBA_MN, YUKA_MINI, YUKA_MINI2`. **LUBA_HM not included.** |
| `isSupportAreaVersion()` (DeviceUtils:695) | `!isLessThanInputVersion("1.14.5") && type.isSupportAllArea()` |
| `isSupportManualMappingAreaVersion()` (DeviceUtils:793) | Per-type firmware floor |
| `isSupportUpdateMap()` (`:666`) | `YUKA_MINIV, YUKA_MN100, LUBA_MB, CM900` |
| `isSupportUpdateMapVersion()` (DeviceUtils:826) | Adds firmware floor |
| `isOnlySupportChargeStationDeploy()` (`:527`) | `YUKA_MINIV, YUKA_MN100, LUBA_LA, YUKA_ML, SWIMMINGPOOL_SP` |
| `isSupportChargeStationDeploy()` (`:595`) | `YUKA_MINIV, YUKA_MN100, LUBA_MB, LUBA_VA, YUKA_ML, SWIMMINGPOOL_SP, LUBA_LA`. **LUBA_HM not included.** |
| `isSupportCrossPointDeviceType()` (`:599`) | `LUBA_MN, LUBA_LD, LUBA_VP, YUKA_MINI, YUKA_VP, YUKA_ML, LUBA_VA, LUBA_HM, LUBA_ME, LUBA_LA`. **LUBA_HM included.** |
| `isSupportCrossingTheObstaclePoint()` (DeviceUtils:716) | type.isSupportCrossPointDeviceType + firmware ≥ 1.15.0 |
| `isSupportDynamicsLine(dev)` (`:606`) | `YUKA_MINIV, YUKA_MN100, LUBA_MB, LUBA_LA, YUKA_ML, LUBA_HM, LUBA_ME, CM900, LUBA_VA(≥1.15.3.4422)`. **LUBA_HM included.** |
| `isNoSupportDrawLine()` (`:507`) | `LUBA_LD, LUBA_VA, LUBA_HM, LUBA_ME, LUBA_LA, YUKA_ML, YUKA_MN101, YUKA_MN100, YUKA_MINIV, LUBA_MD, LUBA_MB`. Hides static line drawing. |
| `isNoSupportAutoMap()` (`:503`) | `isX5DeviceTyp()` |
| `isSupportNoAreaWorkDeviceModel()` (`:634`) | `YUKA_MINIV, YUKA_MN100, LUBA_MB, LUBA_VA, LUBA_HM, LUBA_ME, YUKA_ML, YUKA_MN101, LUBA_LA`. **LUBA_HM included.** |
| `isNoSupportMapBackup()` (`:515`) | `RTK*, LUBA, SWIMMINGPOOL*, SD_PX, YUKA_MN100` |
| `isNoLocalizationDeviceTyp()` (`:495`) | `isX5DeviceTyp() || LUBA_LD` |
| `isNoBaseRTKType()` (`:491`) | `isX5DeviceTyp() || LUBA_LD` |
| `isNoPositioningGuidance()` (`:499`) | `LUBA_LD, YUKA_MINIV, YUKA_MN100, YUKA_MN101, LUBA_MB` |
| `isVerticalScreenRemoteControl()` (`:698`) | `YUKA_MINIV, LUBA_VA, LUBA_HM, LUBA_ME, LUBA_LA`. **LUBA_HM included.** |

#### A.4.4 Mode / OTA features

| Predicate | Returns |
|---|---|
| `isSupportAutoUpgrade(type, fwVer, dev)` (DeviceUtils:700) | Per-type firmware floor |
| `isSupportBatteryLoopCount()` (`:583`) | Most types except Yuka mini family and LUBA_LD/LA/MB/MN |
| `isSupportLocalUpgradeSwimmingPool()` (`:626`) | SP devices only |
| `isSupportRelocationAnimation()` (`:658`) | `isYukaMV() || isLubaMB() || isYukaMN100()` |
| `isSupportBoxDevice()` (`:591`) | `LUBA_VA, LUBA_HM, LUBA_ME`. **LUBA_HM included.** |
| `isSupportFPVDownConversion()` (DeviceUtils:721) | Yuka mini/VP, LUBA_MN/LD/VP/VA |
| `isConditionToFPV(dev)` (DeviceUtils:629) | Combines `availableTime_service` + `isSupportFPVDownConversion` |
| `isConditionToFPV4GTips(dev)` (DeviceUtils:648) | Shows 4G-required tip dialog |

#### A.4.5 App 2.3.20.30 enum changes

The tables above are 2.3.8.201. 2.3.20.30 (`device/source/device/enums/DeviceType.java`, readable Java) renumbers the whole enum (RTK 1001-1005, Luba 2000-2014, CM 3000-3001, Yuka 4000-4007, pools 5000-5004). pymammotion keeps the old ids for existing members and gives the added ones the new ids (no clash).

| Added member | id | Name prefix | Code | `DeviceProductKey` |
|---|---|---|---|---|
| `LUBA_SP` | 2008 | `Luba-SP` | HM435 | `SNvVHSxfU73` |
| `LUBA_TR` | 2012 | `Luba-TR` | HM436 | `z8Pu2TEeNZU` |
| `LUBA_LS` | 2013 | `Luba-LS` | HM432SE | `k8H4M5KZ6Fn` |
| `LUBA_MS` | 2014 | `Luba-MS` | HM434SE | `f4KFveHngnm` |
| `CM901` | 3001 | `Maston-R` | CM901 | none (name only) |
| `YUKA_HS` | 4007 | `Yuka-HS` | MN260 | `h8ZyNy8FV3u` |
| `SPINO_H1` | 5004 | `Spino-H1` | IL100 | `rbk9dxFBe6m`, `xEBF8JsgVeR` |

New prefixes on existing members: `LUBA_HM` `"Luba-HM,Luba-MH"`, `YUKA_MN100` `"Ezy-VT,Yuka-CV"`, `CM900` `"Kumar-MK,Maston-F"`. Name matching (`valueOfStrByDeviceName`) is `startsWith` for the comma lists; `Spino-H1` and `Maston-R` are checked before the generic `Spino` / `CM900` fallbacks.

Predicate changes (2.3.20.30 line numbers): the new Luba/CM members join `isLubaType` (679), `isSupportDynamicsLine` (826), `isSupportFillLight` (830), `isSupportBladeSpeed` (803) and `isX5DeviceTyp` (914) — which also gains `YUKA_MN100` and `YUKA_MN101`. `YUKA_HS` joins `isYuKaType` (946) and the same capability lists. `LUBA_LS`/`LUBA_MS`/`YUKA_HS` join the `isSupportBatteryLoopCount` exclusion (799); `LUBA_MS` (and a vision `YUKA_HS`, a runtime flag) join `is231SimilarParameterSettings` (599); `SPINO_H1` joins `isSwimmingPool` (894). The RN Smart Sleep list adds HM434SE/HM432SE (bundle line 851).

### A.5 Firmware-version gating

All firmware gates live in `device/source/device/utils/DeviceVersionUtils.java`. The key function is `DeviceVersionUtils.isLessThanInputVersion(ICarDevice, String semver)`. Returns true if device firmware older than threshold; the UI hides the action.

| Threshold | Site | Action gated |
|---|---|---|
| `1.14.5` | `DeviceUtils.isSupportAreaVersion()` (`:697`) | Multi-area selection |
| `1.15.0` | `DeviceUtils.isSupportCrossingTheObstaclePoint()` (`:718`) | Add cross-point on map |
| `1.15.3.4422` | `DeviceType.isSupportDynamicsLine(LUBA_VA)` (`:607`) | LUBA_VA dynamic line |
| Per-type floors | `DeviceUtils.isSupportINaviFirmwareVersion()` (`:758`); `isLuba2YukaNewFirmwareVersion()` (`:676`); `isSupportPointCloudVersion()` (`:812`); `isSupportNewSingleSwitchFirmwareVersion()` (`:798`) | INavi, new-UI for Luba2/Yuka, point-cloud, new single-switch |

Checks run on fragment `onResume()` and on view-model state updates; they hide buttons. Click handlers typically don't redo the check.

### A.6 Mode / work-state gating

`DeviceWorkState.java` defines mower modes. The UI maps mode → allowed-actions in switch tables in `home/fragment/DeviceStateFragment.java` and `home/fragment/HomeFragmentNew.java`. `DeviceWorkState.isReturning()` is used directly by `HomeStateViewModule.startStopCarRecharge` (`:1181`) to dispatch between `claseBacktoRecharge` and `returnCharge`.

Action-allow set:

```
IDLE / READY              — start mowing, blade-cal
WORKING                   — pause, stop, return-to-dock (start hidden)
PAUSE                     — resume, stop
RETURN_TO_PILE / CHARGING — start hidden, leave-pile shown
LOCATING / LOCATING_FAIL  — most blocked; relocation UI only
OBSTACLE / EMERGENCY_STOP — ack-error / cancel-task only
OTA / UPDATING            — all user commands blocked
OFFLINE / POWEROFF        — nothing sendable; reconnect prompt
```

Additional pre-send guards inside `HomeStateViewModule.toStartWork` (`:1214-1268`):
- `workSettingBean.getArealist() == null` or empty → toast `toast_please_selelct_area`, return.
- `mBattery < 15` → toast `error_dh_1007_1`, return.
- `MACarDataManager.isDeviceBumperExist(deviceName) == false` → toast `toast_lack_bumper`, return.

### A.7 Concurrency / inflight tracking

No explicit request-ID/response-future correlation. The APK uses three loose mechanisms:

1. **`seq_ble`** on the helper (`MACommandApiHelper:497` `clearSeqBle`, `:362` increment). Only a protobuf `seqs` field for log correlation — not used to reject duplicates.
2. **Per-action "in progress" booleans** on view models. E.g. `HomeStateViewModule.operationStatus` set to `2000` for "starting" and `3000` for "pausing/charging" before `RefreshLoading.showPopupWindow()` (`MACommandApiHelper.startJob:1826`, `pauseExecuteTask:1098`, `claseBacktoRecharge:491`, `closeJob:504`, `returnCharge:1360`). The UI disables the same button while the popup is up but other screens can still send.
3. **`CommandManager.fetchCallbackFun`** (`command/CommandManager.java`) registers per-command observers via Kotlin inline `comObserverFun` wrappers (see the many `CommandManager$xxx$$inlined$comObserverFun$1.java` synthetic classes in `command/`). Two sends of the same command type overwrite each other's observer — last writer wins.

No global rate limiter; every send hits the link manager immediately.

### A.8 Sleep / power gates

`MACommandHelper.getChargingSleepStatus()` / `setChargingSleepStatus()` (`:789`, `:1535`) and `getUnChargingSleepStatus()` / `setUnchargingSleepStatus()` are the only "device awake?" interactions. The UI does **not** automatically wake the device. If the device is `LubaWorkStatus.SLEEP`, sends still flow but the device drops them silently. `DeviceStateFragment.closTips` surfaces a "Mower is sleeping, wake it up?" dialog rather than gating; `HomeStateViewModule.wakingUp(deviceName)` (`:1271`) calls `HomeApiUtils.wakeUp` (HTTP) to wake.

---

## Part B — UI Triggers, Grouped by Feature

### B.1 Top-level navigation

`home/fragment/HomeFragmentNew.java`: device drawer + pager. Each device card switches the active device via `DeviceManager.switchDevice(name)`. Switching does not send any command — it changes the receiver.

### B.2 Start / continue / pause / stop / dock

Owner: `home/fragment/DeviceStateFragment.java` and the newer `HomeFragmentNew.java`. The single funnel is `HomeStateViewModule` (`home/viewmodel/HomeStateViewModule.java`).

| UI element | Click chain | Command sent | Gates |
|---|---|---|---|
| `btn_start_work` ("Start") | `DeviceStateFragment.onListener` → `HomeStateViewModule.toStartWork(act, name, battery, knifeH)` (`:1214`) → first calls `setKnifeHight()` then `MACommandApiHelper.startJob(null)` (`:1823`) | `MctrlNav.todev_taskctrl(type=1, action=1)` (logtype 35) | `arealist != null && !empty`; `battery ≥ 15`; `isDeviceBumperExist`; `deviceOnline && linkType != NONE`. |
| `btn_pause` | `DeviceStateFragment` (`:1219`) → `HomeStateViewModule.startOrPauesJob(false)` (`:1154`) → `MACommandApiHelper.pauseExecuteTask(null)` (`:1095`) | `MctrlNav.todev_taskctrl(type=1, action=2)` (logtype 39) | `workState == WORKING`. |
| `btn_resume` | `DeviceStateFragment` (`:1279`) → `HomeStateViewModule.cancelPauseExecuteTask()` (`:939`) → `MACommandApiHelper.cancelPauseExecuteTask(null)` (`:469`) | `MctrlNav.todev_taskctrl(type=1, action=3)` (logtype 42) | `workState == PAUSE`. |
| `btn_continue_breakpoint` | `MACommandApiHelper.breakPointContinue()` (`:449`) | `MctrlNav.todev_taskctrl(type=1, action=7)` (logtype 42) | `hasBreakpoint`. |
| `btn_continue_here` | `MACommandApiHelper.breakPointAnywhereContinue(loading)` (`:440`) | `MctrlNav.todev_taskctrl(type=1, action=9)` (logtype 43) | `hasBreakpoint && supportsAnywhereContinue`. |
| `btn_close_job` ("Stop") | Confirmation dialog → `HomeStateViewModule.closJob()` (`:946`) → `MACommandApiHelper.closeJob(loading)` (`:501`) | `MctrlNav.todev_taskctrl(type=1, action=4)` (logtype 37) | `workState in {WORKING, PAUSE}`. |
| `btn_back_to_dock` | `HomeStateViewModule.startStopCarRecharge(deviceState)` (`:1180`) → either `claseBacktoRecharge(null)` (`:487`) or `returnCharge(null)` (`:1357`) | Recharge: `MctrlNav.todev_taskctrl(type=1, action=5)` (logtype 38). Cancel: `MctrlNav.todev_taskctrl(type=1, action=12)` (logtype 36). | `DeviceWorkState.isReturning()` chooses cancel vs start. |
| `btn_one_touch_leave_pile` ("Leave dock") | `MACommandApiHelper.autoUnderPile()` (`:431`) | `MctrlNav.todev_one_touch_leave_pile=1` (logtype 20) | `workState == CHARGING && batteryPct > threshold`. |
| No-area work | `MACommandApiHelper.noAreaWork()` (`:1077`) | `MctrlNav.todev_taskctrl(type=1, action=16, type(2)=1)` (logtype 41) | Only when `isSupportNoAreaWorkDeviceModel()` is true (LUBA_HM is included). |
| Continue last job (2.3.20.30) | Two entry points. RN work-report detail (bundle line 782): "Resume task" → `MowingReportModule.continueWork(workId, deviceName)` (`rn/module/MowingReportDataModule.java:89-157`). Home start button (`HomeFragmentNew.updateGrassRobotDevices$lambda$71/$80`, `:9095`/`:9190`): `checkContinueWorking()` (native, packed, `:3078`) picks `continueLastTask()` (`:3325`) → `ContinueWorkBottomDialog` → `HomeCommandHelper.continueLastJob` (`:171`). Both end in `MACommandApiHelper.continueLastWork(accountId, workId)` (`command/app/MACommandApiHelper.java:695-699`). | `MctrlNav.todev_work_report_start_working_msg{accountID, workId, stamp=now ms, result=1}` (logtype 140) | No model list, no firmware compare. RN shows the button for `record.continueWork && record.workType != DROPMOW` (server flag on `device-server/v1/device/work-report/page`). Native checks: device home-selected and `isConnected()`; `!BlockErrorBeanChangeUtils.isVisible(selfCheck)`; `deviceState == MODE_READY (11)`; not (`bleRssi < -80` and no IoT). Home path additionally: map present (`bolHash > 1`), `battery >= 30`, a latest work record exists. pymammotion: `DeviceType.supports_continue_last_job` (any mower). |

`HomeStateViewModule.startOrPauesJob(true)` (`:1154-1162`) is the simpler funnel that just calls `MACommandApiHelper.startJob(null)`. `toStartWork` (`:1214`) is used when an explicit settings dialog returns a configured `WorkSettingBean`.

### B.3 Manual remote control (joystick)

Owner: `home/fragment/DeviceStateFragment.java` and a vertical-screen variant gated by `isVerticalScreenRemoteControl()`.

| UI | Chain | Command | Gates |
|---|---|---|---|
| Joystick drag (`CarRemoteControlManage2.java`) | `CarRemoteControlManage2.send` → `MACommandApiHelper.OperateOnDevice(main_ctrl, knife_ctrl, knife_h, speed, position)` (`:375`) | `MctrlDriver.setMowCtrlByHand` (logtype 51) | `deviceOnline && linkType != NONE`. Throttled by `CarRemoteControlManage2`. |
| Blade height slider release | Same `OperateOnDevice` with new height | Same | Same. |
| Blade on/off | Same `OperateOnDevice` with new `cut_knife_ctrl` | Same | Confirmation dialog if turning on while moving. |
| Direct linear/angular speed (debug) | `MACommandApiHelper.sendControl(linear, angular)` (`:1397`) | `MctrlDriver.todev_devmotion_ctrl` (logtype 51, **iotable=false → BLE only**) | Internal/debug only. |

Layout decided once at fragment `onCreate` against `DeviceType.isVerticalScreenRemoteControl()`.

### B.4 Mapping (boundary / obstacle / channel drawing)

Owner: `map/` package — `map/fragment/MapFragment.java`, `map/activity/MapActivity.java`, and `newui/map/` variants.

| UI element | Chain | Command | Gates |
|---|---|---|---|
| "Start boundary" | `MapViewModel.startDrawBorder(type)` → `MACommandApiHelper.setEditBoundary(type)` (helper variant `MACommandHelper.java:1599`) | `MctrlNav.todev_setEditBoundary` | `isSupportAllArea()` for multi-area; otherwise single. |
| "End boundary" | `MACommandApiHelper.endDrawBorder(type)` (`:576`) | `MctrlNav.todev_setEditBoundary` (action=2) | Requires ≥ N points. |
| "Add obstacle" point | `MACommandApiHelper.addDrawCorridorPoint()` (`:379`, **iotable=false → BLE only**) | `MctrlNav.todev_get_commondata(action=0, type=20)` (logtype 8) | Only in recording mode. |
| "Add cross-point" | `MapViewModel.addManualElement` → `MACommandHelper.addManualElementMessage(elem, link)` (`MACommandHelper.java:353`) | `MctrlNav.toapp_manual_element_message` | `isSupportCrossingTheObstaclePoint()` (type + fw ≥ 1.15.0). Used by LUBA_HM. |
| "Delete map element" | `MACommandApiHelper.deleteMapElements(type, hash)` (`:547`) | `MctrlNav.todev_get_commondata(action=6, type=...)` (logtype 27) | Confirmation dialog. |
| "Clear all map data" | `MACommandApiHelper.deleteAll(int)` (`:530`) | `MctrlNav.todev_get_commondata(action=6, type=6)` (logtype 30) | Two-step confirmation. Hidden when `isNoSupportMapBackup()`. |
| "Cancel record" | `MACommandApiHelper.cancelCurrentRecord()` (`:453`) | `MctrlNav.todev_get_commondata(action=7)` (logtype 26) | Only while recording. |
| "Erase" | `MACommandApiHelper.endErase()` (`:587`) / `cancelErase()` (`:457`) | `MctrlNav.todev_get_commondata(action=7, type=0)` (logtype 10) | Only while erase active. |
| "Rename area" | `MACommandApiHelper.areaRename(deviceId, hash, name, write)` (`:414`) | `MctrlNav.toapp_map_name_msg` (logtype 582) | Inline edit. |
| "Add dump point" | `MACommandApiHelper.addDumpPoint()` (`:383`) | `MctrlNav.todev_get_commondata(action=0, type=12)` (logtype 8) | Yuka with collection. |
| "Outdoor dump add complete" | `MACommandApiHelper.outDropDumpingAdd()` (`:1091`) | `MctrlNav.todev_get_commondata(action=15, type=12)` (logtype 8) | Same. |
| "Revoke dump point" | `MACommandApiHelper.revokeDumpPoint()` (`:1366`) | `MctrlNav.todev_get_commondata(action=6, type=12)` (logtype 8) | Same. |
| "Delete charge point" | `MACommandApiHelper.deleteChargePoint()` (`:537`) / `deleteLDChargePoint()` (`:542`) | `MctrlNav.todev_get_commondata(action=6, type=5)` (logtype 28) and `(action=0, type=5)` (logtype 31) | Only when `isSupportChargeStationDeploy()` (LUBA_HM NOT in this set). |
| "Along boundary" | `MACommandApiHelper.alongBorder()` (`:410`) | `MctrlNav.todev_edgecmd=1` (logtype 112) | Only WORKING / READY. |
| "Generate route" preview | `MACommandApiHelper.GenerateRouteInformation(info)` (`:352`) | `MctrlNav.bidire_reqconver_path` (logtype 31) | Requires at least one boundary. |
| "Modify generated route" | `MACommandApiHelper.modifyGenerateRouteInformation(info)` (`:1066`) | Same proto with subCmd | After initial generate. |
| "Query generated route" | `MACommandApiHelper.queryGenerateRouteInformation()` (`:1128`) | Same proto with query subCmd | After initial generate. |
| "End generate route" | `MACommandApiHelper.endGenerateRouteInformation()` (`:591`) | Same proto with end subCmd | After initial generate. |
| "Confirm base station" | `MACommandApiHelper.confirmBaseStation()` (`:525`) | `MctrlNav.todev_get_commondata(action=2, type=7)` (logtype 29) | `!isNoBaseRTKType()` — skip on LUBA_LD and X5. |
| "Reset base station" | `MACommandApiHelper.resetBaseStation()` (`:1341`) | `MctrlNav` reset | Same. |

### B.5 Mapping (corridor / dynamic line / manual mapping)

Owner: `map/fragment/CorridorFragment.java`, `newui/map/fragment/DynamicLineFragment.java`.

| UI | Chain | Command | Gates |
|---|---|---|---|
| "End corridor" | `MACommandApiHelper.endDrawCorridor()` (`:583`) | `MctrlNav.todev_get_commondata(action=0, type=23)` (logtype 8) | Only while recording. |
| "Give up corridor" | `MACommandApiHelper.giveUpDrawCorridor()` (`:1012`) | `MctrlNav.todev_get_commondata(action=7, type=23)` (logtype 8) | Same. |
| "Recover corridor line/point" | `MACommandApiHelper.recoverDrawCorridorLine/Point()` (`:1179`, `:1183`) | `MctrlNav.todev_get_commondata(action=8)` | Only when undo available. |
| "Dynamic line" entry | `MACommandApiHelper.getDynamicsLine()` (`:941`) | Same proto family | Only when `isSupportDynamicsLine(dev)` (LUBA_HM included). |
| "Manual mapping start" | `MACommandApiHelper.manualMappingStart(int)` (`:1057`) | Nav cmd | Only when `isSupportManualMappingAreaVersion()`. |
| "Manual mapping force end" | `MACommandApiHelper.manualMappingForceEnd()` (`:1042`) | Nav cmd | Same. |
| "Manual mapping goto area" | `MACommandApiHelper.manualMappingGoTpArea()` (`:1047`) | Nav cmd | Same. |
| "Manual mapping instruction" | `MACommandApiHelper.manualMappingInstruction(int)` (`:1052`) | Setup of recording | Same. |
| "Stop and save" | `MACommandApiHelper.stopAndSaveTask()` (`:1847`) | `MctrlNav.todev_taskctrl(type=1, action=4)` (logtype 18) | After manual map. |
| "Stop and not save" | `MACommandApiHelper.stopAndNotSaveTask()` (`:1843`, **iotable=false → BLE only**) | `MctrlNav.todev_taskctrl(type=1, action=18)` (logtype 8) | Same. |

### B.6 Work configuration (cutting params)

Owner: `work/` and `home/fragment/DeviceStateFragment.java` plus `widgets/dialog/StartJobDialog.java`.

| UI | Chain | Command | Gates |
|---|---|---|---|
| Cutting height slider | Persists in `WorkSettingBean.modeBean.knifeHeight`; sent as `MACommandApiHelper.setKnifeHight(h, null)` (called explicitly before `startJob` in `toStartWork:1250`), and also as part of `GenerateRouteInformation` (`:352`). | `MctrlNav.bidire_reqconver_path` (via job start) | Always. |
| Blade speed slider | `MACommandApiHelper.allpowerfullRW(id=8, ctx=speed, rw=1)` (`:391`) | For `isLubaPro() && id ∈ {3,6,7,8,10,11}` it routes to `allpowerfullRWAdapterX3` (`:406`) → `MctrlNav.nav_sys_param_msg` (logtype 43). Otherwise `MctrlSys.bidire_comm_cmd` (logtype 38). For id=5 it uses raw `sendMsg(.., 122, ..)`. | Hidden when `!isSupportBladeSpeed()`. |
| Speed slider | Same `allpowerfullRW(id=2, ...)` | Same | Always. |
| Edge mode toggle | Part of start-job payload | `MctrlNav.bidire_reqconver_path` | Always. |
| Channel mode / width | Same | Same | Always. |
| Toward (mowing direction) | Same | Same | Always. |
| Auto-reverse mowing direction | **Not in 2.3.8.201.** Added by 2.3.18.21, whose native code is Ijiami-packed: only the RN half is readable (bundle module 898 renders `title_reverse_direction`, the screen writes `jobModel.autoChangeDirection` 0/1 and posts it through `WorkSettingModule.sendWorkParams`). | `MctrlNav.bidire_reqconver_path` field 21 (`auto_change_direction`), observed in device echoes as 11 on / 10 off. Field 20 is 2.3.8.201's `app_display_mode` (`task_settings_mode`), the app's basic/advanced settings screen, and reads 1 either way. 2.3.20.30's native code confirms the send: field 21 is `reserved2`, a 32-byte buffer with the raw 0/1 in byte 0, sent even when off (`WorkSettingViewModel.getReserved2`); read back from byte 0 less 10 when >= 10 (`WorkingOptionView.java:77-86`). Schedules carry the same buffer as `NavPlanJobSet` field 41. | 2.3.20.30 has **no native per-model gate**. RN (bundle line 978, rendered at line 981 as `k ? <AutoChangeDirection/> : null`): `isShowCurrentModule(MAWorkSettingDetailCodeAUTOChangeDirection = 23, detailVos)` (server-supplied) **and** `compareVersion(firmwareVersion, "2.3.28.1") >= 0`. `is434Or432Device()` (HM432/HM434) only swaps the description to `cw_reverse_direction_interior`; nothing depends on border laps, job mode or channel mode. pymammotion never fetches `detailVos` (server code 23 is not modelled): `DeviceType.supports_auto_change_direction` takes the RN firmware half for every mower (pools, RTK and UNKNOWN excluded) and stands in for the server half with a user/product-confirmed exclusion of Luba 1 (`LUBA`), Luba 2 (`LUBA_2`, and the Luba 2 Pro/X `LUBA_VP`) and the original Yuka (`LUBA_YUKA`). |
| Edge Coverage (`ride_boundary_distance`) | `SettingOptionsView.refreshData` (2.3.20.30, `work/setting/view/SettingOptionsView.java:1472`) toggles `cvWorkRide`. | `NavReqCoverPath.ride_boundary_distance` | Shown only when `mowing_laps != 0` **and** the type is `LUBA_VA, LUBA_HM, YUKA_MINIV, LUBA_ME, LUBA_TR, LUBA_MB, LUBA_LA, YUKA_ML, LUBA_SP, CM900, CM901`. No firmware compare. pymammotion: `DeviceType.supports_ride_boundary_distance` / `ride_boundary_distance_to_send`. |
| Animal protect toggle | `MACommandApiHelper.allAnimalProtect(id, ctx, rw)` (`:387`) | `MctrlNav.nav_sys_param_msg` (logtype 44) | Hidden when `!isSupportVision()`. |
| Do-not-disturb schedule | `MACommandApiHelper.jobDoNotDisturb(JobDNDBean)` (`:1025`); read via `:1033`; delete via `:1029` | `MctrlNav` family | Only `has4G()` devices. |
| Manual grass collection | `MACommandApiHelper.manualGrassCollection(value)` (`:1038`) | Driver/sys cmd | Only Yuka VP / LUBA_YUKA. |
| Manual pour grass | `MACommandApiHelper.manualPourGrass(value)` (`:1062`) | Same | Same. |

### B.7 Device settings (audio / lights / wiper / network)

Owner: `device/` and `device_center/` settings activities; `home/fragment/DeviceItemFragment.java` for quick controls.

| UI | Chain | Command | Gates |
|---|---|---|---|
| Car volume slider | `MACommandHelper.setCarVolume(v)` (`:1520`) | `LubaMul.SocMul.setSetAudio.setAuSwitch` (logtype 10087) | Always. |
| Car volume gender | `MACommandHelper.setCarVolumeSex(v)` (`:1524`) | `LubaMul.SocMul.setSetAudio.setSex` (logtype 10090) | Always. |
| Car language | `MACommandHelper.setCarVoiceLanguage(lang)` (`:1513`) | `LubaMul.SocMul.setSetAudio.setAuLanguageValue` (logtype 10088) | Always. |
| Get audio cfg | `MACommandHelper.getCarAudioCfg()` (`:778`) | `LubaMul.SocMul` get | Always. |
| Wiper (one-shot) | `MACommandHelper.setCarWiper(rounds)` (`:1531`) | `LubaMul.SocMul.setSetWiper.setRound` (logtype 10090) | Hidden when `isNotSupportCameraWiper()`. Only `LUBA_YUKA` and `YUKA_VP`. |
| Auto night light | `MACommandHelper.setCarLampCtrlNightLight(on, mode, setId)` (`:1508`) | `LubaMul.SocMul.setSetLamp` `lamp_power_ctrl=1` (logtype 10092) | Hidden when `!isSupportFillLight()`. |
| Manual fill light | `MACommandHelper.setCarLampCtrlHandMovement(on, setId, link)` (`:1504`) | `LubaMul.SocMul.setSetLamp` `lamp_power_ctrl=2`, `manual_ctrl=on/off` (logtype 10099) | Same. |
| Get night light | `MACommandHelper.getCarNightLight(setId, link)` (`:785`) | `LubaMul.SocMul` get | Same. |
| Sidelight | `MACommandHelper.readAndSetSidelight(read, sta)` (`:1114`) | `LubaMul.SocMul` lamp set | Only `isSupportFillLight()`. |
| Charging sleep on/off | `MACommandHelper.setChargingSleepStatus(on)` (`:1535`) | `MctrlSys.to_set_dev_low_power_cmd` (logtype 49) | Always (modern firmware). |
| Battery charge limit / off-peak charging | RN battery screen → `BatteryManagerModule.setBatteryInfoWithIotId(controlType=1)` → `MACommandHelper.setBatteryInfo(smart, soc, peakValley, start, end)` (`:1491`); read via `queryBatteryInfo` (`:1069`) | `MctrlSys.bms_ctrl_info_msg` (`smart_charge_switch` 0=smart/1=custom, `charge_soc_threshold` 80-100 step 5, forced 100 when smart). Reply is the same message (`MACarDataManagerAPI` case 33, `smartChargeSwitch==0` → smart). | Page hidden for pools and when `DeviceVersionUtils.isLessThanInputVersion(dev, "2.1.1.5")` (`DeviceFragment.onListener$lambda$42`, `HomeFragmentNew:4738`; unknown version counts as less). Off-peak row additionally needs fw > 2.1.3.50. |
| 4G enable | `MACommandHelper.setDevice4GEnableStatus(z)` (`:1561`) | `DevNet.todev_set_mnet_cfg_req` (logtype 85) | Only `has4G()`. |
| WiFi enable | `MACommandHelper.setDeviceWifiEnableStatus(z)` (`:1591`) | `DevNet.todev_wifi_configuration` (logtype 86) | Always. |
| WiFi connect/forget | `MACommandApiHelper.close_clear_connect_current_wifi(ssid, status, useIot)` (`:510`) | If `!useIot` → BLE JSON (`close_clear_connect_current_wifi2`, `:518`); else `DevNet.todev_wifi_configuration` (logtype 7) | BLE path forced during initial pairing. |
| RTK paring code (NRTK) | `MACommandApiHelper.readAndSetRtKParingCode(rw, code, str)` (`:1161`) | `MctrlSys.app_to_dev_set_mqtt_rtk_t` family | Only `isSupportNRTK() && isSupportRtkService()`. |
| GFSK config | `MACommandApiHelper.readAndSetGfskCfg(rw, str)` (`:1153`) | `MctrlSys` GFSK set | Only on RTK bases (`isRTK()`). |
| Animal protect mode get | `MACommandApiHelper.getAnimalProtectMode(id, ctx)` (`:764`) | `MctrlNav.nav_sys_param_msg` | Only `isSupportVision()`. |
| Reset blade time | `MACommandApiHelper.resetBladeTime()` (`:1345`) | `MctrlSys` | Always. |
| Reset system | `MACommandApiHelper.resetSystem()` (`:1349`) | `MctrlSys` | Always; confirmation dialog. |

### B.8 OTA / firmware

Owner: `device_center/ota/`.

| UI | Chain | Command | Gates |
|---|---|---|---|
| Check version | `MACommandApiHelper.getDeviceVersionInfo(int)` (`:923`) | `MctrlSys` version query | Always. |
| Send firmware finish notify | `MACommandApiHelper.notifyFirmwareSendFinish()` (`:1085`, **iotable=false → BLE only**) | `MctrlOta.fw_download_ctrl(cmd=5)` (logtype 23) | Only during active upload. |
| Remote restart | `MACommandApiHelper.remoteRestart(type, ctx)` (`:1195`) | `MctrlSys` | Settings → Maintenance. |
| Log upload | `MACommandHelper.setDeviceLogUpload(...)` (`:1583`) / cancel (`:431`) | `DevNet.todev_uploadfile_req` (logtype 1 / 4) | Always. Cancel is BLE-only (`iotable=false`). |

### B.9 Calibration (INavi / radar)

Owner: `device_center/calibration/` plus `mvp/fieldmower/` legacy.

| UI | Chain | Command | Gates |
|---|---|---|---|
| Cancel INavi calibration | `MACommandApiHelper.cancelInaviCalibration()` (`:461`) | `MctrlSys.app_to_dev_set_mqtt_rtk_t.setStopNrtkFlag(1)` (logtype 11123) | Only when `isSupportINaviFirmwareVersion()`. |
| Radar test | `MACommandApiHelper.radarTestSend(int)` (`:1143`) | Custom JSON | Only `isSupportRadar()`. |
| Recharge test (debug) | `MACommandApiHelper.reChargeTest()` (`:1149`) | `MctrlSys` debug | Internal/debug. |
| Start radar localisation (X5) | `MACommandApiHelper.startPositioning431All()` (`:1832`, **iotable=false → BLE only**) | `MctrlNav.todev_get_commondata(action=21, type=17)` (logtype 8) | Only X5 / radar devices. |

### B.10 Spino / SwimmingPool

Owner: `home/fragment/DeviceStateSwimmingPool*Fragment.java`. The Spino command path is entirely separate (`sendOrderSpino_Ctrl` `:342`, `getSpMap()` `:991`, `readPlan_SP()` `:1175`, `deletePlan_SP()` `:566`, `requestSwimmingJobHistory()` `:1337`). `HomeStateViewModule.startSwimmingConmand` (`:1195`) and `startPC210SwimmingConmand` (`:1171`) drive the SP work-start flow.

The helper's own `sendOrderMsg_Nav/Sys/Media` short-circuit when `isSpino()` returns true (`:257`, `:266`, `:334`). Thus non-Spino commands sent to a Spino device are silently dropped at the helper layer.

### B.11 Pairing / binding

Owner: `bind/` and `device/fragment/AddDeviceFragment.java`.

The bind flow is BLE-only — `iotable=true` is unreachable because the IoT identifier is not yet known. Calls used:
- `MACommandApiHelper.getDeviceProductModel()` (`:919`) — product model from device.
- `MACommandApiHelper.close_clear_connect_current_wifi2(ssid, status)` (`:518`) — JSON-over-BLE WiFi provisioning.
- `MACommandApiHelper.getDeviceNetWorkInfo()` (`:909`), `get4GInfo(int)` (`:748`), `get4GModuleInfo()` (`:752`) — capabilities probe.
- `MACommandApiHelper.bluetoothPairing()` (`:435`), `queryPairingStatus()` (`:1138`), `deletePairing()` (`:557`) — pairing handshake.
- `BleConnector.java` in `home/` handles scan + connect; `MAScanManager` enforces a 5 s scan window.

No mowing commands sendable from inside the bind flow.

---

## Part C — LUBA_HM (Luba 3) specifics

`LUBA_HM` is defined as a `DeviceType` enum value alongside `LUBA_ME`, `LUBA_VA`, `LUBA_LA`, `LUBA_MD`, `LUBA_MB`.

### C.1 Predicates that return TRUE for LUBA_HM

- `has4G()` (`:403`)
- `isNewDeviceType()` (`:479`)
- `isNewDeviceVersionType(dev)` (`:483`)
- `isNotSupportCameraWiper()` (`:523`) — **no wiper UI**.
- `isPureRadar()` (`:535`) — radar-only positioning.
- `isSupport4wd()` (`:575`) — 4WD drivetrain.
- `isSupportBladeSpeed()` (`:587`) — blade-speed slider.
- `isSupportBoxDevice()` (`:591`) — box-mounting flow.
- `isSupportCrossPointDeviceType()` (`:599`) — cross-point waypoints.
- `isSupportDynamicsLine(dev)` (`:606`) — dynamic line drawing.
- `isSupportFillLight()` (`:610`) — fill light controls.
- `isSupportNoAreaWorkDeviceModel()` (`:634`) — can mow without a defined area.
- `isSupportRadar()` (`:646`).
- `isSupportRtkService()` (`:662`).
- `isVerticalScreenRemoteControl()` (`:698`) — RC fragment uses portrait orientation.
- `isX5DeviceTyp()` (`:702`) — new-gen family.
- `isX5PureRadar()` (`:706`).
- `isX5Support4wd()` (`:718`).
- `isX5SupportReChargePleDeviceTyp()` (`:722`).
- `isNoSupportDrawLine()` (`:507`) — static line drawing hidden (substitute with dynamic line).

### C.2 Predicates that return FALSE for LUBA_HM

- `isSupportAllArea()` (`:579`) — **multi-area UI hidden on Luba 3.** Single-area flow only.
- `isSupportAreaVersion()` (DeviceUtils:695) — follows `isSupportAllArea()`.
- `isSupportChargeStationDeploy()` (`:595`) — **no charge-station deploy step on Luba 3** (despite `isX5SupportReChargePleDeviceTyp() == true` — different flows).
- `isSupportPositioning()` (`:642`) — false (pure radar).
- `isSupportPointCloud()` (`:638`) — LUBA_LD only.
- `isSupportRadarRTKSwitch()` (`:650`) — not on toggle list.
- `isSupportRadarSelfCheck()` (`:654`) — **false despite being radar-only**. No manual self-check button on Luba 3.
- `isSupportRelocationAnimation()` (`:658`).
- `isSupportUpdateMap()` (`:666`) — map-edit-then-update hidden.
- `isSupportVision()` (`:674`) — no camera.
- `isSupportVideo()` (`:670`) — no FPV livestream.
- `isOnlySupportChargeStationDeploy()` (`:527`).
- `isNoBaseRTKType()` (`:491`) — Luba 3 still uses a base RTK.
- `isNoLocalizationDeviceTyp()` (`:495`).
- `isNoPositioningGuidance()` (`:499`).
- `isNoSupportAutoMap()` (`:503`) — auto-map allowed.

### C.3 No explicit LUBA_HM branches outside DeviceType.java

There is no `this == LUBA_HM` outside `DeviceType.java`. Every behavioural difference flows through the capability predicates. From the APK's perspective LUBA_HM is "another X5 4WD radar device" grouped with `LUBA_ME`, `LUBA_VA`, `LUBA_LA`.

### C.4 Map fetch / data sync flow

- Map list via `MACommandHelper.getAllBoundaryHashList(i,j)` (`:702`) — same for all devices.
- Area-name list via `MACommandHelper.getAreaNameList(ctx, name, link)` (`:714`).
- Because `LUBA_HM` is in `isSupportNoAreaWorkDeviceModel()`, the UI does not force area selection; falls through to a no-area job (`MACommandApiHelper.noAreaWork()` `:1077`).
- Because `LUBA_HM` is NOT in `isSupportAllArea()`, only a single area can be selected at a time even when several exist.

### C.5 RC layout for Luba 3

`isVerticalScreenRemoteControl() == true` → `DeviceStateFragment` mounts the vertical-screen RC fragment. Send chain identical to B.3 — `CarRemoteControlManage2 → MACommandApiHelper.OperateOnDevice`.

---

## Part D — Minimum preconditions a sane caller must replicate

1. **Device known online?** UI checks `getStateMachine().getDeviceOnline()` + `getConnectState() != NONE`. Pymammotion equivalent: `DeviceHandle.has_usable_transport`.
2. **Chosen transport viable?** APK requires for IoT: `NetUtils.isNetworkConnected() && !isCarPowerOff() && netUsedType != 3 && deviceIotState(iotId)`. For BLE: `espBleManager != null && system bluetooth on`. Pymammotion equivalent: `Transport.is_usable`.
3. **Feature enabled for this device type?** See A.4.
4. **Firmware new enough?** See A.5.
5. **Device in a state where this command makes sense?** See A.6. Plus the hard pre-checks in `HomeStateViewModule.toStartWork`: `arealist` non-empty, `battery ≥ 15`, `isDeviceBumperExist`.
6. **Spino/SP devices use the Spino command family.** Non-Spino sends to Spino devices silently dropped at `sendOrderMsg_Nav/Sys/Media` (`:257`, `:266`, `:334`).
7. **BLE-only commands (`iotable=false`) should prefer BLE.** Examples: `addDrawCorridorPoint` (`:379`), `cancelLogUpdate` (`:465`), `stopAndNotSaveTask` (`:1843`), `notifyFirmwareSendFinish` (`:1085`), `noticeReportRoutes` (`:1081`), `sendBleAlive` (`:1374`), `startPositioning431All` (`:1832`).

---

## Summary

- Two parallel command helpers: `MACommandHelper.java` (older, per-call MALinkManager) and `MACommandApiHelper.java` (newer, no-arg `isSupportIOT()`). Both have identical dispatch: `iotable==false` → BLE always; `iotable==true` → IoT if `LinkType_IOT`, else BLE fallback.
- Transport selection is fully encapsulated in `MALinkManager.trySwitchToIOT` / `_trySwitchToBT`, driven by network state, IoT entitlement (`netUsedType != 3`), bluetooth state, and `isCarPowerOff()`.
- The UI gates exclusively through `DeviceType.is*` and `DeviceUtils.isSupport*` predicates (A.4), `DeviceVersionUtils.isLessThanInputVersion` firmware floors (A.5), and `DeviceWorkState` mode tables (A.6).
- There is no inflight-tracking, no request-ID correlation, and no rate limiter. Per-button "loading popup" state at `HomeStateViewModule.operationStatus` is the only inflight signal.
- `LUBA_HM` (Luba 3) is treated as a generic X5 4WD radar device. Single-area flow only (no multi-area), no charge-station deploy UI, no manual radar self-check button, no camera/vision/FPV, supports no-area work, supports dynamic-line drawing in place of static lines, and uses the vertical-screen RC layout. There are no explicit LUBA_HM branches outside the `DeviceType` enum.
