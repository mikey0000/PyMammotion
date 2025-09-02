# Technical Documentation: Multimedia Controls

This document provides a technical overview of the protobuf messages used to control the robot's multimedia functions, as defined in `luba_mul.proto`. These features include sophisticated audio controls, video stream management, and control over physical hardware like wipers and headlights. Most of these capabilities are not currently exposed in the high-level library API.

---

## 1. Audio Control

The robot's voice prompts can be customized by the client.

### Message: `MulSetAudio`

-   **Source:** `luba_mul.proto`
-   **Direction:** App/Client -> Robot
-   **Purpose:** To configure the robot's audio output. This message uses a `oneof` to set one property at a time.

#### Fields:

| Field Name    | Type           | Description                                                                                                                                                             |
| :------------ | :------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `at_switch`   | `int32`        | Toggles the audio prompts on or off (e.g., 0=Off, 1=On).                                                                                                                |
| `au_language` | `MUL_LANGUAGE` | **(Unimplemented)** Sets the language for the voice prompts. The `MUL_LANGUAGE` enum includes `ENGLISH`, `GERMAN`, `FRENCH`, `ITALIAN`, `SPANISH`, `PORTUGUESE`, `DUTCH`, and `SWEDISH`. |
| `sex`         | `MUL_SEX`      | **(Unimplemented)** Sets the gender of the voice. The `MUL_SEX` enum includes `MAN` and `WOMAN`.                                                                        |

#### Developer Capabilities Enabled:

-   **Internationalization & Personalization:** Exposing the language and voice gender selection would be a significant user-facing improvement, allowing users to tailor the robot's personality to their preference.

---

## 2. Video Control

These messages are used to manage the video stream from the robot's cameras. This is primarily relevant for models like the Yuka.

### Message: `MulSetVideo`

-   **Source:** `luba_mul.proto`
-   **Direction:** App/Client -> Robot
-   **Purpose:** To enable or disable a video stream from one or more cameras. This is likely one of the first commands sent after establishing a video streaming session via the HTTP API.

#### Fields:

| Field Name  | Type                  | Description                                                                                                                                                                                                    |
| :---------- | :-------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `position`  | `MUL_CAMERA_POSITION` | An enum specifying which camera to control. Values are `LEFT`, `RIGHT`, `REAR`, and `ALL`. This confirms that some models may have multiple cameras.                                                            |
| `vi_switch` | `int32`               | Toggles the video stream on or off (0=Off, 1=On).                                                                                                                                                              |

### Message: `MulSetEncode`

-   **Source:** `luba_mul.proto`
-   **Direction:** App/Client -> Robot
-   **Purpose:** To request the robot to begin encoding the video stream.

#### Fields:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `encode` | `bool` | `true` to start encoding, `false` to stop. |

---

## 3. Hardware Controls (Wipers & Headlights)

The protocol supports direct control over other physical hardware components.

### Message: `MulSetWiper`

-   **Source:** `luba_mul.proto`
-   **Direction:** App/Client -> Robot
-   **Purpose:** To control the camera lens wiper, likely on Yuka or other camera-equipped models.

#### Fields:

| Field Name | Type    | Description                               |
| :--------- | :------ | :---------------------------------------- |
| `round`    | `int32` | The number of wipe cycles to perform.     |

### Message: `SetHeadlamp`

-   **Source:** `luba_mul.proto`
-   **Direction:** App/Client -> Robot
-   **Purpose:** To control the robot's headlights.

#### Fields:

| Field Name           | Type                   | Description                                                                                                 |
| :------------------- | :--------------------- | :---------------------------------------------------------------------------------------------------------- |
| `set_ids`            | `int32`                | Likely an ID for which lamp to control if there are multiple.                                               |
| `lamp_power_ctrl`    | `int32`                | A general power control.                                                                                    |
| `lamp_ctrl`          | `lamp_ctrl_sta`        | An enum to set the lamp state (`power_off`, `power_on`, `power_ctrl_on`).                                   |
| `ctrl_lamp_bright`   | `bool`                 | A flag to indicate whether the brightness value should be applied.                                          |
| `lamp_bright`        | `int32`                | The brightness level of the lamp, likely a percentage (0-100).                                              |
| `lamp_manual_ctrl`   | `lamp_manual_ctrl_sta` | An enum to set a manual override state (`manual_power_off`, `manual_power_on`).                             |

#### Developer Capabilities Enabled:

-   **Model-Specific Features:** Implementing these controls would allow developers to expose all the hardware features of the premium models.
-   **Automation:** A client application could automatically turn on the headlights in low-light conditions (detected via the `brightness` field in the `vio_to_app_info_msg`) or trigger the wiper if the vision system performance degrades.
