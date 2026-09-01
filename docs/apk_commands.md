# APK Command Emission Catalog

Source: decompiled Mammotion APK 2.3.8.201 at `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/`.

## Frame envelope

All binary frames are `LubaMsgOuterClass.LubaMsg`. Built by `MACommandHelper.getProtoBufBuilderSet` (`command/MACommandHelper.java:126-131`):

- `msgtype`: per-payload (see below)
- `sender = DEV_MOBILEAPP`
- `rcver`: usually `DEV_MAINCTL`; ESP-net → `DEV_COMM_ESP`; multimedia → `SOC_MODULE_MULTIMEDIA`; LubaPro nav redirected to `DEV_NAVIGATION` (`getMsgDevice`, line 122); radar tests use `DEV_PERCEPTION`
- `msgattr = MSG_ATTR_REQ`
- `version = 1`
- `subtype = userId` (account, default 102)
- `seqs` = monotonic `seq_ble`
- `timestamp = MonotonicClock.now()`

Payload-typed wrappers:
- `sendOrderMsg_Nav` → `MSG_CMD_TYPE_NAV`, `setNav(MctlNav)` (line 233)
- `sendOrderMsg_Sys` → `MSG_CMD_TYPE_EMBED_SYS`, `setSys(MctlSys)` (line 254)
- `sendOrderMsg_Driver` → `MSG_CMD_TYPE_EMBED_DRIVER`, `setDriver(MctlDriver)` (line 218)
- `sendOrderMsg_Ota` → `MSG_CMD_TYPE_EMBED_OTA`, `setOta(MctlOta)` (line 248)
- `sendOrderMsg_Net` → `MSG_CMD_TYPE_ESP`, `setNet(DevNet)` (line 242)
- `sendOrderMsg_Media` / `sendOrderMsg_Video` → `MSG_CMD_TYPE_MUL`, `setMul(SocMul)` (lines 224, 299)
- `sendOrderSpino_Ctrl` → `MSG_CMD_TYPE_SPINO_CTRL`, `setCtrl(SpinoCtrl)` (line 308)
- For Basestation, raw `MSG_CMD_TYPE_BASESTATION` with `setBase(BaseStation)` (e.g. `getBaseStation` line 760)

**Transport**: `sendMsg(builder, logtype, isIotable, ...)` (line 206) — when `isIotable=true` and the link is `LinkType_IOT`, frames are wrapped as Aliyun JSON `{iotId, identifier=PROTOBUF_SYNC_SERVICE, args:{content:base64}}` via `setDeviceIotService` (line 1565). When `isIotable=false`, bytes are sent raw over BLE only. Many handshake / pairing / sync frames force BLE (`isIotable=false`).

`MACommandApiHelper.java` (1972 lines) is the per-device facade wrapping `MACommandHelper` — most methods are 1:1 wrappers; deltas noted inline. Some Sys frames in app-helper use `sendOrderMsg_Sys2` (line 294) which is BLE→IOT fallback when an `IotResp` is available.

---

## Mowing / task control — `MctlNav.todev_taskctrl` (`NavTaskCtrl`)

All have `type=1`, `result=0` unless noted. File `command/MACommandHelper.java`.

| Method | type | action | Purpose | Line |
|---|---|---|---|---|
| `startJob` | 1 | 1 | Start job | 1724 |
| `pauseExecuteTask` | 1 | 2 | Pause | 1041 |
| `cancelPauseExecuteTask` | 1 | 3 | Cancel pause / resume | 445 |
| `closeJob` | 1 | 4 | End job | 453 |
| `stopAndSaveTask` | 1 | 4 | Stop mapping, save (same opcode) | 1752 |
| `returnCharge` | 1 | 5 | Return to dock | 1290 |
| `breakPointContinue` | 1 | 7 | Continue from breakpoint | 405 |
| `breakPointAnywhereContinue` | 1 | 9 | Continue from current pos | 401 |
| `reChargeTest` | 1 | 10 | Recharge test | 1091 |
| `cancelBacktoRecharge` | 1 | 12 | Cancel back-to-recharge | 409 |
| `noAreaWork` (X5, app-helper 1077) | 1 | 16 | X5 no-map work | — |
| `endDrawCorridor` | 1 | 17 | MN231 end corridor recording | 525 |
| `stopAndNotSaveTask` | 1 | 18 | MN231 abandon mapping mid-build | 1748 |
| `startUpdateMap` | 1 | 19 | Update map | 1744 |
| `resetBaseStation` | 3 | 1 | Reset charging pile / base | 1274 |
| `fastAotuTest(i3)` | 1 | i3 | One-key auto test | 686 |

Other top-level Nav controls:

| Method | Field | Notes | Line |
|---|---|---|---|
| `autoUnderPile` | `setTodevOneTouchLeavePile(1)` | One-touch off-pile | 397 |
| `alongBorder` | `setTodevEdgecmd(1)` | Edge-mode command | 386 |
| `saveTask` | `setTodevSaveTask(1)` | Save mapping task | 1298 |

---

## Map / hash / region — `MctlNav.todev_get_commondata` (`NavGetCommData`)

All `pver=1`. Most are BLE-or-IOT (`isIotable=true`); some are forced BLE (`false`). File `command/MACommandHelper.java` (top-level) and `command/app/MACommandApiHelper.java` (app variant).

### Start / record (action=0)

| Method | action | type | Notes | Line |
|---|---|---|---|---|
| `startDrawBorder` | 0 | 0 | Start drawing boundary (BLE-only) | 1706 |
| `startDrawBarrier` | 0 | 1 | Start drawing obstacle | 1702 |
| `startChannelLine` | 0 | 2 | Start channel/passage line | 1698 |
| `addDumpPoint` | 0 | 12 | Add grass dump point | 349 |
| `startDrawCorridor` | 0 | 19 | MN231 start corridor recording (BLE-only) | 1716 |
| `addDrawCorridorPoint` | 0 | 20 | MN231 add corridor point (BLE-only) | 345 |
| `manualMappingInstruction(i3)` | 0 | 27 | X5 manual map | 1007 |
| `manualMappingForceEnd` | 0 | 28 | X5 force-close mapping | app 1042 |
| `manualMappingStart(i3)` | 0 | 29 | X5 direct start / arrived-start | app 1057 |
| `manualMappingGoTpArea` | 0 | 30 | X5 go to lawn | app 1047 |

### End (action=1)

| Method | action | type | Notes | Line |
|---|---|---|---|---|
| `endDrawBorder(i3)` | 1 | i3 | type=0/1/2 (border/obstacle/channel) | 518 |
| `exitDumpingStatus` | 1 | 12 | Exit grass-dump state | 543 |

### Confirm / arrived (action=2, 22)

| Method | action | type | Notes | Line |
|---|---|---|---|---|
| `confirmBaseStation` | 2 | 7 | Confirm base station unchanged | 472 |
| `arrivedChargeAhead` | 22 | 2 | Arrived in front of charge pile | app 421 |

### Erase (action=4/5/7)

| Method | action | type | Notes | Line |
|---|---|---|---|---|
| `startErase` | 4 | 0 | | 1720 |
| `endErase` | 5 | 0 | | 529 |
| `cancelErase` | 7 | 0 | | 419 |

### Delete (action=6)

| Method | action | type | hash | Notes | Line |
|---|---|---|---|---|---|
| `deleteAll` | 6 | 6 | — | Clear all map data | 481 |
| `deleteChargePoint` | 6 | 5 | — | Delete charging pile | 485 |
| `deleteMapElements(i3, j3)` | 6 | i3 | j3 | Delete boundary/obstacle/channel by hash | 503 |
| `revokeDumpPoint` | 6 | 12 | — | Revoke grass dump point | 1294 |
| `deleteLDChargePoint` (legacy) | 0 | 5 | — | Delete radar charge pile | 490 |
| `deleteLDChargePoint` (newer) | 23 | 5 | — | Delete radar charge pile (newer path) | 1887 |

### Cancel current record (action=7)

| Method | action | sub_cmd | type | Notes | Line |
|---|---|---|---|---|---|
| `cancelCurrentRecord` | 7 | 0 | — | Cancel boundary/obstacle recording | 415 |
| `giveUpDrawCorridor` | 7 | — | 19 | MN231 give up corridor | 973 |

### Sync regional data / iterate frames (action=2/8/12)

| Method | action | sub_cmd | type | hash | total_frame | current_frame | Notes | Line |
|---|---|---|---|---|---|---|---|---|
| `getRegionalData(bean)` | bean.action | 2 | bean.type | bean.hash | bean.total | bean.current | Ack region data, request next frame | 937 |
| `synchronizeHashData(l3)` | 8 | 1 | — | l3 | — | — | sync region data by hash | 1785 |
| `getAreaToBeTransferred` | 8 | 1 | 3 | — | — | — | Pre-charge get area-to-transfer | 756 |
| `getDynamicsLine` (app) | 8 | 1 | 18 | — | — | — | Dynamic route line (3s throttle) | app 941 |
| `recoverDumping` | 12 | — | 12 | — | — | — | Recover dumping op | 1132 |
| `recoverDrawCorridorLine` | 12 | — | 19 | — | — | — | MN231 recover corridor line | 1124 |
| `recoverDrawCorridorPoint` | 12 | — | 20 | — | — | — | MN231 recover corridor point | 1128 |
| `setDataSynchronization(i3)` | 12 | — | i3 | — | — | — | Sync region/obstacle/channel/edit/revoke | 1546 |

### Dumping (action=14/15)

| Method | action | type | Line |
|---|---|---|---|
| `enterDumpingStatus` | 14 | 12 | 539 |
| `outDropDumpingAdd` | 15 | 12 | 1037 |

### Pattern visibility (action=16)

| Method | action | type | hash | Notes | Line |
|---|---|---|---|---|---|
| `setPatternHideOrShow(i3, j3)` | 16 | i3 | j3 | Show/hide pattern | 1639 |

### X5 / radar / 431 (action=19/21/23/24/25)

| Method | action | type | Notes | Line |
|---|---|---|---|---|
| `startDrawBorder431` | 19 | 0 | 431 start boundary (X5) | 1710 |
| `startPositioning431All` | 21 | 17 | 431 planned radar positioning | 1730 |
| `startRecordCharge` | 21 | 5 | Start recording recharge channel | app 1838 |
| `getUpperLimit(i3)` | 24 | i3 | X5 query area-count upper limit | app 1007 |
| `autoAddLawn` | 25 | 0 | X5 auto-add lawn | app 426 |

### Edge / boundary edit

| Method | action | type | Line |
|---|---|---|---|
| `setEdgewiseMapping(i3)` | i3 | 0 | 1595 |
| `setEditBoundary(i3)` | i3 | 0 | 1599 |

---

## Hash list — `MctlNav.todev_gethash` (`NavGetHashList`)

| Method | sub_cmd | total_frame | current_frame | Purpose | Line |
|---|---|---|---|---|---|
| `getAllBoundaryHashList(i3, i4)` | i3 | — | — | Request hash list (caller picks load mode 0/3/4/5) | 702 |
| `getHashResponse(i3, i4)` | 2 | i3 | i4 | Ack hash-list frame and request next | 896 |

`HashDataManager` callsites confirm `sub_cmd` values used: `getAllBoundaryHashList(0, 1)`, `(3, 3)`, `(0, 2)` (lines 484, 1282, 1811 of `app/HashDataManager.java`).

---

## Coverage paths / lines

| Method | Field | Params | Notes | Line |
|---|---|---|---|---|
| `getLineInfo(j3)` | `todev_zigzag_ack` (`NavUploadZigZagResultAck`) | pver=1, current_hash=j3, sub_cmd=0 | Request zigzag/line data for one hash | 900 |
| `getLineInfoList(hashes, txId)` | `app_request_cover_paths` (`app_request_cover_paths_t`) | pver=1, hash_list, transaction_id, sub_cmd=0 | Batched cover-path request | 905 |
| `GenerateRouteInformation(genRouteInfo)` | `bidire_reqconver_path` (`NavReqCoverPath`) | pver=1, sub_cmd=`bean.getSubCmd()` plus all route params | Generate route | 318 |
| `modifyGenerateRouteInformation` | `bidire_reqconver_path` | pver=1, sub_cmd=3 | Modify route params | 1016 |
| `queryGenerateRouteInformation` | `bidire_reqconver_path` | pver=1, sub_cmd=2 | Query route config | 1075 |
| `endGenerateRouteInformation` | `bidire_reqconver_path` | pver=1, sub_cmd=9 | End route generation | 533 |

`NavReqCoverPath` fields used by `GenerateRouteInformation`: `pver, sub_cmd, zone_hashs[], job_mode, edge_mode, knife_height, speed, ultra_wave, channel_width, channel_mode, toward, toward_included_angle, toward_mode, reserved (=path_order), ride_boundary_distance, app_display_mode`.

---

## Edgewise mapping ack — `MctlNav.toapp_edge_points_ack` (`NavEdgePointsAck`)

| Method | Params | Notes | Line |
|---|---|---|---|
| `responseEdgewiseMapping(bean)` | action, hash, result, type, total_frame, current_frame | Ack edge-mapping data frame | 1286 |

---

## SVG — `MctlNav.todev_svg_msg` (`svg_message_ack_t`)

| Method | sub_cmd | total_frame | current_frame | data_hash | paternal_hash_a | result | svg_message_t | Line |
|---|---|---|---|---|---|---|---|---|
| `sendSvgDate(bean)` | bean.subCmd | bean.total | bean.current | bean.dataHash | bean.paternalHashA | bean.result | Yes: x/y move, scale, rotate, svg_file_name, svg_file_data, name_count, base_width_m, base_height_m, data_count | 1399 |
| `sendResponseSvgDate(bean)` | 2 | bean.total | bean.current | bean.dataHash | bean.paternalHashA | — | — | 1355 |

---

## Area name — `MctlNav.toapp_map_name_msg` (`NavMapNameMsg`)

| Method | rw | hash | name | device_id | result | Notes | Line |
|---|---|---|---|---|---|---|---|
| `getAreaNameList(ctx, deviceId, ...)` | 0 | 0 | — | str | 0 | Request area name list (skipped on Luba1) | 714 / 1972 |
| `areaRename(deviceId, hash, name, write)` | 1 if write else 0 | hash | str2 | str | 0 | Rename area | 390 |

---

## Manual elements — `MctlNav.toapp_manual_element` (`ManualElementMessage`)

| Method | sub_cmd | type | shape | data_hash | extras | Notes | Line |
|---|---|---|---|---|---|---|---|
| `addManualElementMessage(el, link)` | el.subCmd | el.type | el.shape | (none) | point1_center_xy, point2_width/height, rotate_radius | Add visual obstacle/zone | 353 |
| `deleteManualElementMessage(hash, type, shape, isAll, link)` | 2 if isAll else 1 | i3 | i4 | j3 | — | Delete visual zone | 495 |
| `sendDate(elementMessageBean)` (app-helper) | bean.subCmd | bean.type | bean.shape | bean.dataHash | point1_xy, point2_wh, rotate_radius, data_couple[], point_count | Generic element data set | app 1401 |

---

## Plans / scheduling

### Plan job set — `MctlNav.todev_planjob_set` (`NavPlanJobSet`)

| Method | sub_cmd | Notes | Line |
|---|---|---|---|
| `deletePlan(i3, str)` (app) | i3 | Delete schedule by planId | app 562 |
| `sendSchedule(planBean1)` (app) | bean.subCmd | Full plan set; uses pver, area, device_id, work_time, version, id, user_id, plan_id, task_id, job_id, start_time/end_time, week, knife_height, model, edge_mode, required_time, route_angle, route_model, route_spacing, ultrasonic_barrier, total_plan_num, plan_index, result, speed, ride_boundary_distance, task_name, zone_hashs[], reserved, weeks[], start_date, trigger_type, day=interval_days, toward_mode, toward_included_angle | app 1461 |
| `readPlan(i3, i4, i5)` (app) | i3 | Read plan by index | app 1171 |

### Plan task execute — `MctlNav.plan_task_execute` (`nav_plan_task_execute`)

| Method | sub_cmd | id | Notes | Line |
|---|---|---|---|---|
| `singleSchedule(id)` | 1 | str | Immediately execute plan | 1673 |

### Unable-time (do-not-disturb) — `MctlNav.todev_unable_time_set` (`NavUnableTimeSet`)

| Method | sub_cmd | trigger | Other | Line |
|---|---|---|---|---|
| `jobDoNotDisturb(bean, link)` | 1 | 1 | unable_start_time, unable_end_time | 986 |
| `jobDoNotDisturbDel(link)` | 1 | 0 | — | 994 |
| `jobDoNotDisturbRead(i3, link)` | 2 | — | — | 998 |
| `jobAnimalProtectRead(i3)` | 2 | 99 | — | 981 |
| `setPlanUnableTime(i3, devId, end, start)` | i3 | — | device_id, unable_start_time, unable_end_time, result=0, reserved="0" | 1643 |

### Spino (PC210 / swimming-pool) plans — `SpinoCtrl.plan_job_set` (`PlanJobSet`)

| Method | cmd | Notes | Line |
|---|---|---|---|
| `sendSchedule_SP(bean, link)` | bean.cmd | Full PC210 plan: work_mode, job_id, job_name, trigger_type, start_time, end_date, user_id, device_id, start_date, day, weeks[], enable, sub_modes[], total_plan_num, plan_index, result, operating_power, remained_seconds, speed | 1359 |
| `readPlan_SP(planCmd, idx, logType, link)` | planCmd | plan_index | 1120 |
| `deletePlan_SP(planCmd, jobId, link)` | planCmd | job_id | 514 |

### Pool wall material / floor speed / docking — `MctlSys.app_downlink_cmd` (`app_downlink_cmd_t`)

| Method | cmd | ack | extra | Notes | Line |
|---|---|---|---|---|---|
| `getSpLine(link)` | `app_get_line_cmd` | WAIT_ACK | dummy MapInfo + MapPoints(1,1) | Get pool line | 941 |
| `getSpMap(link)` | `app_get_map_cmd` | WAIT_ACK | dummy MapInfo | Get pool map | 949 |
| `spEnvironmentUpdate(i3, query, link)` | `app_wall_material_cmd` | INQUIRY (query) or WAIT_ACK | wall_material=i3 | Pool wall material set/query | 1678 |
| `spSpeedUpdate(f3, query, link)` | `app_floor_speed_cmd` | INQUIRY or — | floor_speed | Pool floor speed | 1688 |
| `spTimedWaterlineUpdate(type, query, h, m)` (app) | `app_docking_time_cmd` | INQUIRY (query) or WAIT_ACK | docking_time(hours,minutes), type | Poolside docking time | app 1788 |

### Pool work mode — `MctlSys.set_work_mode` (`work_mode_t`)

| Method | work_mode | extras | Notes | Line |
|---|---|---|---|---|
| `sendSwtichSwimmingWorkModule(link, module)` | module.workMode | — | Switch pool work module | 1434 |
| `sendSwtichSwimmingSPWorkModule(mode, subList, dev, speed, power)` (app) | i3 | sub_modes[], speed=((speed*100)-10), operating_power | If mode=6 add custom_list[] | app 1540 |

---

## Manual control — `MctlDriver`

| Method | Field | Params | Line |
|---|---|---|---|
| `OperateOnDevice(main, knife, height, speed, pos)` | `setMowCtrlByHand` (`DrvMowCtrlByHand`) | main_ctrl, cut_knife_ctrl, cut_knife_height, max_run_speed | 341 |
| `sendControl(linear, angular, link)` | `setTodevDevmotionCtrl` (`DrvMotionCtrl`) | set_linear_speed, set_angular_speed | 1313 |
| `manualGrassCollection(i3)` | `setCollectCtrlByHand` (`DrvCollectCtrlByHand`) | collect_ctrl | 1003 |
| `manualPourGrass(i3)` | `setCollectCtrlByHand` | unload_ctrl | 1012 |
| `setKnifeHight(i3)` | `setTodevKnifeHightSet` (`DrvKnifeHeight`) | knife_height | 1615 |
| `setSpeed(f3, link)` | `setBidireSpeedReadSet` (`DrvSrSpeed`) | rw=1, speed | 1653 |
| `getSpeed()` / `getSpeed(link)` | `setBidireSpeedReadSet` | rw=0 | 957 / 1839 |
| `sendGetCutterMode` | `setCurrentCutterMode` (`AppGetCutterWorkMode`) | (empty) | 1323 |
| `sendSetCutterMode(i3)` | `setCutterModeCtrlByHand` (`AppSetCutterWorkMode`) | cutter_mode | 1384 |
| `setNavStarPoint(str)` | `setRtkCfgReq` (`rtk_cfg_req_t`) | cmd_req, cmd_length=str.length-1 | 1625 |
| `synNavStarPointData(i3)` | `setRtkSysMaskQuery` (`rtk_sys_mask_query_t`) | sat_system | 1756 |

---

## Vision / radar — `MctlNav.vision_ctrl` (`vision_ctrl_msg`)

| Method | cmd | type | rcver | Notes | Line |
|---|---|---|---|---|---|
| `radarTestSend(i3)` | i3 | 1 | DEV_PERCEPTION | Radar static-test on/off | 1085 |

---

## Simulation / tools — `MctlNav.simulation_cmd` / `MctlSys.simulation_cmd`

| Method | Field | sub_cmd | param_id | param_value[] | Line |
|---|---|---|---|---|---|
| `indoorSimulation(i3)` | `MctlNav.simulation_cmd` (`SimulationCmdData`) | i3 | — | — | 977 |
| `sendToolsOrder(i3, list)` | `MctlNav.simulation_cmd` | 2 | i3 | list | 1461 |
| `testToolOrderToSys(i3, i4, list)` | `MctlSys.simulation_cmd` (`mCtrlSimulationCmdData`) | i3 | i4 | list | 1789 |

---

## Sys-param / common read-write — `MctlNav.nav_sys_param_cmd` (`nav_sys_param_msg`) and `MctlSys.bidire_comm_cmd` (`SysCommCmd`)

| Method | Field | id | context | rw | Notes | Line |
|---|---|---|---|---|---|---|
| `allpowerfullRW(id, ctx, rw)` | `MctlSys.bidire_comm_cmd` | id | ctx | rw | Generic RW; routes via `nav_sys_param_cmd` instead if id in {3,6,7,8,10,11} AND LubaPro | 367 |
| `allpowerfullRWAdapterX3(id, ctx, rw)` | `MctlNav.nav_sys_param_cmd` | id | ctx | rw | Generic RW (X3 adapter) | 382 |
| `allAnimalProtect(id, ctx, rw)` | `MctlNav.nav_sys_param_cmd` | id | ctx | rw | Animal protect set | 363 |
| `getAllAnimalProtect(id, rw)` | `MctlNav.nav_sys_param_cmd` | id | — | rw | Animal protect read | 698 |
| `getAnimalProtectMode(id, rw)` | `MctlNav.nav_sys_param_cmd` | id | — | rw | Animal protect mode | 706 |
| `getRechargeAndContinueWorking(id, rw, link)` | `MctlNav.nav_sys_param_cmd` | id | — | rw | id 14/15 read | 920 |
| `setRechargeAndContinueWorking(id, ctx, rw, link)` | `MctlNav.nav_sys_param_cmd` | id | ctx | rw | id 14/15 set | 1649 |

---

## Sleep / low-power — `MctlSys.{to_set_dev_low_power_cmd,to_get_dev_low_power_cmd}`

| Method | Field | Params | Line |
|---|---|---|---|
| `setChargingSleepStatus(z2)` | `to_set_dev_low_power_cmd` (`dev_low_power_set_info`) | set_charging_lowpower_sta=true, charging_low_power=z2?1:0, set_uncharging_lowpower_sta=false | 1535 |
| `setUnChargingSleepStatus(z2)` | same | set_uncharging_lowpower_sta=true, uncharging_low_power=z2?1:0, set_charging_lowpower_sta=false | 1665 |
| `getChargingSleepStatus` | `to_get_dev_low_power_cmd` (`dev_low_power_get`) | charging_low_power=0 | 789 |
| `getUnChargingSleepStatus` | same | uncharging_low_power=0 | 969 |

---

## Battery / BMS — `MctlSys.bms_ctrl_info_msg` (`BmsCtrlInfoMsg`)

| Method | Params | Line |
|---|---|---|
| `queryBatteryInfo(link)` | smart_charge_switch=-1, peak_valley_charge_switch=-1 (probe) | 1069 |
| `setBatteryInfo(smart, soc, peakValley, start, end, link)` | smart_charge_switch=!smart, charge_soc_threshold=(smart?100:soc), peak_valley_charge_switch=peakValley, valley_charge_start_time, valley_charge_end_time | 1491 |

---

## Date / time — `MctlSys.todev_data_time` (`SysSetDateTime`)

| Method | Params | Line |
|---|---|---|
| `sendSysSetDateTime` | year, month, date, week, hours, minutes, seconds, time_zone(min), daylight(min) | 1440 |

`synTime()` (line 1760) is a JSON variant (subCmd=57) for legacy JSON-mode devices.

---

## Lights / wiper / audio — multimedia (`LubaMul.SocMul`)

`setHeadlamp` / `getHeadlamp`:

| Method | Field | set_ids | extra | Line |
|---|---|---|---|---|
| `getCarNightLight(i3, link)` | `setGetLamp` (`GetHeadlamp`) | get_ids=i3 | — | 785 |
| `setCarLampCtrlNightLight(on, mode, setId)` | `setSetLamp` (`SetHeadlamp`) | i4 | lamp_power_ctrl=1, lamp_ctrl per (mode, on), ctrl_lamp_bright=false, lamp_bright=0 | 1508 |
| `setCarLampCtrlHandMovement(on, setId, link)` | `setSetLamp` | i3 | lamp_power_ctrl=2, lamp_manual_ctrl per `on` | 1504 |

Audio / wiper:

| Method | Field | Params | Line |
|---|---|---|---|
| `getCarAudioCfg` | `setAudioCfg` (`MulAudioCfg`) | (empty) | 778 |
| `setCarVoiceLanguage(i3)` | `setSetAudio` (`MulSetAudio`) | au_language=i3 | 1513 |
| `setCarVolume(i3)` | `setSetAudio` | au_switch=i3 | 1520 |
| `setCarVolumeSex(i3)` | `setSetAudio` | sex=`MUL_SEX.valueOf(i3)` | 1524 |
| `setVolumeValue(i3)` (app) | `setSetAudio` | au_volume=i3 | app 1772 |
| `setCarWiper(i3)` | `setSetWiper` (`MulSetWiper`) | round=i3 | 1531 |

Video / FPV / camera:

| Method | Field | Params | Line |
|---|---|---|---|
| `refreshFPV` | `setReqEncode` (`MulSetEncode`) | encode=true | 1136 |
| `deviceAgoraJoinChannelWithPosition(i3)` (app) | `setSetVideo` (`MulSetVideo`) | position (ALL for Yuka, else LEFT), vi_switch=i3 | app 570 |

---

## Side-light / time-ctrl-light — `MctlSys.todev_time_ctrl_light` (`TimeCtrlLight`)

| Method | enable | operate | Notes | Line |
|---|---|---|---|---|
| `readAndSetSidelight(z2, i3)` | 0 if z2 else 1 | i3 | action=0, start/end hour/min=0 | 1114 |

---

## Blade timer

| Method | Field | Params | Line |
|---|---|---|---|
| `resetBladeTime` | `setTodevResetBladeUsedTime(1)` | — | 1278 |
| `setBladeWarningTime(hours)` | `setBladeUsedWarnTime` (`user_set_blade_used_warn_time`) | blade_used_warn_time=hours*3600 | 1499 |

---

## Device factory reset / remote restart

| Method | Field | Params | Line |
|---|---|---|---|
| `resetSystem` | `setTodevResetSystem(1)` | — | 1282 |
| `remoteRestart(force, account)` | `setToDevRemoteReset` (`remote_reset_req_t`) | magic=1916956532, bizid=System.currentTimeMillis(), reset_mode=0, force_reset, account | 1140 |

---

## OTA — `MctlOta`

| Method | Field | Params | Notes | Line |
|---|---|---|---|---|
| `getDeviceInfoNew` | `setTodevGetInfoReq` (`getInfoReq`) | type=IT_BASE | Get base info | 852 |
| `getDeviceOTAInfo(i3)` | `setTodevGetInfoReq` | type=IT_OTA | Get OTA info | 864 |
| `notifyFirmwareSendFinish` | `setFwDownloadCtrl` (`fwDownloadCtrl`) | downlink=empty, cmd=5 | Firmware-send-finish | 1031 |
| `startSwimmingPoolDeviceOta(str)` | `setFwDownloadCtrl` | cmd=1, downlink.data=int-list(str) | Pool OTA start | 1736 |
| `sendSwimmingPoolDeviceOtaFirst(imgSize, otaNum, _, _, ver)` | `setFotaInfo` (`FotaInfo_t`) | need_ota_num, need_ota_img_size, ota_otype=1, ota_version, ota_oid="1" | Pool OTA first | 1404 |
| `sendSwimmingPoolDeviceOtaPackage(data, fwId, pkgSeq, _)` | `setFwDownloadCtrl` | cmd=3, downlink.{fw_id, pkg_seq, data} | Pool OTA package | 1412 |
| `sendSwimmingPoolDeviceOtaSecond(subId, imgSize, url, ver)` | `setFotaSubInfo` (`FotaSubInfo_t`) | sub_mod_ota_flag=1, sub_mod_id, sub_img_size, sub_mod_version, sub_img_url | Pool OTA second | 1423 |

---

## Net / WiFi / 4G — `DevNetOuterClass.DevNet`

### BLE-sync heartbeats

| Method | Field | type | Notes | Line |
|---|---|---|---|---|
| `sendTodevBleSync()` | `setTodevBleSync(2)` | 2 | App→device BLE heartbeat | 1455 |
| `sendBlueToothDeviceSync(i3, name, logType)` | `setTodevBleSync(i3)` | i3 | Variant with explicit type | 1306 |
| `sendIotDeviceSync(iotId, name, i3, logType)` | `setTodevBleSync(i3)` wrapped as IOT JSON | i3 | IOT heartbeat (uses `PROTOBUF_SYNC_SERVICE`) | 1327 |
| `sendTodevBleSync(blufi, link, i3)` | `setTodevBleSync(2)` | 2 | Skipped when i3==1 and IOT-supported | 1847 |

### WiFi

| Method | Field | Params | Line |
|---|---|---|---|
| `getRecordWifiList(binary)` | `setTodevBleSync(1) + setTodevWifiListUpload(DrvWifiList)` | — | 924 |
| `wifiConnectinfoUpdate(name, binary)` | `setTodevBleSync(1) + setTodevWifiMsgUpload(DrvWifiUpload)` | wifi_msg_upload=1 | 1795 |
| `close_clear_connect_current_wifi(ssid, status, binary)` | `setTodevBleSync(1) + setTodevWifiConfiguration(DrvWifiSet)` | config_param=status, confssid=ssid | 457 |
| `setDeviceWifiEnableStatus(z2)` | `setTodevBleSync(1) + setTodevWifiConfiguration(DrvWifiSet)` | config_param=4, wifi_enable=z2 | 1591 |

### 4G / network info

| Method | Field | Notes | Line |
|---|---|---|---|
| `get4GInfo` | `setTodevMnetInfoReq` | Get 4G info | 690 |
| `get4GModuleInfo` | `setTodevGetMnetCfgReq` | Get 4G module info | 694 |
| `set4GNetApnInfo(apn)` | `setTodevSetMnetCfgReq` (`SetMnetCfgReq`) | apn name; inet_enable=true, mnet_enable=true | 1465 |
| `setDevice4GEnableStatus(z2)` | `setTodevBleSync(1) + setTodevSetMnetCfgReq` | type=NET_TYPE_WIFI, inet/mnet=z2 | 1561 |
| `getDeviceNetWorkInfo` | `setTodevNetworkinfoReq` (`GetNetworkInfoReq`) | req_ids=1 | 860 |
| `setMTUValue(i3)` | `setTodevSetBleMtu` (`SetDrvBleMTU`) | mtu_count=i3 | 1620 |
| `setIotSetting(type)` | `setTodevSetIotOfflineReq(type)` | — | 1611 |
| `setZMQEnable` | `setTodevSetDds2Zmq` (`DrvDebugDdsZmq`) | is_enable=true, rx_topic="perception_post_result", tx_zmq_url="tcp://0.0.0.0:5555" | 1669 |
| `setINaviSwitchNetConnectType(i3, link)` | `MctlSys.setAppToDevSetMqttRtkMsg` (`app_to_dev_set_mqtt_rtk_t`) | set_nrtk_net_mode=i3 | 1603 |
| `cancelInaviCalibration(link)` | `MctlSys.setAppToDevSetMqttRtkMsg` | stop_nrtk_flag=1 | 423 |
| `setNetRtkLinkMode(i3, link)` | `MctlSys.setAppToDevSetMqttRtkMsg` | set_rtk_mode=`rtk_used_type.forNumber(i3)` (0=数传, 1=网络, 2=nrtk) | 1631 |

### Device info / version

| Method | Field | Notes | Line |
|---|---|---|---|
| `getDeviceBaseInfo` | `setTodevDevinfoReq` (`DrvDevInfoReq`) | Loop ids 1..7, types 3 & 6 for id=1 | 793 |
| `getDeviceVersionMain(str)` | `setTodevDevinfoReq` | id=1, type=6 | 882 |
| `getDeviceVersionMain2` | same | same | 890 |
| `getDeviceVersionInfo` | `MctlSys.setTodevGetDevFwInfo(1)` | New version interface | 878 |
| `getDeviceProductModel(link)` | `MctlSys.setDeviceProductTypeInfo` (`device_product_type_info_t`) | empty body | 870 |

### BLE pairing — `DevNet.todev_ble_pair_req` (`BlePairReq`) (app-helper only)

| Method | action | Line |
|---|---|---|
| `bluetoothPairing` (app) | `REQUEST_PAIR` | app 435 |
| `queryPairingStatus` (app) | `QUERY_PAIR_STATUS` | app 1138 |
| `deletePairing` (app) | `DELETE_BOND` | app 557 |

### BLE encrypt / signature

| Method | Field | Params | Line |
|---|---|---|---|
| `sendSignVerification(rsa, random)` | `setTodevVerifySignatureReq` (`BleSignatureReq`) | signature_data=rsa, random_data=random | 1388 |
| `sendDeviceIdentity(result, identity, key)` (app) | `setTodevGetIdentityRsp` (`GetIdentityRsp`) | req_id, result, identity_data, decryption_key | app 1411 |

### Log upload — `DevNet.todev_uploadfile_req` / `todev_log_data_cancel` / `todev_req_log_info`

| Method | Field | Params | Line |
|---|---|---|---|
| `setDeviceLogUpload(id, op, ip, port, num, type)` | `setTodevBleSync(1) + setTodevUploadfileReq` (`DrvUploadFileToAppReq`) | biz_id, operation, server_ip, server_port, num, type | 1583 |
| `setDeviceSocketRequest(...)` | same as above | same | 1587 |
| `getDeviceLogInfo(id, type, url)` | `setTodevBleSync(1) + setTodevReqLogInfo` (`DrvUploadFileReq`) | biz_id, type, url, num=0, user_id | 856 |
| `cancelLogUpdate(id)` | `setTodevLogDataCancel` (`DrvUploadFileCancel`) | biz_id | 431 |

---

## Sys-misc — `MctlSys`

| Method | Field | Params | Line |
|---|---|---|---|
| `setDebugEnable(i3)` | `setDebugEnable` (`debug_enable_t`) | enbale=i3 | 1557 |
| `setDebugConfig(key, val)` | `setDebugCfgWrite` (`debug_cfg_write_t`) | key, value | 1553 |
| `setAllDebugConfig` | `setDebugResCfgAbility` (`debug_res_cfg_ability_t`) | total_keys=0, cur_key_id=-1, value="", keys="" | 1469 |
| `setClearFlash` | JSON sub_cmd=580 (subCMD=68, param="4321") | — | 1539 |
| `factoryTestOrder(type, duration, expectJson)` | `setMowToAppQctoolsInfo` (`mow_to_app_qctools_info_t`) | type, time_of_duration, optional QCAppTestExcept[]/QCAppTestConditions[] parsed from JSON | 551 |
| `sendFactoryTestComplete(i3)` | `setMowToAppQctoolsInfo` | type=QC_APP_TEST_COMPLETE_SIGNAL, result=i3 | 1319 |
| `toDevMsgBus(i3)` (app) | `setToDevMsgbus` (`msgbus_pkt`) | send=7, recv=1, type=130, type_command=120, data=base64("release"/"calibrationZero"/"calibrationAuto") | app 1890 |
| `sendCompleteReport(i3, items)` (app) | `setTaskReportResult` (`FileTransferResult`) | type=`result_type_e.forNumber(i3)`, items=arrayList | app 1385 |
| `sendConfirmReport(workId, frameSeq, bizId, errCode)` (app) | `setTaskReportResp` (`FileTransferResponse`) | biz_id, results.{work_id, frame_sequence, error_code} | app 1389 |
| `sendReceiveWorkReport` (app) | `setTaskReportInteraction` (`task_report_interaction_t`) | signal=1 | app 1453 |
| `requestSwimmingJobHistory` (app) | `setResponseSetMode` (`response_set_mode_t`) | statue=2 | app 1337 |
| `changeEnvironment(cmd, env, account, name)` (app) | `setIotProductParamReq` (`iot_product_param_req_t`) | account, cmd, origin_device_name, test_key (product_key, product_secret, device_name, device_secret) | app 478 |

---

## Lora / GFSK pairing — `MctlSys`

| Method | Field | Params | Line |
|---|---|---|---|
| `readAndSetRtKParingCode(op, cfg, link)` | `setTodevLoraCfgReq` (`LoraCfgReq`) | op, cfg | 1106 |
| `readAndSetGfskCfg(cmd, cfg, link)` | `setGfskCfgCmd` (`gfsk_cfg_cmd_t`) | cmd, cfg | 1095 |

---

## Base station — `Basestation.BaseStation`

| Method | Field | Params | Notes | Line |
|---|---|---|---|---|
| `getBaseStation(name, logType)` | `setToDev` (`request_basestation_info_t`) | request_type=1 | Routed BLE→IOT manually | 760 |
| `setBaseNetRtkSwitch(bean, name)` | `setAppToBaseMqttRtkMsg` (`app_to_base_mqtt_rtk_t`) | rtk_switch | Routed BLE→IOT manually | 1473 |

---

## Work-report / job-history — `MctlNav.todev_work_report_*`

| Method | Field | sub_cmd | Notes | Line |
|---|---|---|---|---|
| `queryJobHistory` | `setTodevWorkReportUpdateCmd` (`WorkReportUpdateCmd`) | 1 | Check for updates | 1081 |
| `requestJobHistory(i3)` | `setTodevWorkReportCmd` (`WorkReportCmdData`) | 1, get_info_num=i3 | Fetch N records | 1232 |
| `getTask` | JSON cmd=213 (params: pver=1, subCmd=2, result=0) | — | Legacy JSON | 961 |

---

## Subscription / reporting — `MctlSys.todev_report_cfg` (`report_info_cfg`)

`getMctrlSysBuilder(act, ids[], timeout, period, no_change_period, count)` (line 911). Used to start/stop polling of `rpt_info_type` enum values.

Common bundles:

| Method | act | Subscribed ids | timeout/period/noChange/count | Line |
|---|---|---|---|---|
| `requestConnectingChannels(iotResp, i3, log)` | RPT_START | CONNECT, RTK, DEV_LOCAL, WORK, DEV_STA, VISION_POINT, VIO, VISION_STATISTIC, MAINTAIN, BASESTATION_INFO | 10000/1000/4000/i3 | 1144 |
| `requestHomeConnectStatus(iotResp)` | RPT_START | CONNECT, DEV_STA | 10000/1000/4000/1 | 1150 |
| `requestIOTMessage(deviceId)` | RPT_START | CONNECT, RTK, DEV_LOCAL, WORK, DEV_STA, MAINTAIN, VISION_POINT, VIO, VISION_STATISTIC (app adds CUTTER_INFO) | 10000/3000/4000/0 | 1154 / app 1209 |
| `requestIOTStopMessage(deviceId)` | RPT_STOP | same as above | 10000/1000/1000/0 | 1186 / app 1241 |
| `requestMAINITAINData(iotResp, period, noChange)` | RPT_START | CONNECT, DEV_STA, VISION_POINT, VIO, MAINTAIN | 10000/period/noChange/countKeep | 1236 |
| `requestMapLocationBTorIOTData(iotResp, period, noChange, isBT, log)` | RPT_START | CONNECT, RTK, DEV_LOCAL, WORK, DEV_STA, VISION_POINT, VIO, VISION_STATISTIC, BASESTATION_INFO (app adds CUTTER_INFO) | 10000/period/noChange/countKeep | 1245 / app 1300 |
| `requestMapLocationData(iotResp, period, noChange, name, log)` | RPT_START | same as above | 10000/period/noChange/countKeep | 1265 |
| `requestIot_Sys(actInt, ids, log, isIot, iotResp)` | `forNumber(actInt)` | caller-supplied | 5000/1000/2000/0 | 1223 |

---

## JSON-mode commands (legacy non-protobuf, transmitted via `postCustomData`)

`postCustomData` writes UTF-8 JSON `{cmd, id, params}` over the same link.

| Method | JSON_CMD | params | Notes | Line |
|---|---|---|---|---|
| `sendBleAlive` | 59 | `ctrl:"1"` | BLE keepalive (text) | 1302 |
| `synTime` | 57 | year/month/date/week/hours/minutes/seconds/timeZone/daylight | Legacy time sync | 1760 |
| `getRecordWifiList2` | 69 | — | Legacy WiFi list query | 933 |
| `wifiConnectinfoUpdate2` | 68 | getMsgCmd=1 | Legacy WiFi info | 1805 |
| `close_clear_connect_current_wifi2` | 77 | ssid, getMsgCmd | Legacy WiFi op | 465 |
| `getDeviceInfo` | 63 | — | Legacy device info | 848 |
| `getDeviceBorderState` | 64 | — | Legacy border-state | 844 |
| `noticeReportRoutes` | 26 | — | Notify report routes | 1027 |
| `getTask` | 213 | pver=1, subCmd=2, result=0 | Legacy task query | 961 |
| `setClearFlash` | 580 | subCMD=68, param="4321" | Erase flash | 1539 |
| `getDeviceBaseInfo2` | 38 | reqInfo[{id, type:3}] for id=5..7 | Legacy base info (JSON variant) | 806 |
| `getDeviceBaseInfoMian` | 38 | reqInfo[{id:1, type:6}] | Legacy main version | 826 |

---

## Helpers / utilities

These are not user-facing commands but they shape outgoing payloads:

- `clearSeqBle` (line 449) — resets `seq_ble` counter
- `postCustomData(byte[], tag)` (line 1045) — direct raw byte path
- `postBlueToothDateByte` (line 192) — bluetooth-forced byte path

---

## Notes for pymammotion

- **Map fetch / report channel docs**: see existing `docs/hash_guide.md`, `docs/report_channels.md`, `docs/common_data_types.md`. This catalog does not re-describe those flows; it only enumerates the call sites.
- **MQTT vs BLE**: every `sendOrderMsg_*` call passes `isIotable`; `true` allows IOT/MQTT, `false` forces BLE. The "force BLE" set in `MACommandHelper.java` is: `sendBlueToothDeviceSync`, `sendTodevBleSync`, `sendSignVerification`, `cancelLogUpdate`, `getDeviceLogInfo`, `getDeviceOTAInfo`, `notifyFirmwareSendFinish`, `setDeviceSocketRequest`, `bluetoothPairing`, `deletePairing`, `queryPairingStatus`, `resetBaseStation`, `setMTUValue` callers via Net, all `sendSwimmingPool*Ota*` variants, `startDrawBorder`, `startDrawBorder431`, `startDrawCorridor`, `startPositioning431All`, `giveUpDrawCorridor`, `recoverDrawCorridor*`, `stopAndNotSaveTask`, `saveTask`.
- **Account / userId**: `subtype` in every frame is `Integer.parseInt(SharedPreferencesMgr.getString("account", "102"))` — pymammotion currently hardcodes 1 in some paths; this is an account-tracking identifier, not a sequence.
- **Seq behaviour**: `seq_ble` is per `MACommandHelper` instance (per device). It increments on **every** outgoing frame including failures. Reset only via `clearSeqBle()`.
- **`logtype` (the int passed to `sendMsg`)** is not a protocol field; it's only logged. Don't try to match it.

---

## Files cited

- `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/command/MACommandHelper.java` — top-level builder, 2042 lines
- `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/command/app/MACommandApiHelper.java` — per-device facade, 1972 lines
- `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/command/app/HashDataManager.java` — hash/map orchestration
- `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/command/CommandManager.java` — Kotlin coroutine wrappers
- `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/command/MapCommandManager.java` — routing/registry only
- `/home/michael/Downloads/mammotion-2-3-8-201/agilex/java_src/com/agilexrobotics/command/menus/MsgCmdType.java`, `PbMsgType.java` — enums
