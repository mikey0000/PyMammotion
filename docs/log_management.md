# Technical Documentation: Remote Log Management

This document provides a technical overview of the robot's remote log management capabilities. The `pymammotion` protocol includes a powerful feature that allows a client to command the robot to upload its internal log files to a specified URL. This is an essential tool for deep, offline debugging of the robot's behavior.

This feature is currently unimplemented in the high-level library API.

---

## 1. Log Upload Mechanism

The log upload process is initiated by the client and executed by the robot. The client sends a single command containing all the necessary information for the upload.

### Message: `DrvUploadFileReq`

-   **Source:** `dev_net.proto`
-   **Direction:** App/Client -> Robot (`todev_req_log_info`)
-   **Purpose:** To command the robot to package and upload one or more of its internal log files to a specified HTTP endpoint.

#### Fields:

| Field Name | Type                    | Description                                                                                                                                                                                                     |
| :--------- | :---------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bizId`    | `string`                | A "business ID" or transaction ID, likely used to uniquely identify this upload request. A client should generate a unique string (e.g., a UUID) for this field.                                                |
| `url`      | `string`                | **(Required)** The full HTTP/HTTPS URL of the server endpoint where the robot should `POST` the log files. The server at this URL must be prepared to accept a multipart/form-data upload.                        |
| `userId`   | `string`                | The user ID associated with the request.                                                                                                                                                                        |
| `num`      | `int32`                 | The number of log files to upload.                                                                                                                                                                              |
| `type`     | `DrvUploadFileFileType` | **(Required)** An enum specifying the category of logs to upload. See the available types below.                                                                                                                |

### Log Type Enum: `DrvUploadFileFileType`

This enum specifies which logs the robot should collect and upload.

| Enum Value         | Log Category    | Description                                                                                             |
| :----------------- | :-------------- | :------------------------------------------------------------------------------------------------------ |
| `FILE_TYPE_ALL`    | All Logs        | Upload all available logs.                                                                              |
| `FILE_TYPE_SYSLOG` | System Logs     | General system-level logs, likely containing information about the operating system, services, and errors. |
| `FILE_TYPE_NAVLOG` | Navigation Logs | Detailed logs from the navigation subsystem, crucial for debugging pathfinding and localization issues.   |
| `FILE_TYPE_RTKLOG` | RTK Logs        | Raw data logs from the RTK (Real-Time Kinematic) GPS module, essential for diagnosing positioning accuracy problems. |

### Monitoring Upload Progress

The robot reports the status of the log upload via the `SysUploadFileProgress` and `BleLogUploadUpdateProgress` messages.

-   **Message:** `SysUploadFileProgress` (from `mctrl_sys.proto`)
-   **Direction:** Robot -> App/Client
-   **Purpose:** Provides periodic updates on the upload progress.

| Field Name | Type     | Description                                                                                                           |
| :--------- | :------- | :-------------------------------------------------------------------------------------------------------------------- |
| `bizId`    | `string` | The unique transaction ID from the original request, used to correlate the progress update with the command.          |
| `result`   | `int32`  | The status of the upload (e.g., 0=Success, 1=Fail).                                                                   |
| `progress` | `int32`  | An integer from 0 to 100 representing the percentage of the upload that is complete.                                  |


---

## 2. Developer Capabilities and Implementation Path

### Capabilities Enabled:

-   **Deep Offline Analysis:** This feature is the ultimate tool for debugging complex, intermittent issues that cannot be diagnosed with real-time data alone. By retrieving the raw navigation and RTK logs, a developer can replay a mowing session and analyze the robot's decision-making process frame by frame.
-   **Centralized Fleet Diagnostics:** For users managing multiple robots, this feature could be used to build a system that automatically collects logs from all devices and aggregates them on a central server for analysis.

### Conceptual Implementation Guide:

A developer seeking to implement this feature in the library would need to:

1.  **Set up a Server Endpoint:** Create a web server capable of receiving `POST` requests with `multipart/form-data` content.
2.  **Create a High-Level API Method:** Add a method to the `Mammotion` class, such as `request_log_upload(log_type: DrvUploadFileFileType) -> str`. This method would:
    a. Generate a unique `bizId`.
    b. Construct the `DrvUploadFileReq` protobuf message, filling in the `url` of the server endpoint and the requested `log_type`.
    c. Send the command to the robot.
    d. Return the `bizId` to the caller so they can track the upload progress.
3.  **Handle Progress Notifications:** Add logic to the main message handling loop to parse incoming `SysUploadFileProgress` messages. This logic would use the `bizId` to route the progress update to the correct handler or callback, allowing the application to display a progress bar to the user.
