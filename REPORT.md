# PyMammotion Library: Comprehensive Analysis and Improvement Report

## 1. Current State and Functionality

This document provides a comprehensive analysis of the `pymammotion` library, detailing its current capabilities, architecture, and potential for future enhancements. The library is a third-party Python API for controlling Mammotion robotic mowers (Luba, Yuka series) and serves as the foundation for the Mammotion Home Assistant integration.

### 1.1. Core Architecture

The library is architected around a central singleton class, `Mammotion`, which acts as the primary entry point for developers. This class manages device discovery and communication channels.

-   **Device Management:** A `MammotionDeviceManager` tracks all known robots. Each robot is represented by a `MammotionMixedDeviceManager` instance, which is a key architectural component that manages the two distinct communication channels for that device.
-   **Communication Channels:** The library supports two primary communication methods:
    1.  **Cloud:** Via a persistent MQTT connection to Mammotion's servers, hosted on Alibaba Cloud (Aliyun).
    2.  **Bluetooth LE (BLE):** For direct, local control of the robot.
-   **State Management:** A `StateManager` instance is maintained for each device, holding its canonical state (e.g., position, battery level, current activity). This state is updated by incoming data from either communication channel.
-   **Command Structure:** Commands are dispatched through a unified `MammotionCommand` factory. This class uses a mixin pattern, inheriting methods from various `Message...` classes (`MessageNavigation`, `MessageSystem`, etc.) that are responsible for constructing the specific protocol buffer (`protobuf`) messages for each command.

### 1.2. Implemented Features

The library currently exposes a rich set of features, primarily focused on mowing operations, scheduling, and map management.

-   **Task Control:**
    -   Start, pause, resume, and cancel mowing jobs.
    -   Command the robot to return to the charging dock.
-   **Map and Zone Management:**
    -   Create, edit, and delete task areas, including boundaries, no-go zones, and channels.
    -   Save and name map areas.
    -   A robust, multi-step map synchronization process to download map data from the robot.
-   **Scheduling:**
    -   Set, read, and delete complex mowing schedules with various parameters (time, frequency, mowing mode, etc.).
    -   Configure "do not disturb" periods.
-   **Manual Control:**
    -   Basic real-time movement commands (forward, backward, turn left/right), suitable for joystick-like control.
-   **State Reporting:**
    -   Real-time updates on robot status, including position, battery level, charging status, error codes, and current task progress.
-   **Job History:**
    -   The ability to query a list of past work reports.

## 2. Communication and Data Flow

The library's dual-channel communication system allows for both remote and local control.

### 2.1. Cloud (MQTT) Communication

The cloud connection is the primary method for remote access.

-   **Authentication:** The process is complex and multi-staged:
    1.  An initial HTTP login to Mammotion's authentication server with a username and password.
    2.  The returned token is used to perform a series of authentication calls against the Aliyun IoT API.
    3.  This sequence generates a temporary `device_secret` and other credentials required for the MQTT connection.
    4.  The MQTT password is created by generating an HMAC-SHA1 signature from the `device_secret` and other client identifiers.
-   **Data Exchange:**
    -   The library connects to an Aliyun IoT MQTT broker at an endpoint like `{product_key}.iot-as-mqtt.{region}.aliyuncs.com`.
    -   Commands are sent by publishing a serialized `LubaMsg` protobuf to the `/sys/.../app/up/thing/model/up_raw` topic.
    -   State updates and responses are received on the `/sys/.../app/down/thing/model/down_raw` topic.

### 2.2. Bluetooth LE (BLE) Communication

BLE provides direct, local control when the user's device is within range of the robot.

-   **Connection:** The library scans for BLE devices advertising a "Luba-" or "Yuka-" name and establishes a direct connection.
-   **Data Exchange:** Communication occurs over a standard UART-like GATT service (`0000ffff-...`).
    -   **Commands:** Serialized `LubaMsg` protobufs are sent by writing to the write characteristic (`0000ff01-...`).
    -   **State Updates:** Data is received as notifications on the notification characteristic (`0000ff02-...`).
-   **Data Flow:** Once received, the BLE data follows the same internal path as MQTT data, being passed to the `StateManager` to update the robot's state.

## 3. Partially Implemented Features

These are features where the underlying protocol support is present and some library code exists, but they are not fully implemented or exposed to the end-user.

-   **Connection Management:** The library currently requires a manual preference to be set for either `WIFI` or `BLUETOOTH`. The code contains `TODO` comments indicating the author's intent to implement a more intelligent, automatic failover system.
-   **Simulation Mode:** A low-level command `indoor_simulation()` exists, which sends a `SimulationCmdData` protobuf. However, this is not exposed through the high-level API, and its exact function and parameters are undocumented.
-   **Detailed Job History:** While the library can query for job history, the `WorkReportInfoAck` message returned by the robot contains a very rich set of data (work time, area, result, etc.) that may not be fully parsed and presented in a user-friendly format.

## 4. Unimplemented Features

This is the most significant area of opportunity. The robot's protocol defines a vast number of advanced capabilities that are not used at all in the current library code.

### 4.1. Perception System (Highest Impact)

The robot is equipped with a sophisticated, real-time perception system, likely camera-based. The data from this system is completely unused by the library.
-   **Live Obstacle Visualization:** The `perception_obstacles_visualization_t` message provides a list of detected obstacles, each with a classification `label` and a set of `(x,y)` points defining its boundary. This could be used to build a live map of the robot's surroundings.
-   **Navigation Costmap:** The `costmap_t` message provides a grid-based map of navigation costs, which could be used to visualize the robot's pathfinding decisions.
-   **Visual-Inertial Odometry (VIO) Data:** The `vio_to_app_info_msg` provides real-time VIO data, including position, heading, and the number of visual features being tracked, which would be invaluable for advanced diagnostics.
-   **Vision System Control:** The `vision_ctrl_msg` exists to send commands to the perception system (e.g., enable/disable), but it is not implemented.

### 4.2. Advanced Diagnostics and Configuration

-   **Hardware Self-Tests:** The protocol defines a comprehensive suite of quality control messages (`QCAppTest...`) that can trigger factory diagnostics for nearly every sensor and actuator on the robot. This is a powerful, unimplemented troubleshooting tool.
-   **Log File Uploads:** The `DrvUploadFileReq` message allows a client to command the robot to upload its internal system logs (`SYSLOG`, `NAVLOG`, `RTKLOG`) to a remote URL.
-   **Internet RTK (NTRIP):** The protocol supports configuring the RTK base station to connect to an internet-based NTRIP server for correction data, a professional-grade feature for achieving higher accuracy.
-   **Cellular APN Configuration:** The library can be configured to use a custom SIM card by setting the APN via the `MnetApnSetCfg` message.

### 4.3. Device Controls and Multimedia

-   **Cutter Work Modes:** The `AppSetCutterWorkMode` message allows for setting the cutter to `STANDARD`, `ECONOMIC`, or `PERFORMANCE` modes.
-   **Advanced Audio Control:** The `MulSetAudio` message allows for selecting the language and gender of the robot's voice prompts.
-   **Model-Specific Controls:** Features for camera wipers and the debris collection system (on Yuka models) are defined in the protocol but not exposed.
-   **Mysterious "Special Modes":** The `special_mode_t` message contains undocumented modes like `violent_mode` and `stair_mode` that are intriguing and completely unexplored.

## 5. Recommended Improvements

The following actionable recommendations are proposed to enhance the library's capabilities and developer experience.

### 5.1. Priority 1: Implement Core Unimplemented Features

-   **Expose Perception Data:** The highest priority should be to parse and expose the perception system data. This would be a game-changing feature for visualization and advanced control.
-   **Unified Connection Management:** Refactor the connection logic to provide automatic, seamless switching between Bluetooth and Cloud, removing the burden from the developer.
-   **Create a Diagnostics API:** Expose the powerful hardware self-tests and log upload capabilities through a dedicated, high-level `diagnostics` API.

### 5.2. Priority 2: Expose Untapped Device Controls

-   **Add Full Multimedia Control:** Implement methods to control the audio language/gender, headlight brightness, and wipers.
-   **Add Cutter Power Modes:** Expose the ability to switch between the standard, economic, and performance cutter modes.
-   **Expose "Special Modes":** Add the commands for the undocumented "special modes" to allow the community to experiment and discover their function.

### 5.3. Priority 3: Documentation and Examples

-   **Create Protocol Documentation:** Add a `PROTOCOL.md` file to the repository that documents the key findings from this report, especially the structure of the perception messages and other unimplemented features. This would dramatically lower the barrier for new contributors.
-   **Expand Code Examples:** Provide more example scripts that demonstrate how to perform common tasks and use the more advanced features of the library.
