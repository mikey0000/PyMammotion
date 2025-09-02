# Technical Documentation: Perception System

This document provides a deep technical dive into the protobuf messages related to the `pymammotion` robot's perception system. This system is the source of the richest and most complex real-time data from the robot, and understanding it is key to unlocking advanced capabilities.

The primary messages are part of the `MctlPept` (`pept` for perception) and `MctlSys` payloads.

---

## 1. Real-time Obstacle Visualization

This is the most significant unimplemented feature. The robot can stream a list of all obstacles it currently detects, including their classification and precise boundaries.

### Message: `perception_obstacles_visualization_t`

-   **Source:** `mctrl_pept.proto`
-   **Direction:** Robot -> App/Client
-   **Purpose:** Provides a complete snapshot of all detected obstacles in the robot's immediate vicinity. This message is likely sent periodically as a `REPORT` when the perception system is active.

#### Fields:

| Field Name  | Type                               | Description                                                                                                                              |
| :---------- | :--------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------- |
| `status`    | `int32`                            | The status of the perception system itself.                                                                                              |
| `num`       | `int32`                            | The total number of unique obstacles currently detected. This corresponds to the number of `perception_obstacles_t` messages in the `obstacles` field. |
| `obstacles` | `repeated perception_obstacles_t` | A list containing the details for each individual obstacle.                                                                              |
| `timestamp` | `double`                           | The timestamp (likely Unix time with milliseconds) when this perception snapshot was generated.                                          |
| `scale`     | `float`                            | A scale factor that may need to be applied to the `points_x` and `points_y` coordinates.                                                 |

### Sub-Message: `perception_obstacles_t`

This message contains the details for a single obstacle.

| Field Name | Type            | Description                                                                                                                                                                                                   |
| :--------- | :-------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `label`    | `int32`         | An enum or integer representing the classified type of the obstacle (e.g., 1=Tree, 2=Person, 3=Pole). The exact mapping of these integer labels is currently unknown and would need to be determined experimentally. |
| `num`      | `int32`         | The number of points that make up the boundary of this obstacle. This corresponds to the length of the `points_x` and `points_y` arrays.                                                                     |
| `points_x` | `repeated sint32` | An array of signed integers representing the X-coordinates of the obstacle's boundary polygon. The coordinates are relative to the robot's own coordinate frame.                                            |
| `points_y` | `repeated sint32` | An array of signed integers representing the Y-coordinates of the obstacle's boundary polygon.                                                                                                              |

#### Developer Capabilities Enabled:

-   **Live Obstacle Map:** A client application could listen for these messages and use the data to draw a real-time 2D map of the robot's surroundings, showing the exact position and shape of all detected obstacles.
-   **Enhanced Remote Control:** A remote control interface could display this map to the operator, providing situational awareness far beyond what a simple camera stream could offer.
-   **Data Analysis:** By logging this data, developers could analyze the perception system's performance, understand its limitations, and potentially build higher-level obstacle avoidance logic.

---

## 2. Navigation Costmap

The robot can provide a `costmap`, a grid-based representation of its environment used for pathfinding.

### Message: `costmap_t`

-   **Source:** `mctrl_nav.proto`
-   **Direction:** Robot -> App/Client (`toapp_costmap`)
-   **Purpose:** To transmit the robot's internal navigation costmap, which it uses to find paths that avoid obstacles and difficult terrain.

#### Fields:

| Field Name | Type            | Description                                                                                                                                                           |
| :--------- | :-------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `width`    | `int32`         | The width of the costmap grid in cells.                                                                                                                               |
| `height`   | `int32`         | The height of the costmap grid in cells.                                                                                                                              |
| `center_x` | `float`         | The real-world X-coordinate of the center of the costmap.                                                                                                             |
| `center_y` | `float`         | The real-world Y-coordinate of the center of the costmap.                                                                                                             |
| `yaw`      | `float`         | The rotation (yaw) of the costmap grid relative to the world frame.                                                                                                   |
| `res`      | `float`         | The resolution of the map in meters per cell. For example, a `res` of 0.05 means each grid cell is 5cm x 5cm.                                                          |
| `costmap`  | `repeated int32` | A flattened 1D array of cost values. The size of this array is `width * height`. Each value represents the "cost" of traversing that cell (e.g., 0=Free, 255=Lethal Obstacle). |

#### Developer Capabilities Enabled:

-   **Pathfinding Visualization:** By rendering the costmap as a color-graded grid, developers can see exactly how the robot perceives its environment. This is an invaluable tool for debugging why the robot might choose a particular path or get stuck in a certain area.
-   **Advanced Behavior Analysis:** Observing how the costmap changes over time can provide insights into how the robot reacts to dynamic obstacles or changing terrain conditions.

---

## 3. Vision System Control & Data

The protocol defines messages for controlling the vision system and receiving other vision-related data streams.

### Message: `vision_ctrl_msg`

-   **Source:** `mctrl_nav.proto`
-   **Direction:** App/Client -> Robot
-   **Purpose:** To send control commands to the vision/perception system.

| Field Name | Type    | Description                                                                                             |
| :--------- | :------ | :------------------------------------------------------------------------------------------------------ |
| `type`     | `int32` | The type of control command. The exact enum is unknown.                                                 |
| `cmd`      | `int32` | The command value (e.g., 0=Off, 1=On). This would likely be used to enable/disable the perception system to save power. |

### Message: `vio_to_app_info_msg`

-   **Source:** `mctrl_sys.proto`
-   **Direction:** Robot -> App/Client
-   **Purpose:** To stream real-time Visual-Inertial Odometry (VIO) data. VIO is a technique used to estimate the robot's position and orientation by combining camera data with inertial sensor data (IMU).

| Field Name           | Type    | Description                                                                 |
| :------------------- | :------ | :-------------------------------------------------------------------------- |
| `x`, `y`, `heading`  | `double`  | The robot's estimated position and heading from the VIO system.             |
| `vio_state`          | `int32` | The current state of the VIO system (e.g., Initializing, Tracking, Lost).   |
| `brightness`         | `int32` | The average brightness of the camera image, useful for detecting low-light conditions. |
| `detect_feature_num` | `int32` | The number of visual features detected in the current camera frame.         |
| `track_feature_num`  | `int32` | The number of visual features currently being tracked across multiple frames. |

#### Developer Capabilities Enabled:

-   **Deep Diagnostics:** VIO data is essential for diagnosing complex navigation failures. A developer could plot the VIO position against the GPS/RTK position to identify drift or discrepancies. Monitoring the number of tracked features can indicate when the robot is struggling to localize visually.
-   **Power Management:** The `vision_ctrl_msg` could be used to create application-level logic that turns off the perception system when not needed (e.g., when docked) to conserve battery.
