# Cloud remote drive ("FPV control")

Driving the mower by joystick over the cloud, the way the app does it from its FPV
video page. Ported from APK 2.3.20.30: `command/fpvdrive/internal/RemoteDriveControllerImpl`,
`ControlTokenRepository`, `map/fpvdrive/FpvDriveUiCoordinator`, and
`MACommandApiHelper.sendSessionControl` / `sendSessionExitNotify`. The code lives in
`pymammotion/device/remote_drive.py`. `MammotionClient` exposes it as
`start_remote_drive` / `confirm_remote_drive` / `remote_drive` / `stop_remote_drive` /
`subscribe_remote_drive` / `set_remote_drive_video_ready` / `acknowledge_remote_drive_fence`.

Over BLE the app does not use a session: it sends the legacy `DrvMotionCtrl`
(`send_movement`). A session is cloud-only. It refuses to start without a usable cloud
transport and never falls back to BLE.

## Wire

| step | what |
|---|---|
| token | `POST /device-server/v1/fpv/control/token` `{"deviceId": iotId}`. The response `data` is `FpvControl`: `deviceResult`, `token`, `expireIn` (s), `timeoutExit` (s), `latencyThreshold` (ms), `preemptUser`, `fps4G`, timestamps |
| renew | `POST …/fpv/control/refresh-token` `{"deviceId", "token"}` at `expireIn − 60` s |
| frame | `MctlDriver.todev_session_ctrl_req` (18): `ctrlSeq`, linear, angular, `channel=DRV_CTRL_IOT`, `appSendTsMs`, `vehicleSendTsMs` (echo of the last ack), `token`. Sent IoT-only with a 1 s invoke timeout on each attempt; a credential refresh between attempts is not timed |
| ack | `toapp_session_ctrl_ack` (19): `ctrlSeq`, `result`, `vehicleSendTsMs`, `appSendTsMs`, `measuredDelayMs`, `fenceExceedDistance`, `localizationValid`, `preemptAccount` |
| exit | `todev_session_exit_nfty` (20) `{token, channel}`. The device's own `toapp_session_exit_nfty` (21) is logged and otherwise ignored, as in the app |

Token outcome: envelope `code != 0` or no data → unavailable; `deviceResult` 0 with a
non-blank token → granted; 9 → occupied by `preemptUser`; anything else → unavailable.

## Phases

`IDLE → REQUESTING_TOKEN → SAFETY_NOTICE → ACTIVE → EXITING → IDLE`

- **SAFETY_NOTICE**: a zero-speed keep-alive with `ctrlSeq=0` goes out at once and then
  every 3 s, without waiting for an ack. It ends on `confirm()`, not on the first input.
  After 180 s unconfirmed the session exits with `SAFETY_NOTICE_TIMEOUT`.
- **ACTIVE**: one frame in flight at a time, at least 150 ms between frames. After each
  matched ack the last non-zero speed is repeated; a zero speed is not. `ctrlSeq`
  restarts at 0 after a ≥ 1 s gap, after an invoke timeout, and when input resumes during
  the idle countdown. An ack only counts if its `ctrlSeq` matches the frame in flight.
  Negative linear speed is sent as 0, because the app does not reverse over IoT.
  `drive(0, 0)` means hands off and starts the idle countdown (`timeoutExit`, default 10 s).
- **Exit**: when ACTIVE, a forced `(0, 0)` stop that does not wait for an ack; then the
  exit notify with the token. A token granted after `stop()` (or after a newer `start()`)
  is released with an exit notify at once, and `start()` returns False.

## Events

Ack results:
- 0, 3 and 5 keep driving.
- 4 and 11 → `NETWORK_POOR`.
- 6 and 7 → `TOKEN_EXPIRED`.
- 8 → `OUT_OF_FENCE`.
- 9 → `BLE_PREEMPT` (masked account).
- 10 → `NO_LOC_MILEAGE_EXHAUSTED`.
- Anything else → `ENV_NOT_READY`.

Other faults:
- Three consecutive invoke timeouts (a 1 s timeout or `GatewayTimeoutException`) →
  `NETWORK_POOR`. A send that needed a credential refresh counts only if its retry times out.
- A failed renewal → `TOKEN_EXPIRED`. An "occupied" answer to a renewal → `BLE_PREEMPT`.
- Any other send error → `SEND_FAILED`, carrying the exception.

A refused token request at start → `TOKEN_UNAVAILABLE` or `OCCUPIED_BY_OTHER`. These
event kinds end the session.

Two notices leave the session running:
- `APPROACH_FENCE`: `fenceExceedDistance ≥ 5` m with valid localisation stops the mower
  and drops input until `acknowledge_fence_warning()`.
- `LATENCY_HIGH`: sent once, when `measuredDelayMs ≥ latencyThreshold − 500`.

## Host responsibilities

- **Function code 002.002.** The app shows the entry only for this function code; check it with
  `DeviceHandle.supports_wifi_movement()`. The session does not check it.
- **Video.** The app requests no token and ends a session while its video has no frame.
  The library does not own the video, so this is opt-in. Pass
  `require_video=True` and report frames with `set_remote_drive_video_ready`. The app
  also hides the entry without a map (`bolHash ≤ 1`) and when the 4G video quota is spent.
- **Speed units.** Pass `drive()` wire units: the app sends rocker×10 linear and ×4.5
  angular after a 15 % dead zone.

## Differences from the app

- The app keeps a faulted session in `FAULTED` until the user dismisses the dialog, and
  releases the token then. The library releases it immediately.
- Input that arrives while a hold-repeat is queued replaces it rather than trailing it.
- The fence stop is sent a clock turn after the ack that triggers it. The queue is
  cleared when the ack arrives, not when the stop is sent, so input sent after an early
  `acknowledge_fence_warning()` is kept. Input sent while still paused is dropped.

## Unverified on hardware

- Every item above comes from the decompiled app; none of it has been run against a mower.
- Whether an Aliyun (pre-2025) device accepts session frames. The app's IoT path is the
  same invoke.
- Whether the server rejects a frame with no `token` or with a stale `vehicleSendTsMs`.
- The real latency of acks relative to the 150 ms pacing, and whether the 1 s invoke
  timeout trips often on a slow cloud.
