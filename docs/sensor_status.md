# sensor_status Bit-Field Reference

`DeviceData.sensor_status` is an `int32` field from the `rpt_dev_status` protobuf
message (proto index 4).  The firmware packs several independent 3-bit sensor
states into a single integer using bitwise fields.

Source: `MACarDataManager.java` in Mammotion APK 2.2.4.13 —
`setUlt_Status()`, `setBumperState()`, and the "刀盘逻辑" knife-state extraction;
`SelfCheckFragment.java` `setCheckState()` for the 3-state display mapping, and
`MapManualActivityNew.java` `lambda$initCarWorkState$7` for the grass-collector
and bin-tipping fields.

---

## Bit layout

```
Bit position  Width  Field                   Sensor ID (app-internal)
-----------   -----  ---------------------   ------------------------
  0 –  2        3    Bumper / collision bar   —
  3 –  8        6    (reserved)               —
  9 – 11        3    Blade / cutter disc      —
 12 – 14        3    Left ultrasonic          110
 15 – 17        3    Left-front ultrasonic    111
 18 – 20        3    Right-front ultrasonic   112
 21 – 23        3    Right ultrasonic         113
 24 – 26        3    Grass collector (sweep)  —
 27 – 29        3    Bin tipping (dump)       —
 30 – 63       34    (reserved)               —
```

---

## 3-bit sensor state values (`SensorCheckState`)

Each 3-bit slot uses the same `SensorCheckState` encoding.
The app's self-check screen (`SelfCheckFragment.setCheckState`) maps these to
three visual states:

| Value | `SensorCheckState` | Self-check display    |
|------:|--------------------|-----------------------|
|     0 | `OK`               | Green ✓ — healthy     |
|     1 | `WARNING`          | Yellow ⚠ — degraded   |
| 2 – 7 | `ERROR`            | Red ✗ — fault/blocked |

Values 3–7 all render as `ERROR`; the Python properties clamp them to 2.

---

## Blade state values (`BladeState`) — bits 9–11

The blade field uses a separate `BladeState` enum and is also broadcast as a
`KnifeStateEvent` on the internal RxBus.

| Value | `BladeState` | Meaning               |
|------:|--------------|-----------------------|
|     0 | `OFF`        | Blade not rotating    |
|     1 | `ON`         | Blade active/rotating |
| 2 – 7 | `ON`         | (non-zero → ON)       |

Log tag in firmware: `"刀盘逻辑=====================是否开刀===3:"` (cutter-disc
logic: is blade open?)

---

## Grass-collector state values (`CollectorState`) — bits 24–26

The app's `colloctState`.  It stops collection and shows the upload-failed warning
for anything above `COLLECTING`, so the accessor clamps 3–7 to `FAULT`.

| Value | `CollectorState` | Meaning                                |
|------:|------------------|----------------------------------------|
|     0 | `IDLE`           | Collector not running                  |
|     1 | `COLLECTING`     | Sweeping clippings into the bin        |
| 2 – 7 | `FAULT`          | Collection failed (3–7 clamp to 2)     |

---

## Bin-tipping state values (`DumpState`) — bits 27–29

The app's `pourState`.  Unlike the fields above, values the library does not model
(4–7) resolve to `UNKNOWN` (−1) rather than clamping, and are logged once per value.

| Value | `DumpState`  | Meaning                                                   |
|------:|--------------|-----------------------------------------------------------|
|     0 | `LOWERED`    | Bin stowed                                                |
|     1 | `RAISED`     | Bin lifted and ready to tip                               |
|     2 | `ADJUSTING`  | Collect-mode adjustment running; must be turned off first |
|     3 | `POURING`    | Clippings being tipped out                                |
| 4 – 7 | `UNKNOWN`    | Not modelled                                              |

Whether a collector is fitted is **not** in `sensor_status`: it is
`collector_status.collector_installation_status` (non-zero = fitted), exposed as
`collector_installed`.  The app hides every sweep and dump control while it is zero.

---

## Python accessors (`DeviceData`)

`DeviceData` exposes read-only properties that decode each field directly:

```python
device.report_data.dev.bumper_state      # SensorCheckState
device.report_data.dev.blade_state       # BladeState
device.report_data.dev.ult_left          # SensorCheckState  (bits 12-14)
device.report_data.dev.ult_left_front    # SensorCheckState  (bits 15-17)
device.report_data.dev.ult_right_front   # SensorCheckState  (bits 18-20)
device.report_data.dev.ult_right         # SensorCheckState  (bits 21-23)
device.report_data.dev.collector_state   # CollectorState    (bits 24-26)
device.report_data.dev.dump_state        # DumpState         (bits 27-29)
device.report_data.dev.collector_installed  # bool, from collector_status (not a sensor_status bit)
```

Raw integer access is always available via `device.report_data.dev.sensor_status`.

---

## Extraction example

```python
from pymammotion.data.model.enums import BladeState, SensorCheckState

raw = device.report_data.dev.sensor_status

bumper    = SensorCheckState(min(raw & 0x7, 2))
blade     = BladeState.ON if (raw >> 9) & 0x7 else BladeState.OFF
ult_left  = SensorCheckState(min((raw >> 12) & 0x7, 2))
```
