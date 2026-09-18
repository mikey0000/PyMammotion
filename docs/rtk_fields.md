# RTK Field Reference

The device pushes RTK data inside `toapp_report_data` → `ReportInfoData.rtk` (`rpt_rtk` proto
message).  No explicit request is needed beyond subscribing to `RIT_RTK` in `get_report_cfg()`.
The Python model is `RTKData` in `pymammotion/data/model/report_info.py`.

---

## How RTK data is delivered

RTK status is **pushed (unsolicited)** as part of the periodic `toapp_report_data` message.
The app subscribes by calling `get_report_cfg()` which includes `RptInfoType.RIT_RTK` in the
subscription list.  The device then streams `rpt_rtk` snapshots automatically.

To change the correction source, the app sends `app_to_dev_set_mqtt_rtk_t` (proto field 45):

```
MctlSys {
    app_to_dev_set_mqtt_rtk_msg = AppToDevSetMqttRtkT {
        set_rtk_mode = <RtkUsedType>   # 0=LoRa, 1=Internet/NTRIP, 2=NRTK
    }
}
```

Python equivalent: `system.set_net_rtk_link_mode(mode)` in
`pymammotion/mammotion/commands/messages/system.py`.

---

## `rpt_rtk` field reference

| Proto field | Python name | Type | Description |
|---|---|---|---|
| `status` | `status` | int32 | RTK fix status — see `RTKStatus` enum |
| `pos_level` | `pos_level` | int32 | Positioning solution level — see `PositionMode` enum |
| `gps_stars` | `gps_stars` | int32 | Total tracked satellite count (all constellations) |
| `age` | `age` | int32 | Age of differential correction (seconds) |
| `lat_std` | `lat_std` | int32 | Latitude accuracy standard deviation (scaled int) |
| `lon_std` | `lon_std` | int32 | Longitude accuracy standard deviation (scaled int) |
| `l2_stars` | `l2_stars` | int32 | L2 dual-frequency satellite count |
| `dis_status` | `dis_status` | int64 | Packed signal quality — see `get_dis_status()` |
| `top4_total_mean` | `top4_total_mean` | int64 | Mean CNR of best 4 satellites |
| `co_view_stars` | `co_view_stars` | int32 | Packed co-view satellite counts (L1 + L2) |
| `reset` | `reset` | int32 | RTK reset count since boot |
| `lora_info` | `lora_info` | `LoraInfo` | LoRa base-station pairing state |
| `mqtt_rtk_info` | `mqtt_rtk_info` | `MqttRtkInfo` | Correction channel config |
| `score_info` | `score_info` | `RtkPositionScore` | Positioning quality scores |

---

## `status` — RTK fix status (`RTKStatus` enum, `pymammotion/data/model/enums.py`)

| Value | Enum | Meaning |
|------:|------|---------|
| 0 | `NONE` | No GNSS fix |
| 1 | `SINGLE` | Single-point positioning (SPP) |
| 2 | `SINGLE` | Also treated as single |
| 4 | `FIX` | RTK fixed solution (best) |
| 5 | `FLOAT` | RTK float solution |
| other | `UNKNOWN` | Unrecognised |

Source: `MACarDataManager.java` rapid-state `raw[0]` extraction +
`RTKStatusFragment.java` display logic.

---

## `pos_level` — positioning solution level (`PositionMode` enum)

| Value | Enum | Meaning |
|------:|------|---------|
| 0 | `FIX` | Best — RTK fixed |
| 1 | `SINGLE` | Single-point |
| 2 | `FLOAT` | RTK float |
| 3 | `NONE` | No solution |
| 4+ | `UNKNOWN` | Unrecognised |

Lower value = better fix quality.
Source: `MACarDataManager.java` `posLevel = rtk.getPosLevel()`.

---

## `co_view_stars` — co-view satellite counts (packed int32)

Both counts are packed into one integer using the same scheme used for `rapid_state raw[15]`:

| Bits | Field | Accessor |
|------|-------|---------|
| 0–7  | L1 co-view satellite count | `co_view_stars & 0xFF` |
| 8–15 | L2 co-view satellite count | `(co_view_stars >> 8) & 0xFF` |

Source: `MACarDataManager.java` lines 10548–10555 (`coViewStars` extraction).

---

## `dis_status` — packed signal quality (int64)

Decoded by `RTKData.get_dis_status()` which returns an `RTKDisStatus` dataclass.

| Bits | `RTKDisStatus` field | Default (when 0) | Meaning |
|------|--------------------|------------------|---------|
| 8–15 | `pos_status` | 3 | Position status indicator |
| 16–23 | `l1` | 0 | L1 signal quality |
| 24–31 | `l2` | 0 | L2 signal quality |
| 32–39 | `device_signal` | 3 | Rover (device) signal quality |
| 40–47 | `rtk_signal` | 3 | RTK correction signal quality |
| 48–55 | `connection_to_ref` | 3 | Connection-to-reference-station quality |
| 56–63 | `precision` | 3 | Positioning precision indicator |

All fields are raw 8-bit values (0–255).  The default of 3 when `dis_status == 0`
suggests these are on an internal quality scale, not raw CNR in dB-Hz.

Source: `MACarDataManager.java` lines 10505–10531.

---

## `mqtt_rtk_info.rtk_switch` — correction source / positioning mode (`RtkSwitchMode` enum)

This is what the Mammotion app labels **"Positioning Mode"** (`tvPositionModeValue` in
`RTKStatusFragment.java`).

| Value | Enum | APK display label |
|------:|------|-------------------|
| 0 | `LORA` | Antenna Over Datalink |
| 1 | `INTERNET` | Antenna Over Internet |
| 2 | `NRTK` | Network RTK |

---

## Python accessors

```python
rtk = device.report_data.rtk

# Fix status
status: RTKStatus = RTKStatus.from_value(rtk.status)

# Positioning level
mode: PositionMode = rtk.positioning_mode      # property on RTKData

# Satellite counts
total_sats: int = rtk.gps_stars
l2_sats: int = rtk.l2_stars
co_view_l1: int = rtk.co_view_stars & 0xFF
co_view_l2: int = (rtk.co_view_stars >> 8) & 0xFF

# Correction age
age_secs: int = rtk.age

# Signal quality
dis = rtk.get_dis_status()
dis.device_signal       # rover signal quality
dis.rtk_signal          # RTK correction signal quality
dis.connection_to_ref   # reference station connection quality
dis.l1                  # L1 signal quality
dis.l2                  # L2 signal quality

# Correction source
source: RtkSwitchMode = rtk.mqtt_rtk_info.switch_mode
```
