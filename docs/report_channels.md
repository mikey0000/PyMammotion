# Report Info Channels (`rpt_info_type`)

The device streams subsets of its state via the `todev_report_cfg`
(`ReportInfoCfg`) subscription mechanism.  The `sub` field is a list of
`rpt_info_type` enum values that selects which channels get populated in each
`toapp_report_data` payload.

See `pymammotion/mammotion/commands/messages/system.py` for the command
builders (`get_report_cfg`, `get_report_cfg_stop`, `request_iot_sys`).  See
`pymammotion/client.py` for the sys_status-driven rapid-stream watcher.

## Channel → payload field mapping

Each channel populates a specific field of `ReportInfoData`.  The table below
is derived from the APK's usage in `MACommandHelper.requestConnectingChannels`
and the proto definition in `MctrlSys.java`.

| Value | Name                   | Payload field                 | Contents (not exhaustive)                                          |
| ----- | ---------------------- | ----------------------------- | ------------------------------------------------------------------ |
| 0     | `RIT_CONNECT`          | `connect`                     | connection type, BLE/Wi-Fi/mnet RSSI, link state, IoT status       |
| 1     | `RIT_DEV_STA`          | `dev`                         | `sys_status`, `charge_state`, `battery_val`, sensor status, locks  |
| 2     | `RIT_RTK`              | `rtk`                         | RTK fix quality, GPS stars, LoRa / MQTT RTK info, score            |
| 3     | `RIT_DEV_LOCAL`        | `locations`                   | device position, heading, zone/bol hashes                          |
| 4     | `RIT_WORK`             | `work`                        | `path_hash`, `ub_path_hash`, `path_pos_x`/`y`, progress, knife     |
| 5     | `RIT_FW_INFO`          | `fw_info`                     | firmware module versions                                           |
| 6     | `RIT_MAINTAIN`         | `maintain`                    | mileage, work-time hours, blade-used time, battery cycles          |
| 7     | `RIT_VISION_POINT`     | `vision_point_info`           | detected vision point groups with (x, y, z) coordinates            |
| 8     | `RIT_VIO`              | `vio_to_app_info`             | visual-inertial odometry: x, y, heading, VIO state, feature counts |
| 9     | `RIT_VISION_STATISTIC` | `vision_statistic_info`       | vision pipeline statistics (mean, variance per group)              |
| 10    | `RIT_BASESTATION_INFO` | `basestation_info`            | RTK base station firmware, status, connect-since-poweron           |
| 11    | `RIT_CUTTER_INFO`      | `cutter_work_mode_info`       | current cutter mode and RPM                                        |

## Subscription parameters

`ReportInfoCfg` carries these fields alongside `sub`:

All time values are in **milliseconds**.

| Field              | Purpose                                                                                                                        |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| `act`              | `RPT_START` (0) to begin, `RPT_STOP` (1) to end.                                                                                |
| `timeout`          | Subscription keep-alive budget, ms.  See note below.                                                                            |
| `period`           | Interval between reports in ms.  Lower = faster (250 ms → 4 Hz).                                                                |
| `no_change_period` | Interval in ms when data hasn't changed — keeps a heartbeat alive without spamming identical payloads.                         |
| `count`            | Number of reports before auto-stop.  `1` = one-shot poll (default in `get_report_cfg`); `0` = continuous until `RPT_STOP` sent. |

### `timeout` — educated guess

This field isn't documented in the APK and the proto only names it `timeout`.
Based on how the app uses it (always ~10× `period`, set alongside every
`RPT_START`, and the fact that the app explicitly sends `RPT_STOP` on
backgrounding rather than relying on a timeout to terminate the stream), the
most likely interpretation is:

> **Watchdog on the subscription itself.**  The device auto-terminates the
> stream if no fresh `ReportInfoCfg` is received within `timeout` ms.  The app
> keeps a subscription alive by re-issuing the cfg before the window elapses.

That fits the observed `10000 ms` value: long enough to survive one or two
skipped report cycles, short enough for the device to notice an unresponsive
client within seconds.  A shorter `timeout` means a more eager dead-client
detection; a longer one keeps the stream alive across flaky links at the cost
of wasted reports when the client has actually gone away.

This is not firmware-confirmed — if you observe different behaviour with very
short or very long `timeout` values, update this doc.

## Observed APK usage

### Live map view — `requestConnectingChannels`
```
period=1000  no_change=4000  count=DeviceUtils.getCountKeep()
sub = [CONNECT, RTK, DEV_LOCAL, WORK, DEV_STA, VISION_POINT, VIO,
       VISION_STATISTIC, MAINTAIN, BASESTATION_INFO]
```

### Background IoT polling — `requestIOTMessage`
```
period=3000  no_change=4000  count=0
```

### pymammotion rapid-stream watcher (in `client.py`)
Triggered on `sys_status` transition to `MODE_WORKING` / `MODE_RETURNING`:
```
period=250  no_change=4000  count=0
sub = [CONNECT, WORK, DEV_LOCAL, DEV_STA, VISION_POINT]
```
`RIT_DEV_STA` is included so the watcher can still observe sys_status during
the stream and send `RPT_STOP` on transition out of the active states.

## Notes

- The ~4 Hz `system_tard_state_tunnel` frames seen during mowing are a
  **separate always-on channel** — not controlled by `ReportInfoCfg`.
- Channels populate only their own field; absent channels leave their
  corresponding `ReportInfoData` field empty / unchanged.
- The device doesn't deliver a one-time "initial snapshot" when you subscribe;
  it just starts emitting at the requested `period`.
