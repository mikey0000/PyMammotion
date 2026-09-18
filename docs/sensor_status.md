# sensor_status Bit-Field Reference

`DeviceData.sensor_status` is an `int32` field from the `rpt_dev_status` protobuf
message (proto index 4).  The firmware packs several independent 3-bit sensor
states into a single integer using bitwise fields.

Source: `MACarDataManager.java` in Mammotion APK 2.2.4.13 —
`setUlt_Status()`, `setBumperState()`, and the "刀盘逻辑" knife-state extraction;
`SelfCheckFragment.java` `setCheckState()` for the 3-state display mapping.

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
 24 – 63       40    (reserved)               —
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

## Python accessors (`DeviceData`)

`DeviceData` exposes read-only properties that decode each field directly:

```python
device.report_data.dev.bumper_state      # SensorCheckState
device.report_data.dev.blade_state       # BladeState
device.report_data.dev.ult_left          # SensorCheckState  (bits 12-14)
device.report_data.dev.ult_left_front    # SensorCheckState  (bits 15-17)
device.report_data.dev.ult_right_front   # SensorCheckState  (bits 18-20)
device.report_data.dev.ult_right         # SensorCheckState  (bits 21-23)
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
