# Mammotion APK 2.2.4.13 — Protocol & Architecture Analysis

Decompiled source location:
```
/home/michael/Downloads/Mammotion_2.2.4.13_APKPure/com.agilexrobotics/java_src/com/agilexrobotics/
```

---

## IoT Platform Types

The app has three distinct device connection backends:

```java
// Constants.java
IoT_TYPE_ALI   = "0"   // Aliyun IoT (pre-2025 mowers: Luba 1, Luba 2, Yuka)
IoT_TYPE_MA    = "1"   // Mammotion IoT (post-2025 / RTK base stations)
IoT_TYPE_LOCAL = "2"   // BLE / local connection
```

**RTK base stations always use Mammotion IoT (`IoT_TYPE_MA`)**, never Aliyun.

### Mammotion IoT device detection

`MaIoTApp.isMaIotDevice(productKey)` checks against a hardcoded list of Mammotion
product keys:

```
pdA6uJrBfjz, USpE46bNTC7, CDYuKXTYrSP, NnbeYtaEUGE,
zkRuTK9KsXG, 6DbgVh2Qs5m, ...
```

Any device whose `productKey` matches this list is a Mammotion IoT device and must
use the Mammotion cloud endpoints — not the Aliyun gateway.

---

## API Endpoints (Mammotion IoT)

| Path | Method | Purpose |
|------|--------|---------|
| `/v1/user/device/page` | POST | List all bound devices (returns `iotId`, `productKey`, `deviceName`, …) |
| `/v1/mqtt/rpc/thing/service/invoke` | POST | Send a command to a device |
| `/v1/mqtt/auth/jwt` | GET | Get MQTT JWT credentials |
| `/oauth2/login` | POST | Authenticate |
| `/oauth2/token` | POST | Refresh access token |
| `/v1/ma-user/region` | GET | Resolve regional API base URL |

Base host: `api-iot-region.mammotion.com` (beta: `api-iot-region-t.mammotion.com`)

> **Important:** `/device-server/v1/device/list` is **not** used by the app for
> Mammotion IoT device lookup. That endpoint is used for other device-server
> operations (OTA, settings, etc.) but the `iotId` it returns is not used for
> invoke calls.

---

## Device List (`/v1/user/device/page`)

### Request — `GetDeviceListReq`

```java
private int pageNumber = 1;
private int pageSize   = 100;
private Integer owned;     // nullable — omit to get all
private String iotId = ""; // optional filter
```

### Response — `DeviceRecord`

```java
private String identityId = "";
private String iotId      = "";   // canonical device identifier for invoke calls
private String productKey = "";
private String deviceName = "";
private String nickName   = "";
private int    owned;
private int    status;
private long   bindTime;
```

This is the **only** source of `iotId` for Mammotion IoT devices. The app calls this
endpoint periodically; it does not cache iotIds across sessions in a way that bypasses
this call.

---

## Service Invoke (`/v1/mqtt/rpc/thing/service/invoke`)

### Request — `ServiceInvokeReq`

```java
private String iotId      = "";
private String productKey = "";
private String deviceName = "";
private String identifier = "";   // e.g. "device_protobuf_sync_service"
private Args   args;              // args.content = base64-encoded protobuf payload
```

### Critical: `iotId` vs `productKey + deviceName`

The app can identify the target device in **two ways** — whichever fields are
non-empty:

```java
// MaIoTApp$invokService$1.java lines 55–66
if (!TextUtils.isEmpty(jSONObject.getString("iotId"))) {
    serviceInvokeReq.setIotId(jSONObject.getString("iotId"));
} else {
    serviceInvokeReq.setProductKey(jSONObject.getString("productKey"));
    serviceInvokeReq.setDeviceName(jSONObject.getString("deviceName"));
}
```

**The server accepts either form.** When `iotId` is unknown or empty, the app falls
back to `productKey + deviceName`. This means our Python transport can do the same:
if `handle.iot_id` is unavailable, passing `productKey` + `deviceName` in the invoke
request is a valid alternative.

---

## RTK Base Station Specifics

RTK device name prefixes and their `DeviceType`:

| Prefix | DeviceType | ProductKey prefix |
|--------|-----------|-------------------|
| `RTK`  | `RTK`     | various           |
| `RTKBAU` | `RTK`  | various           |
| `RBSA0` | `RTK3A0` | `RBS03A0`        |
| `RBSA1` | `RTK3A1` | `RBS03A1`        |
| `RBSA2` | `RTK3A2` | `RBS03A2`        |
| `NB`   | `RTKNB`   | various           |

RTK devices communicate via the Mammotion MQTT path exclusively. In the app:

```java
if (f7220a.type().isRTK()) {
    // RTK-specific message handling
    // Uses BASE_TO_APP_MQTT_RTK_MSG for incoming RTK data
}
```

---

## Implications for pymammotion

### Current issue

RTK devices (e.g. `RTKBAU242721575`) may appear in the Aliyun binding list
(`list_binding_by_account`) with a wrong or placeholder `iotId`. Registering them
via `_register_aliyun_device` causes sends to go through `AliyunMQTTTransport` /
`cloud_gateway.send_cloud_command`, which is incorrect for Mammotion IoT devices.

### Correct approach

1. Detect Mammotion IoT devices by `productKey` using `isMaIotDevice()` logic —
   i.e. check against the list of Mammotion product keys in `device_type.py`
   (`YukaMVProductKey`, `LubaLAProductKey`, `YukaMN100ProductKey`, `Cm900ProductKey`,
   and the RTK keys).

2. For these devices, skip Aliyun registration and register via
   `_register_mammotion_device` with `iotId` from `get_user_device_page()`.

3. If `iotId` is empty/wrong, fall back to **`productKey + deviceName`** in the
   `mqtt_invoke` call — the server supports this form.

### `mqtt_invoke` fallback

The current `MQTTTransport.send()` raises `TransportError` when `iot_id` is empty.
A better approach: if `iot_id` is empty, pass `productKey` and `deviceName` instead:

```python
# http.py mqtt_invoke — server accepts iotId OR productKey+deviceName
if iot_id:
    body["iotId"] = iot_id
else:
    body["productKey"] = product_key
    body["deviceName"] = device_name
```

---

## Key Source Files

| File | Contents |
|------|----------|
| `maiot_module/bean/response/DeviceRecord.java` | Device record with `iotId` |
| `maiot_module/bean/request/ServiceInvokeReq.java` | Invoke request structure |
| `maiot_module/api/MaIoTApiService.java` | All MA IoT API endpoint declarations |
| `maiot_module/utils/Constants.java` | API paths and IoT type constants |
| `maiot_module/MaIoTApp.java` | `isMaIotDevice()`, `invokService()` logic |
| `maiot_module/MaIoTApp$invokService$1.java` | iotId vs productKey+deviceName fallback |
| `device_module/device/enums/DeviceType.java` | RTK / mower type detection |
| `mvp/fieldmower/device/MACarDataManager.java` | Device state + message routing |
| `mvp/fieldmower/device/MACommandHelper.java` | Command builder (field mower) |
| `command/MACommandHelper.java` | Command builder (top-level) |
