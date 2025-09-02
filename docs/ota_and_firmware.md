# Technical Documentation: OTA & Firmware Management

This document provides a technical overview of the protobuf messages used to manage the robot's Over-The-Air (OTA) firmware updates, as defined in `mctrl_ota.proto`. The protocol supports querying for updates, monitoring progress, and, most significantly, retrieving a direct download URL for the firmware image.

---

## 1. Checking for Updates and Monitoring Progress

The client can ask the robot about its current firmware version and the status of any ongoing OTA process.

### Message: `getInfoReq`

-   **Source:** `mctrl_ota.proto`
-   **Direction:** App/Client -> Robot (`todev_get_info_req`)
-   **Purpose:** To request either base device information or OTA status information.

#### Fields:

| Field Name | Type     | Description                                                                                              |
| :--------- | :------- | :------------------------------------------------------------------------------------------------------- |
| `type`     | `infoType` | An enum to specify the type of information requested. `IT_BASE` for device info, `IT_OTA` for update status. |

### Message: `getInfoRsp`

-   **Source:** `mctrl_ota.proto`
-   **Direction:** Robot -> App/Client (`toapp_get_info_rsp`)
-   **Purpose:** To provide the information requested by `getInfoReq`. It uses a `oneof` to return either `baseInfo` or `otaInfo`.

#### `otaInfo` Sub-Message Fields:

| Field Name | Type     | Description                                                                 |
| :--------- | :------- | :-------------------------------------------------------------------------- |
| `otaid`    | `string` | A unique ID for the OTA transaction.                                        |
| `version`  | `string` | The version of the firmware being installed.                                |
| `progress` | `int32`  | The progress of the update as a percentage (0-100).                         |
| `result`   | `int32`  | The final result of the update (e.g., 0=Success, 1=Fail).                   |
| `message`  | `string` | A human-readable message associated with the status (e.g., "Download failed"). |

---

## 2. Firmware Image URL Discovery (High Impact)

This is a highly significant, unimplemented feature. The protocol defines a message that the robot can send to the client which contains a direct download URL for a firmware image.

### Message: `FotaInfo_t` & `FotaSubInfo_t`

-   **Source:** `mctrl_ota.proto`
-   **Direction:** Robot -> App/Client
-   **Purpose:** To inform the client about an available firmware update, including where to download it from.

#### `FotaInfo_t` Fields (The main update notification):

| Field Name         | Type    | Description                                                              |
| :----------------- | :------ | :----------------------------------------------------------------------- |
| `need_ota_num`     | `int32` | The number of sub-modules that require an update.                        |
| `need_ota_img_size`| `int32` | The total size in bytes of all firmware images to be downloaded.         |
| `ota_version`      | `string`| The target version for this OTA update.                                  |

#### `FotaSubInfo_t` Fields (Sent for each sub-module):

| Field Name        | Type     | Description                                                                                                                                                             |
| :---------------- | :------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sub_mod_id`      | `int32`  | The ID of the specific hardware module to be updated (e.g., main controller, Bluetooth chip).                                                                           |
| `sub_img_size`    | `int32`  | The size in bytes of this specific module's firmware image.                                                                                                             |
| `sub_mod_version` | `string` | The new version for this specific module.                                                                                                                               |
| `sub_img_url`     | `string` | **(Key Field)** A direct HTTP/HTTPS URL from which the firmware image file for this module can be downloaded.                                                             |

#### Developer Capabilities Enabled:

-   **Firmware Archiving and Analysis:** A developer could create a tool that listens for these messages, automatically downloads the firmware images from the provided URLs, and archives them. This would allow for offline analysis, reverse engineering, and comparison between different firmware versions.
-   **Manual / Custom Updates:** While risky, this capability provides a path for developers to manually flash firmware updates, potentially allowing for downgrades or applying custom patches if the firmware format were ever understood.
-   **Enhanced Update Process:** A third-party application could implement its own, more robust firmware download and update process instead of relying solely on the official app.
