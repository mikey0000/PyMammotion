# Technical Documentation: Task Control & Scheduling

This document provides a technical overview of the protobuf messages used to control the robot's tasks, such as starting a mow, pausing, and returning to the dock. It also covers the rich scheduling system. These messages are primarily defined in `mctrl_nav.proto`.

---

## 1. Real-time Task Control

Real-time control over the current task is handled by the `NavTaskCtrl` message. This single message type is used for multiple actions, differentiated by the `action` field.

### Message: `NavTaskCtrl`

-   **Source:** `mctrl_nav.proto`
-   **Direction:** App/Client -> Robot (`todev_taskctrl`)
-   **Purpose:** To send high-level commands to the currently active or pending task.

#### Fields:

| Field Name | Type    | Description                                                                                                                                                                                               |
| :--------- | :------ | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `type`     | `int32` | The category of the task control. For mowing tasks, this is typically `1`. The value `3` is used for resetting the base station position.                                                                  |
| `action`   | `int32` | **(Required)** An enum-like integer that specifies the action to perform. See the table below for a list of known actions.                                                                                  |
| `result`   | `int32` | A field for the robot to populate in response messages. When sending a command, this is typically set to `0`.                                                                                               |
| `reserved` | `string`| A reserved field, typically unused when sending commands.                                                                                                                                                 |

#### Known `action` Values (for `type = 1`):

| Action Value | Command                 | Description                                                                                             |
| :----------- | :---------------------- | :------------------------------------------------------------------------------------------------------ |
| `1`          | Start Job               | Begins the scheduled or prepared mowing task.                                                           |
| `2`          | Pause Job               | Pauses the currently running job.                                                                       |
| `3`          | Resume Job              | Resumes a previously paused job.                                                                        |
| `4`          | Cancel Job              | Stops and cancels the current job completely.                                                           |
| `5`          | Return to Dock          | Commands the robot to stop its current task and return to the charging station.                         |
| `7`          | Continue from Breakpoint| Resumes a job from a specific breakpoint, likely after an interruption like low battery.                |
| `9`          | Continue from Anywhere  | Resumes a job from the robot's current physical position, rather than a formal breakpoint.              |
| `10`         | Return to Dock (Test)   | A test command for the return-to-dock procedure.                                                        |
| `12`         | Cancel Return to Dock   | Cancels a pending return-to-dock command.                                                               |

---

## 2. Starting a Specific (Ad-Hoc) Job

To start a mowing job that is not part of a recurring schedule, the `NavStartJob` message is used.

### Message: `NavStartJob`

-   **Source:** `mctrl_nav.proto`
-   **Direction:** App/Client -> Robot (`todev_mow_task`)
-   **Purpose:** To start a one-time mowing task with specified parameters.

#### Fields:

| Field Name     | Type     | Description                                                                 |
| :------------- | :------- | :-------------------------------------------------------------------------- |
| `jobId`        | `int64`  | The unique ID of the task area to mow. This is likely a hash of the map data. |
| `jobVer`       | `int32`  | The version of the job/map data.                                            |
| `jobMode`      | `int32`  | The mowing mode (e.g., in-out, back-and-forth). The enum is unknown.        |
| `rainTactics`  | `int32`  | What to do in case of rain (e.g., 0=Stop, 1=Continue).                      |
| `knifeHeight`  | `int32`  | The desired cutting height in millimeters.                                  |
| `speed`        | `float`  | The mowing speed.                                                           |
| `channelWidth` | `int32`  | The width of the mowing channels/lanes.                                     |
| `UltraWave`    | `int32`  | Whether to use the ultrasonic obstacle avoidance sensors (0=Off, 1=On).     |
| `channelMode`  | `int32`  | The pattern for mowing channels.                                            |

---

## 3. Creating and Managing Schedules

The protocol supports a very rich scheduling system, allowing for complex, recurring jobs.

### Message: `NavPlanJobSet`

-   **Source:** `mctrl_nav.proto`
-   **Direction:** App/Client -> Robot (`todev_planjob_set`)
-   **Purpose:** To create, update, read, or delete a scheduled job plan. The `subCmd` field determines the action.

#### Key Fields:

| Field Name              | Type            | Description                                                                                               |
| :---------------------- | :-------------- | :-------------------------------------------------------------------------------------------------------- |
| `subCmd`                | `int32`         | The action to perform (e.g., 0=Create/Update, 1=Delete, 2=Read).                                          |
| `planId`                | `string`        | A unique identifier for the schedule plan.                                                                |
| `jobId`                 | `string`        | The ID of the task/area to be mowed in this schedule.                                                     |
| `taskName` / `jobName`  | `string`        | Human-readable names for the task and job.                                                                |
| `startTime` / `endTime` | `string`        | The start and end time for the job in "HH:MM:SS" format.                                                  |
| `startDate` / `endDate` | `string`        | The date range for which this schedule is active.                                                         |
| `weeks`                 | `repeated fixed32` | A list of integers representing the days of the week for recurring jobs (e.g., Monday=1, Sunday=7).     |
| `triggerType`           | `int32`         | The type of job (e.g., manual trigger, scheduled trigger).                                                |
| `knifeHeight`, `speed`, etc. | (various) | The same mowing parameters as in `NavStartJob`.                                                           |
| `zoneHashs`             | `repeated fixed64`| A list of hashes for the specific zones to be mowed in this job.                                          |

### Executing a Scheduled Job

While schedules can trigger automatically, a specific scheduled job can also be triggered manually.

### Message: `nav_plan_task_execute`

-   **Source:** `mctrl_nav.proto`
-   **Direction:** App/Client -> Robot
-   **Purpose:** To manually trigger the execution of a single, saved scheduled job.

#### Fields:

| Field Name | Type     | Description                                                          |
| :--------- | :------- | :------------------------------------------------------------------- |
| `subCmd`   | `int32`  | The action to perform (e.g., 1=Execute).                             |
| `id`       | `string` | The `planId` of the schedule to execute.                             |
| `name`     | `string` | The human-readable name of the plan to execute.                      |
| `result`   | `int32`  | A field for the robot's response.                                    |
