
# Mammotion Mower CLI Control - User Guide

**Version:** 1.1
**Date:** May 25, 2025

This guide explains how to use the Python-based command-line interface (CLI) to control and monitor your Mammotion Luba (and potentially Yuka) mower. This CLI is designed to work with the `PyMammotion` library.

## Table of Contents

1.  [Introduction](#1-introduction)
2.  [Prerequisites](#2-prerequisites)
3.  [Setup](#3-setup)
4.  [Running the Script](#4-running-the-script)
5.  [Initial Connection](#5-initial-connection)
6.  [Available Commands](#6-available-commands)
    *   [`connect`](#connect)
    *   [`status`](#status)
    *   [`raw_status`](#raw_status)
    *   [`maps` / `plans`](#maps--plans)
    *   [`sync_maps`](#sync_maps)
    *   [`mow_areas <area_hash1>,<area_hash2>,... [setting=value ...]`](#mow_areas-area_hash1area_hash2-settingvalue-)
    *   [`start <plan_id_or_name>`](#start-plan_id_or_name)
    *   [`dock` / `charge`](#dock--charge)
    *   [`undock` / `leave_dock`](#undock--leave_dock)
    *   [`pause`](#pause)
    *   [`resume`](#resume)
    *   [`stop` / `cancel`](#stop--cancel)
    *   [`blade_height <mm>`](#blade_height-mm)
    *   [`rawcmd <command_name> [json_parameters | key=value ...]`](#rawcmd-command_name-json_parameters--keyvalue-)
    *   [`help`](#help)
    *   [`exit`](#exit)
7.  [Understanding Status and Output](#7-understanding-status-and-output)
8.  [Troubleshooting](#8-troubleshooting)
9.  [Advanced Notes](#9-advanced-notes)
    *   [Device-Specific Behavior](#device-specific-behavior)
    *   [Enum Value Parsing](#enum-value-parsing)
10. [Examples](#10-examples)

## 1. Introduction

This CLI provides a powerful way to interact with your Mammotion mower directly from your terminal. It allows for automation, detailed status monitoring, and execution of various mowing commands without needing the official mobile application for every interaction.
It could also serve as the basis for further experimentation or integration with Telegram, OpenHAB ...

## 2. Prerequisites

Before you begin, ensure you have the following:

*   **Python:** Version 3.10 or newer installed. You can check your version with `python --version` or `python3 --version`.
*   **PyMammotion Library:** This script relies on the `PyMammotion` library. Install it using pip:
    ```bash
    pip install pymammotion
    ```
    Alternatively, if you need a specific version or the latest development build, you can install it directly from its [GitHub repository](https://github.com/mikey0000/PyMammotion) (refer to `PyMammotion` documentation for specific instructions).
*   **Mammotion Account:** You will need your Mammotion app login credentials (email and password).

## 3. Setup

Follow these steps to get the CLI ready:

1.  **Save the Script:**
    Save the provided Python code as a `.py` file (e.g., `mammotion-cli.py`) on your computer.

2.  **Credentials (Recommended: Environment Variables):**
    For security and convenience, it's best to set your Mammotion email and password as environment variables.

    *   **Linux/macOS:**
        ```bash
        export EMAIL="your_mammotion_email@example.com"
        export PASSWORD="your_mammotion_password"
        ```
        (Add these to your shell's profile file like `.bashrc` or `.zshrc` for persistence).
    *   **Windows (Command Prompt):**
        ```cmd
        set EMAIL="your_mammotion_email@example.com"
        set PASSWORD="your_mammotion_password"
        ```
        (For persistence, use the System Properties > Environment Variables dialog).
    *   **Windows (PowerShell):**
        ```powershell
        $env:EMAIL="your_mammotion_email@example.com"
        $env:PASSWORD="your_mammotion_password"
        ```
        (Add to your PowerShell profile for persistence).

    If these environment variables are not set, the script will prompt you to enter them securely when it starts.

3.  **Log Level (Optional):**
    Control the script's logging verbosity by setting the `LOG_LEVEL` environment variable.
    *   Options: `DEBUG`, `INFO` (default), `WARNING`, `ERROR`.
    *   Example (Linux/macOS):
        ```bash
        export LOG_LEVEL="DEBUG" # For more detailed output
        ```
    The script also sets more restrictive log levels for verbose third-party libraries like `paho.mqtt.client` by default.

## 4. Running the Script

1.  Open your terminal or command prompt.
2.  Navigate to the directory where you saved `mammotion-cli.py`.
3.  Execute the script:
    ```bash
    python mammotion-cli.py
    ```
    (Or `python3 mammotion-cli.py` depending on your system's Python setup).

## 5. Initial Connection

*   On the first run (or if credentials are not set via environment variables), you'll be prompted for your Mammotion email and password.
*   The script will then attempt to:
    1.  Log in to the Mammotion cloud.
    2.  Set up the cloud gateway.
    3.  List your bound devices. If multiple Luba devices are found, you will be prompted to select one. Otherwise, the first Luba found will be used.
    4.  Initialize an MQTT connection for real-time updates.
    5.  Send initial commands to gather device status (`get_report_cfg`).
    6.  Attempt to populate the list of saved mowing plans/tasks (`attempt_to_populate_maps`).
    7.  Request continuous status reporting from the mower (`request_iot_sys`).
    8.  Start a background task (`periodic_status_monitor`) for periodic status polling and display.

*   If successful, you'll see log messages indicating these steps and finally the command prompt:
    ```
    INFO - CLI Ready. Mower: Luba-XXXXXX
    MowerControl>
    ```
*   The background status monitor will poll for status updates at intervals defined in the script (e.g., every 20 seconds, or more frequently if the mower is actively working or data is stale).

## 6. Available Commands

Type commands at the `MowerControl>` prompt and press Enter. Command names are case-insensitive.

---

### `connect`
Manually initiates or re-initiates the connection sequence to the mower. This will disconnect any existing session and attempt a fresh connection. Useful if the initial connection fails or if the connection drops. This is is somewhat untested, restart the script if this fails.

**Usage:**
```
MowerControl> connect
```

---

### `status`
Displays a summary of the current mower status. The script attempts to refresh data if it appears stale.
*   Includes: Device Name, Nickname, Serial Number, Battery, Activity (e.g., `Charging`, `Mowing`, `Docked`), Error Code, Docked & Charging status, Connection Info, RTK Status (Stars, L1/L2), Mowing Progress, Task Details, Blade Height, Position (Certainty, Lat/Lon), Current Area Name.

**Usage:**
```
MowerControl> status
```

---

### `raw_status`
Dumps the entire raw `MowingDevice` state object (from `PyMammotion`) as JSON. Useful for debugging and understanding the full data structure available. The script attempts to refresh data if it appears stale.

**Usage:**
```
MowerControl> raw_status
```

---

### `maps` (or `plans`)
Displays saved mowing plans and defined mowing areas in a tabular format.

*   **Tasks/Plans:** Lists saved mowing plans with their Name, ID, schedule details (Days, Start Time), Height, and Speed. Data is sourced from `mower.map.plan`. Upcoming tasks are at the top and all tasks, enabled or disabled, are shown alike.
*   **Areas:** Lists defined mowing areas with their Name, an assigned Number, and Hash. Data is sourced from `mower.map.area_name`. Area hashes are needed for the `mow_areas` command.

**Usage:**
```
MowerControl> maps
```
or
```
MowerControl> plans
```
> **Note:** If the list is incomplete or empty, use `sync_maps`.

---

### `sync_maps`
Attempts to refresh the list of areas and plans from the mower.
It clears the local cache and sends commands (`get_area_name_list`, `read_plan`) to request this data.

**Usage:**
```
MowerControl> sync_maps
```

---

### `mow_areas <area_hash1>,<area_hash2>,... [setting=value ...]`
Starts mowing one or more specified areas with custom operational settings.

*   `<area_hash1>,<area_hash2>,...`: Comma-separated list of area hashes (get these from the `maps` command).
*   `[setting=value ...]`: Optional space-separated settings to override defaults.
    **Type `mow_areas` without arguments to see a detailed list of available settings, their current defaults in the script, and their expected values/formats** (e.g., `speed=0.6`, `mowing_laps=lap_2` or `mowing_laps=2`, `job_mode=grid_first` or `job_mode=1`).
    The script attempts to parse enum values case-insensitively by name or by their integer index.

**Usage Examples:**
```
MowerControl> mow_areas <hash_for_area1>
MowerControl> mow_areas <hash_area1>,<hash_area2> speed=0.5 mowing_laps=1
MowerControl> mow_areas <hash_area3> job_mode=GRID_FIRST toward_mode=ABSOLUTE_ANGLE toward=45
```
The script generates `OperationSettings` and `GenerateRouteInformation`, then sends `generate_route_information` followed by `start_job`. Device-specific logic (e.g., for Luba 1 or Yuka) may apply.

Defaults are defined in the handle_mow_areas_command function of the script, look for OperationSettings(). Incorrect arguments are generally ignored here, however for parameters with known options these will be printed. Final parameters passed to the mover will be displayed  using pprint(op_settings.__dict__) - for experimentation you can uncomment the return just after pprint to prevent the mower from starting.

---

### `start <plan_id_or_name>`
Starts a pre-saved mowing plan/task using its ID or its exact Name (case-sensitive for name matching from `maps` output).

*   `<plan_id_or_name>`: The ID (numeric string) or the Name of the plan as shown in the `maps` command output. If the name contains spaces, enclose it in quotes.

**Usage Examples:**
```
MowerControl> start 174670239929556252383
MowerControl> start "My Front Yard Plan"
MowerControl> start Zqxwlc
```
This command uses the `single_schedule` mower command.

---

### `dock` (or `charge`)
Sends the `return_to_dock` command to the mower.

**Usage:**
```
MowerControl> dock
```
or
```
MowerControl> charge
```

---

### `undock` (or `leave_dock`)
Sends the `leave_dock` command. The mower will leave the dock and wait for further instructions.

**Usage:**
```
MowerControl> undock
```
or
```
MowerControl> leave_dock
```

---

### `pause`
Sends the `pause_execute_task` command to pause the current operation.

**Usage:**
```
MowerControl> pause
```

---

### `resume`
Sends the `resume_execute_task` command to resume a paused operation.

**Usage:**
```
MowerControl> resume
```

---

### `stop` (or `cancel`)
Sends the `cancel_job` command to stop the current operation. The mower will typically stop and idle.

**Usage:**
```
MowerControl> stop
```
or
```
MowerControl> cancel
```

---

### `blade_height <mm>`
Sets the blade cutting height in millimeters using the `set_blade_height` command.

**Usage Example:**
```
MowerControl> blade_height 60
```
(Sets blade height to 60mm)

---

### `rawcmd <command_name> [json_parameters | key=value ...]`
Sends a raw command directly to the mower. This is useful for testing or advanced control.

*   `command_name`: The string name of the command as defined in `PyMammotion`'s `MammotionCommand` class (e.g., `get_device_info`).
*   `json_parameters`: Optional. If the command takes parameters, provide them as a valid single JSON string (e.g., `'{"shine_mode":1, "custom_time":{"start_hour":20}}'`).
*   `key=value ...`: Alternatively, provide parameters as space-separated `key=value` pairs. The script will attempt to convert values to `int`, `float`, `bool`, or `None` where appropriate, otherwise they remain strings.

**Usage Examples:**
```
MowerControl> rawcmd get_report_cfg
MowerControl> rawcmd set_led_shine '{"shine_mode":1, "custom_time":{"start_hour":20, "start_min":0, "end_hour":6, "end_min":0}}'
MowerControl> rawcmd allpowerfull_rw rw_id=5 rw=1 context=1
```
> **Note:** The exact parameters and their structure depend on the specific command. Refer to `PyMammotion` documentation or source code. Type `rawcmd` alone for examples.

---

### `help`
Displays a summary of available commands and their syntax.

**Usage:**
```
MowerControl> help
```

---

### `exit`
Disconnects from the mower, stops continuous reporting and background tasks, and closes the application gracefully.

**Usage:**
```
MowerControl> exit
```

---

## 7. Understanding Status and Output

*   **Log Messages:** The script logs its actions, status updates, and any errors to the console. The default level is `INFO`. Set `LOG_LEVEL="DEBUG"` (see [Setup](#3-setup)) for more verbose output. The script attempts to handle known benign errors (like certain `JSONDecodeError`s from background MQTT tasks) gracefully.
*   **Periodic Status:** The `STATUS:` line that appears periodically shows a snapshot of the mower's state, including activity, battery, RTK, progress, and current area. This is driven by the `periodic_status_monitor`.
*   **Notifications:** The script includes simple logic to log a "NOTIFICATION" if a task that was previously working at high progress changes to an idle/completed state, suggesting task completion.

## 8. Troubleshooting

*   **Connection Issues:**
    *   Double-check email/password (case-sensitive).
    *   Ensure your Luba mower is online and has a stable internet connection (WiFi).
    *   Check for firewall issues on your computer or network.
    *   Use the `connect` command to re-attempt connection or restart the script.
*   **Commands Not Working:**
    *   Ensure the mower is in an appropriate state for the command.
    *   Allow a few seconds for commands to be processed and status to update.
    *   Use `raw_status` to inspect the mower's complete state.
    *   Use `status` to check the mower's current activity.
*   **Incomplete Plan List (`maps` command):**
    *   Run `sync_maps`. Wait 10-15 seconds. Then run `maps` again.
*   **`AttributeError` or Command Not Found:**
    This usually means the command name used does not map to a known function in the `PyMammotion` library as expected by the script. Check for typos.

## 9. Advanced Notes

### Device-Specific Behavior

*   **`mow_areas` Command:**
    *   **Yuka:** If a Yuka device is detected, the `blade_height` for the custom job will automatically be set to `-10` as required.
    *   **Luba 1:** Specific adjustments may be made to `GenerateRouteInformation` parameters (e.g., `toward_mode`, `toward_included_angle` set to 0). After starting a job, an additional `set_blade_control(on_off=1)` command is sent to help ensure blades engage.
NOTE: Only the Luba mini has been tested

### Enum Value Parsing

*   For commands like `mow_areas` that take settings corresponding to `PyMammotion` enums (e.g., `job_mode`, `mowing_laps`), the script attempts to parse your input value:
    1.  Case-insensitively by the enum member's name (e.g., `GRID_FIRST`).
    2.  By the integer index of the enum member (e.g., `1` for `GRID_FIRST` if it's the second item in the enum).
    *   Refer to the `mow_areas` help text (by typing `mow_areas` alone) for guidance on valid names/indices.

## 10. Examples

Output from the `maps` command (example structure):

```
MowerControl> maps

--- Tasks/Plans (from mower.map.plan) ---

PlanId                | Days                      | Start Time | Name                 | Height | Speed
---------------------------------------------------------------------------------------------------------
890123456789012345671 | Tue                       | 09:30      | Zqxwlc               | 65     | 0.4
234567890123456789012 | Tue, Fri                  | 10:20      | Bmndfv               | 65     | 0.4

--- Mapped Areas (from mower.map.area_name) ---

No.   | Area Name                    | Hash
-----------------------------------------------------------------
1     | Yvrbql                       | 9012456789012345678
2     | Fzldhv                       | 8765321098765432101
```

**Example Actions:**

1.  **Start the plan 'Zqxwlc' using its Name:**
    ```
    MowerControl> start Zqxwlc
    ```
2.  **Start a plan using its PlanId:**
    ```
    MowerControl> start 890123456789012345671
    ```
3.  **Mow Area with hash `9012456789012345678` at 45 degrees, no perimeter cuts, custom speed:**
    (Check `mow_areas` help for exact enum names for `mowing_laps` and `toward_mode`)
    ```
    MowerControl> mow_areas 9012456789012345678 mowing_laps=NONE toward_mode=ABSOLUTE_ANGLE toward=45 speed=0.5
    ```
    (Note: `mowing_laps=NONE` or its equivalent integer index, `toward_mode=ABSOLUTE_ANGLE` or its index)

