# Mammotion Mower CLI Control - User Guide

**Version:** 1.2
**Date:** May 28, 2025

This guide explains how to use the Python-based command-line interface (CLI) to control and monitor your Mammotion Luba (and potentially Yuka) mower. This CLI is designed to work with the `PyMammotion` library.
NOTE: Only the Luba mini has been tested, using Linux.

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
    *   [`mow_areas`](#mow_areas)
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
    *   [Enum Value Parsing for `mow_areas`](#enum-value-parsing-for-mow_areas)
    *   [Configuration Files](#configuration-files)
10. [Examples](#10-examples)

## 1. Introduction

This CLI provides a powerful way to interact with your Mammotion mower directly from your terminal. It allows for automation, detailed status monitoring, and execution of various mowing commands without needing the official mobile application for every interaction. It could also serve as the basis for further experimentation or integration with other systems.

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
    The script also sets more restrictive log levels for verbose third-party libraries by default (e.g., `pymammotion` logs at `WARNING` unless CLI log level is `DEBUG`, `paho.mqtt.client` at `WARNING`).

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
    3.  List your bound devices. If multiple Luba or Yuka devices are found, you will be prompted to select one. Otherwise, the first compatible device found will be used.
    4.  Initialize an MQTT connection for real-time updates.
    5.  Send initial commands to gather device status (e.g., `get_report_cfg`).
    6.  Attempt to populate the list of saved mowing plans/tasks and map data from cache or by fetching if cache is empty/invalid.
    7.  Request continuous status reporting from the mower (`request_iot_sys`).
    8.  Start a background task (`periodic_status_monitor`) for periodic status display and polling (if needed).

*   If successful, you'll see log messages indicating these steps and finally the command prompt:
    ```
    INFO - CLI Ready. Mower: Luba-XXXXXX (or Yuka-XXXXXX)
    MowerControl>
    ```
*   The background status monitor will print a summary status at intervals (default: 20 seconds, or more frequently if the mower is actively working, undocked, or data seems stale).

## 6. Available Commands

Type commands at the `MowerControl>` prompt and press Enter. Command names are case-insensitive.

---

### `connect`
Manually initiates or re-initiates the connection sequence to the mower. This will disconnect any existing session and attempt a fresh connection, including re-selection of the device if multiple are available. Useful if the initial connection fails or if the connection drops. This command attempts to gracefully shut down the old connection before establishing a new one.

**Usage:**
```
MowerControl> connect
```

---

### `status`
Displays a detailed, formatted summary of the current mower status. The script attempts to refresh data from the mower if it appears stale (older than 5 seconds) or is missing a timestamp.
*   Includes: Device Name, Nickname, Serial Number, Battery details (percent, charging status, docked status, charge rate, estimated time to 80%/100%), Activity (e.g., `Charging`, `Mowing`, `Docked`), Error Code, Connection Info (type, RSSI), RTK Status (type, Stars, L1/L2 satellites), Mowing Progress (percent, remaining time), Task Details (total/elapsed time, area), Blade Height, Mowing Speed, Position (certainty, lat/lon), Current Area Name, and Timestamps.

**Usage:**
```
MowerControl> status
```

---

### `raw_status`
Dumps the entire raw `MowingDevice` state object (from `PyMammotion`) as a JSON string. This is useful for debugging and understanding the full data structure available from the mower. The script attempts to refresh data from the mower if it appears stale or is missing a timestamp.

**Usage:**
```
MowerControl> raw_status
```

---

### `maps` (or `plans`)
Displays saved mowing plans (tasks) and defined mowing areas in a tabular format. Data is sourced from the local cache (`mower.map.plan` and `mower.map.area_name`).

*   **Tasks/Plans:** Lists saved mowing plans with their Plan ID, scheduled Days, Start Time, Name, Blade Height, and Speed.
*   **Mapped Areas:** Lists defined mowing areas with an Index Number, Area Name, and its unique Hash. Area hashes are needed for the `mow_areas` command.

**Usage:**
```
MowerControl> maps
```
or
```
MowerControl> plans
```
> **Note:** If the list is incomplete or empty, use `sync_maps` to refresh from the mower and update the cache.

---

### `sync_maps`
Attempts to refresh the list of areas and plans from the mower and updates the local cache file (`map_cache.json`). It clears the current in-memory map data and sends commands (`get_area_name_list`, `read_plan`) to request this data. Allow 10-15 seconds for data to populate after issuing the command.

**Usage:**
```
MowerControl> sync_maps
```

---

### `mow_areas`
This command has multiple forms:
1.  **`mow_areas show`** (or `mow_areas` with no arguments):
    Displays the current default mowing settings stored in `mow_defaults.json`, lists available settings with examples (including valid Enum member names), and shows usage instructions.

2.  **`mow_areas set <setting1>=<value1> [<setting2>=<value2> ...]`**:
    Sets and saves new default mowing parameters to `mow_defaults.json`.
    *   `<settingX>=<valueX>`: Space-separated key-value pairs. For Enum settings, use their string names (case-insensitive, e.g., `job_mode=GRID_FIRST`). Numeric values are parsed as integers or floats.
    *   Example: `mow_areas set speed=0.5 job_mode=GRID_FIRST blade_height=55`

3.  **`mow_areas <area_hash1>[,<area_hash2>,...] [setting1=value1 ...]`**:
    Starts mowing one or more specified areas with custom operational settings that override the defaults for this specific job.
    *   `<area_hash1>[,<area_hash2>,...]`: Comma-separated list of area hashes (get these from the `maps` command).
    *   `[settingX=valueX ...]`: Optional space-separated settings to override defaults for this job. Use Enum member names for enum settings.
    *   The script applies defaults from `mow_defaults.json`, then applies any CLI overrides. It generates `OperationSettings` and `GenerateRouteInformation`, then sends `generate_route_information` followed by `start_job`. Device-specific logic (e.g., for Luba 1 or Yuka) may apply to parameters.

**Usage Examples (for starting a mow):**
```
MowerControl> mow_areas <hash_for_area1>
MowerControl> mow_areas <hash_area1>,<hash_area2> speed=0.5 mowing_laps=ONE
MowerControl> mow_areas <hash_area3> job_mode=GRID_FIRST toward_mode=ABSOLUTE_ANGLE toward=45
```

---

### `start <plan_id_or_name>`
Starts a pre-saved mowing plan/task using its ID or its exact Name.
*   `<plan_id_or_name>`: The ID (numeric string) or the Name of the plan as shown in the `maps` command output. If the name contains spaces, it's best if the script doesn't require quotes, but check behavior (the script joins `args` with spaces). The script attempts to match the provided reference first as an ID, then as a name from the cached plan data.

**Usage Examples:**
```
MowerControl> start 174670239929556252383
MowerControl> start My Front Yard Plan
MowerControl> start Zqxwlc_PlanName
```
This command uses the `single_schedule` mower command with the resolved plan ID.

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
> **Note:** The exact parameters and their structure depend on the specific command. Refer to `PyMammotion` documentation or source code, or use the `help` command for some common examples.

---

### `help`
Displays a summary of available commands and their syntax.

**Usage:**
```
MowerControl> help
```

---

### `exit`
Disconnects from the mower, stops continuous reporting and background tasks, saves map cache, and closes the application gracefully.

**Usage:**
```
MowerControl> exit
```

---

## 7. Understanding Status and Output

*   **Log Messages:** The script logs its actions, status updates, and any errors to the console. The default level is `INFO`. Set `LOG_LEVEL="DEBUG"` (see [Setup](#3-setup)) for more verbose output. The script attempts to handle known benign errors (like certain `JSONDecodeError`s from background MQTT tasks) gracefully by logging them at a `DEBUG` level.
*   **Periodic Status Summary:** A summarized status line (formatted by `StatusFormatter.format_summary_text`) appears periodically. It shows a snapshot of the mower's state, including Device Name & Update Age, Activity & Error, Battery & Charging, RTK & Position, Current Area, and Work Progress/Values if applicable. This is driven by the `periodic_status_monitor`.
*   **Detailed Status (`status` command):** Provides a more comprehensive, multi-line formatted output of the mower's current state.
*   **Notifications:** The script includes simple logic to log an "NOTIFICATION: Task likely completed!" message if a task that was previously working at high progress (>=95%) changes to an idle/completed state.

## 8. Troubleshooting

*   **Connection Issues:**
    *   Double-check email/password (case-sensitive).
    *   Ensure your mower is online and has a stable internet connection.
    *   Check for firewall issues on your computer or network.
    *   Use the `connect` command to re-attempt connection or restart the script.
*   **Commands Not Working:**
    *   Ensure the mower is in an appropriate state for the command.
    *   Allow a few seconds for commands to be processed and status to update. The script generally attempts to refresh status after most commands.
    *   Use `raw_status` to inspect the mower's complete state.
    *   Use `status` to check the mower's current activity.
*   **Incomplete Plan List (`maps` command):**
    *   Run `sync_maps`. Wait 10-15 seconds. Then run `maps` again.
*   **`AttributeError` or Command Not Found:**
    This usually means the command name used does not map to a known function in the `PyMammotion` library as expected by the script. Check for typos.

## 9. Advanced Notes

### Device-Specific Behavior

*   **`mow_areas` Command:**
    *   **Yuka:** If a Yuka device is detected, the `blade_height` for the custom job will automatically be set to `-10` in `OperationSettings` as required.
    *   **Luba 1:** If a Luba 1 device is detected, `toward_mode` and `toward_included_angle` are set to `0` in the `GenerateRouteInformation` object sent to the mower, as Luba 1 may not support these advanced path angle settings.

### Enum Value Parsing for `mow_areas`

*   For settings in the `mow_areas` command that correspond to `PyMammotion` enums (e.g., `job_mode`, `mowing_laps`, `channel_mode`), the script expects you to provide the **string name** of the enum member (e.g., `GRID_FIRST`, `ONE`, `SINGLE_GRID`).
*   Parsing is case-insensitive and also attempts to match if underscores are omitted or present differently (e.g., `gridfirst` or `GRID_FIRST`).
*   Refer to the output of `mow_areas show` (or `mow_areas` with no arguments) for a list of valid Enum member names for each setting.

### Configuration Files

The script uses two JSON files in the same directory where it's run:
*   **`map_cache.json`**: Stores the last fetched map data (areas, plans, etc.) to speed up subsequent startups and provide offline access to map info. This is loaded on startup and saved on exit or after `sync_maps`.
*   **`mow_defaults.json`**: Stores default settings for the `mow_areas` command. This file is created with initial hardcoded defaults if it doesn't exist. You can modify it directly or use the `mow_areas set ...` command.

## 10. Examples

**Example `maps` command output structure:**
```
MowerControl> maps

--- Tasks/Plans (from mower.map.plan) ---

PlanId                | Days                      | Start Time | Name                 | Height | Speed
---------------------------------------------------------------------------------------------------------
174670239929556252383 | Tue, Fri                  | 10:20      | Front Yard Schedule  | 60     | 0.5
890123456789012345671 | Sun                       | 09:00      | Back Garden Weekly   | 65     | 0.4
---------------------------------------------------------------------------------------------------------


--- Mapped Areas (from mower.map.area_name) ---

No.   | Area Name                    | Hash
-----------------------------------------------------------------
1     | Front Lawn Main              | 9012456789012345678
2     | Backyard Zone A              | 8765321098765432101
-----------------------------------------------------------------
```

**Example Actions:**

1.  **Start the plan 'Front Yard Schedule' using its Name:**
    ```
    MowerControl> start Front Yard Schedule
    ```
2.  **Start a plan using its PlanId:**
    ```
    MowerControl> start 174670239929556252383
    ```
3.  **Mow Area 'Front Lawn Main' (hash `9012456789012345678`) with specific settings:**
    (Assuming `mowing_laps` has `ONE` as a member, `toward_mode` has `ABSOLUTE_ANGLE`, from `mow_areas show` output)
    ```
    MowerControl> mow_areas 9012456789012345678 mowing_laps=ONE toward_mode=ABSOLUTE_ANGLE toward=45 speed=0.5
    ```
4.  **Set new defaults for mowing speed and job mode:**
    ```
    MowerControl> mow_areas set speed=0.6 job_mode=GRID_FIRST
    ```
    Then check the new defaults:
    ```
    MowerControl> mow_areas show
    ```
