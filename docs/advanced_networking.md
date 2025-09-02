# Technical Documentation: Advanced Networking

This document provides a technical overview of the advanced networking capabilities of the `pymammotion` robot and its RTK base station. The protocol supports sophisticated configurations for both the RTK correction data source and the robot's cellular connection. These features are currently unimplemented in the high-level library API but offer significant benefits for performance and flexibility.

---

## 1. Internet RTK (NTRIP) Configuration

By default, the robot receives RTK correction data from its paired base station via a direct LoRa radio link. However, the protocol allows for configuring the base station to connect to a third-party internet RTK correction service, commonly known as an NTRIP caster. This allows the base station to act as an NTRIP client, fetching correction data over the internet and then relaying it to the robot.

This is a professional-grade feature that can provide more accurate, more reliable, or more geographically flexible RTK correction data than the standard base station setup.

### Message: `app_to_base_mqtt_rtk_t`

-   **Source:** `basestation.proto`
-   **Direction:** App/Client -> Base Station
-   **Purpose:** To configure the base station's NTRIP client settings.

#### Fields:

| Field Name       | Type     | Description                                                                                                                                                             |
| :--------------- | :------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rtk_switch`     | `int32`  | Enables or disables the NTRIP client feature (e.g., 0=Off, 1=On).                                                                                                       |
| `rtk_url`        | `string` | **(Required)** The hostname or IP address of the NTRIP caster.                                                                                                          |
| `rtk_port`       | `int32`  | **(Required)** The port number for the NTRIP caster.                                                                                                                    |
| `rtk_username`   | `string` | The username for authenticating with the NTRIP service. Required for non-public casters.                                                                                |
| `rtk_password`   | `string` | The password for authenticating with the NTRIP service.                                                                                                                 |

#### Developer Capabilities Enabled:

-   **Improved Accuracy:** Users can connect to professional or state-run CORS (Continuously Operating Reference Station) networks, which can offer higher accuracy and reliability than the consumer-grade base station.
-   **Eliminate Base Station Line-of-Sight:** In scenarios where the robot operates in an area with poor radio reception from its base station but has good internet connectivity (via WiFi), using an internet NTRIP source can provide a stable correction stream.
-   **Flexibility:** Allows the use of a single, remote internet-based reference station to serve multiple robots over a large area.

---

## 2. Custom Cellular APN Configuration

The robot models equipped with a cellular modem can be configured with custom APN (Access Point Name) settings. This allows a developer or advanced user to use a SIM card from a different carrier than the one provided by Mammotion.

### Message: `MnetApnSetCfg` & `SetMnetCfgReq`

-   **Source:** `dev_net.proto`
-   **Direction:** App/Client -> Robot
-   **Purpose:** To configure the cellular modem's APN settings. The main message to send is `SetMnetCfgReq`, which contains an `MnetCfg` object, which in turn contains an `MnetApnSetCfg` object.

#### `MnetApnSetCfg` Fields:

| Field Name      | Type          | Description                                                                                             |
| :-------------- | :------------ | :------------------------------------------------------------------------------------------------------ |
| `use_default`   | `bool`        | If `true`, the robot will use its default, pre-configured APN settings. If `false`, it will use the custom settings provided in the `cfg` field. |
| `cfg`           | `MnetApnCfg`  | A message containing the custom APN configuration.                                                      |

#### `MnetApnCfg` Fields:

| Field Name       | Type          | Description                                                                                             |
| :--------------- | :------------ | :------------------------------------------------------------------------------------------------------ |
| `apn_used_idx`   | `int32`       | The index of the APN to use from the `apn` list.                                                        |
| `apn`            | `repeated MnetApn` | A list of custom APN configurations.                                                                    |

#### `MnetApn` Fields (The core APN settings):

| Field Name    | Type          | Description                                                                                             |
| :------------ | :------------ | :------------------------------------------------------------------------------------------------------ |
| `apn_alias`   | `string`      | A human-readable name for the APN setting.                                                              |
| `apn_name`    | `string`      | **(Required)** The Access Point Name provided by the cellular carrier (e.g., "internet" or "iot.carrier.com"). |
| `auth`        | `apn_auth_type` | The authentication type required by the carrier (e.g., `APN_AUTH_NONE`, `APN_AUTH_PAP`, `APN_AUTH_CHAP`). |
| `username`    | `string`      | The username for APN authentication, if required.                                                       |
| `password`    | `string`      | The password for APN authentication, if required.                                                       |

#### Developer Capabilities Enabled:

-   **Carrier Freedom:** This is a critical feature for users in regions where the default cellular provider has poor coverage or for developers who want to use their own M2M/IoT data plans. By inserting their own SIM card and sending these configuration messages, they can switch the robot to their preferred carrier.
-   **Private Networks:** This enables the use of the robot on private cellular networks (e.g., private LTE/5G), which is a common requirement for large-scale commercial or industrial deployments.
