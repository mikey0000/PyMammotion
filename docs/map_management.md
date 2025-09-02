# Technical Documentation: Map Management & Synchronization

This document provides a technical overview of the protobuf messages used to create, edit, and synchronize the robot's map data. Managing maps is a complex process that involves drawing boundaries, defining obstacles, creating pathways, and ensuring the local map is in sync with the robot's internal state. These messages are primarily defined in `mctrl_nav.proto`.

---

## 1. The Core Map Editing Command: `NavGetCommData`

Many different map editing actions (drawing, deleting, etc.) are multiplexed through a single, powerful message: `NavGetCommData`. The specific action is determined by the combination of the `action` and `type` fields.

### Message: `NavGetCommData`

-   **Source:** `mctrl_nav.proto`
-   **Direction:** App/Client -> Robot (`todev_get_commondata`)
-   **Purpose:** To send a wide variety of map-related commands to the robot.

#### Key Fields:

| Field Name | Type    | Description                                                                                              |
| :--------- | :------ | :------------------------------------------------------------------------------------------------------- |
| `action`   | `int32` | **(Required)** An enum-like integer specifying the primary action (e.g., Draw, Save, Delete).            |
| `type`     | `int32` | **(Required)** An enum-like integer specifying the type of map element the action applies to (e.g., Boundary, Obstacle, Channel). |
| `hash`     | `fixed64` | The hash/ID of the map element to be operated on, used for actions like deletion.                        |

### Common `action` and `type` Combinations

| Action | Type | Command Description                             |
| :----- | :--- | :---------------------------------------------- |
| `0`    | `0`  | Start Drawing Boundary                          |
| `0`    | `1`  | Start Drawing Obstacle                          |
| `0`    | `2`  | Start Drawing Channel Line                      |
| `1`    | `0`  | End Drawing Boundary                            |
| `1`    | `1`  | End Drawing Obstacle                            |
| `1`    | `2`  | End Drawing Channel Line                        |
| `4`    | `0`  | Start Erasing a map element                     |
| `5`    | `0`  | End Erasing a map element                       |
| `6`    | `0`  | Delete a Boundary                               |
| `6`    | `1`  | Delete an Obstacle                              |
| `6`    | `2`  | Delete a Channel Line                           |
| `6`    | `5`  | Delete the Charging Point                       |
| `6`    | `6`  | **Delete All Map Data**                         |
| `7`    | `0`  | Cancel the current drawing/erasing operation    |
| `8`    | `1`  | Synchronize data for a specific map hash (see below) |

---

## 2. Map Synchronization

The robot's map is composed of many data elements, each identified by a unique hash. To ensure the client has the complete and latest map, a multi-step synchronization process is used. This is one of the most complex interactions in the protocol.

### Step 1: Get the List of All Hashes

The client first requests a list of all the hashes that make up the map.

-   **Message:** `NavGetHashList`
-   **Direction:** App/Client -> Robot (`todev_gethash`)
-   **Purpose:** To request the list of all hashes for a specific category of map data.
-   **Key Field `subCmd`:**
    -   `0`: Get hashes for map boundaries, obstacles, and channels.
    -   `3`: Get hashes for saved jobs (`??` - based on code comments).
    -   `4``: Get hashes for Yuka-specific dump locations (`??` - based on code comments).

The robot responds with a `NavGetHashListAck` message, which contains a `repeated int64 dataCouple` field with the list of hashes.

### Step 2: Request Data for Each Hash

Once the client has the list of all hashes, it can compare it with its local copy. For any missing or outdated hashes, the client requests the full data.

-   **Message:** `NavGetCommData`
-   **Direction:** App/Client -> Robot (`todev_get_commondata`)
-   **Purpose:** To request the full data packet for a specific map element hash.
-   **Usage:**
    -   Set `action = 8`
    -   Set `subCmd = 1`
    -   Set `hash` to the specific hash number you want to retrieve data for.

The robot responds with a `NavGetCommDataAck` message, which contains the actual map data (e.g., boundary points) in the `repeated CommDataCouple dataCouple` field. This data may be split across multiple frames, requiring the client to send further `NavGetCommData` requests with updated `currentFrame` values until `currentFrame == totalFrame - 1`.

---

## 3. Naming and Managing Map Areas

### Message: `NavMapNameMsg`

-   **Source:** `mctrl_nav.proto`
-   **Direction:** Bidirectional
-   **Purpose:** To set or get the human-readable name for a specific map area.

#### Key Fields:

| Field Name | Type     | Description                                                                                                   |
| :--------- | :------- | :------------------------------------------------------------------------------------------------------------ |
| `rw`       | `int32`  | Read/Write flag. `0` to request the name for a given hash, `1` to set the name for a given hash.                |
| `hash`     | `fixed64`| The unique hash/ID of the map area to be named or queried.                                                    |
| `name`     | `string` | When writing (`rw=1`), this field contains the new name for the area.                                         |
| `deviceId` | `string` | The ID of the device this map belongs to.                                                                     |
| `result`   | `int32`  | A result code, populated in the robot's response.                                                             |

### Message: `ManualElementMessage`

-   **Source:** `mctrl_nav.proto`
-   **Direction:** Robot -> App/Client (`toapp_manual_element`)
-   **Purpose:** Appears to be for reporting manually added geometric shapes on the map, though its exact usage is unclear. It supports elements like points and rectangles (`shape` field) with coordinates and rotation. This could be related to a "manual no-go zone" feature.
