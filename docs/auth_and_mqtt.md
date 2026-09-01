# Mammotion Auth & MQTT Reference

Source: APK v2.2.4.13 (`com.agilexrobotics`)
Key files examined:
- `com/agilexrobotics/maiot_module/api/MaIoTApiService.java`
- `com/agilexrobotics/maiot_module/helper/MaIoTRequestHelper.java`
- `com/agilexrobotics/maiot_module/mqtt/MQTTClient.java`
- `com/agilexrobotics/maiot_module/MQTTService.java`
- `com/agilexrobotics/maiot_module/utils/SignUtil.java`
- `com/agilexrobotics/maiot_module/utils/Constants.java`
- `com/agilexrobotics/iot_module/third/utils/AliIoTLoginUtil.java`

---

## Overview

The APK supports two separate IoT backends, selected by a per-device `iot_type` flag:

| `iot_type` | System | Devices |
|---|---|---|
| `"1"` | **Mammotion MA** (direct MQTT + REST) | Post-2025 devices |
| `"0"` | **Aliyun IoT** (legacy AEP SDK) | Pre-2025 devices |
| `"2"` | Local / Bluetooth | All device types |

These are completely separate credential systems with separate connection paths.

---

## Hardcoded App Credentials

From `Constants.java` (production build, `HttpConstants.isRelease == true`):

```
APP_KEY    = "VJd2Q3zDXW"
APP_SECRET = "f46b29501aa183c4f0dfcd8d785e8296"
BASE_URL   = "https://api-iot-region.mammotion.com"
```

The `region` placeholder in the base URL is replaced at runtime with the user's region
key extracted from the JWT claim `region_key` (via `JWTUtils.getClaim(token, "region_key")`).
The resolved URL is stored in SharedPreferences under `SP_MA_IoT_REGION_BASE_URL`.

Debug/staging values:
```
APP_KEY    = "ZyZkcxZjDq"
APP_SECRET = "66bce078b65b5a271450e4d74d7f374c"
BASE_URL   = "https://api-iot-region-t.mammotion.com"
```

---

## MA Account System (Post-2025 Devices)

### Token Types

Three separate credentials are maintained simultaneously:

| Token | Stored in | Obtained from | Used for |
|---|---|---|---|
| HTTP access token (Bearer JWT) | `SP_MA_IoT_ACCESS_TOKEN` | `/oauth2/login` or `/oauth2/token` | All API calls |
| HTTP refresh token | `SP_MA_IoT_REFRESH_TOKEN` | `/oauth2/login` | Renewing the access token |
| MQTT JWT | not persisted | `/v1/mqtt/auth/jwt` | MQTT password |

### HMAC-SHA256 Request Signing

Login and token-refresh endpoints require a signature header. From `SignUtil.java`:

```
signature = HMAC-SHA256(data_string, APP_SECRET)
encoded as lowercase hex
```

Required headers on signed requests:
```
Ma-Iot-App-Key:      <APP_KEY>
Ma-Iot-Sign-Version: 1.0.0
Ma-Iot-Timestamp:    <unix_ms>
Ma-Iot-Signature:    <hmac_sha256_hex>
```

All other endpoints use `Authorization: Bearer <access_token>`.

### HTTP Endpoints

Base URL: `https://api-iot-<region>.mammotion.com`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/oauth2/login` | HMAC signed | Initial login; returns `access_token` + `refresh_token` |
| POST | `/oauth2/token` | HMAC signed | Refresh tokens; body: `refresh_token` |
| POST | `/v1/mqtt/auth/jwt` | Bearer | Get MQTT JWT; called before every MQTT connect |
| POST | `/v1/ma-user/region` | Bearer | Resolve regional base URL and MQTT broker host |
| POST | `/v1/user/region` | HMAC signed | Older region lookup (deprecated path) |
| POST | `/v1/user/device/page` | Bearer | List devices |
| POST | `/v1/user/device/window/bind` | Bearer | Bind device to account |
| POST | `/v1/user/device/unbind` | Bearer | Unbind device |
| PUT | `/v1/user/device/nick-name` | Bearer | Rename device |
| POST | `/v1/mqtt/rpc/thing/properties/get` | Bearer | Cloud property read |
| POST | `/v1/mqtt/rpc/thing/properties/set` | Bearer | Cloud property write |
| POST | `/v1/mqtt/rpc/thing/service/invoke` | Bearer | Cloud service invocation |

### Token Refresh Flow

From `MaIoTRequestHelper.java`:

**Reactive refresh (on 401 / non-zero API code):**
1. `getJWTForAuth(retry=true)` is called before each MQTT connect.
2. If the JWT endpoint returns a non-zero code, `refreshToken()` is called first,
   then `getJWTForAuth(retry=false)` is retried once.
3. If the token refresh itself fails, the session is considered invalid and
   the app triggers re-login.

**`isLogin()` check:**
```java
return getStatus().isReady() && !TextUtils.isEmpty(getAccessToken())
```
Any flow that needs auth first checks `isLogin()`.

**Error codes returned by the helper layer:**
| Code | Meaning |
|---|---|
| `0` | Success |
| `-10000` | Unknown exception |
| `-10001` | Internal exception |
| `-10002` | Retrofit/network exception |
| `-10003` | Not logged in ("no login.") |

---

## MA MQTT Connection (Post-2025)

### Broker Details

The MQTT broker hostname is **not hardcoded** — it is returned by the `/v1/ma-user/region`
endpoint along with the regional REST base URL. Port **1883** (plain TCP) is used by the
`MQTTClient`. The APK uses Eclipse Paho MQTT v5 (`org.eclipse.paho.mqttv5.client`).

### Credential Assembly

Both `userName` and `password` are set to the **JWT token** returned by `/v1/mqtt/auth/jwt`.
This is an unusual pattern (the token is used as both username and password).

```java
options.setUserName(jwtToken);
options.setPassword(jwtToken.getBytes());
```

The `clientId` is device-specific (assembled from device identifiers).

### Connection Parameters

From `MQTTClient.java`:

| Parameter | Value |
|---|---|
| Connection timeout | 30 seconds |
| Keep-alive interval | 60 seconds |
| Automatic reconnect | enabled |
| Clean start | true |
| QoS | 0 (all subscriptions) |

### Connection Lifecycle

From `MQTTService.java`:

1. Call `getJWTForAuth(retry=true)` — if the access token is expired this triggers
   a token refresh before fetching the JWT.
2. Call `getMaRegion()` — resolves the broker hostname and regional base URL.
3. Construct `MQTTClient` with JWT credentials.
4. `mqttAsyncClient.connect(options)` with a 15-second `CountDownLatch` timeout.
5. On `connectComplete(reconnect, cause)`:
   - Notify listeners (`connectStatus = 1`).
   - Call `mqttClient.reSubscribe()` to restore all previously subscribed topics.
6. On `disconnected(response)`:
   - Notify listeners (`connectStatus = 0`).
   - Automatic reconnect (built into Paho) will retry; a full `fullReconnect()` is
     available for forced reconnection (closes client, creates new, re-subscribes).

### Topic Patterns

| Topic suffix | Content |
|---|---|
| `/thing/status` | Device online/offline status |
| `/property/post` | Device property updates (includes `otaProgress`) |
| `device_protobuf_msg_event` | Binary protobuf messages (main command channel) |
| `device_log_progress_event` | Log upload progress events |

### Full Reconnect vs Automatic Reconnect

- **Automatic reconnect** (Paho built-in): Re-uses existing credentials; kicks in on
  transient disconnects. `reSubscribe()` is called on `connectComplete`.
- **`fullReconnect()`**: Called when credentials may have changed (e.g. after token
  refresh). Forcibly disconnects, destroys the client, fetches a fresh JWT, and builds
  a new `MQTTClient` from scratch.

---

## Invoke Token Refresh (MA System)

The `POST /v1/mqtt/rpc/thing/service/invoke` endpoint is the HTTP path used to send
protobuf commands to a device when a direct MQTT connection is not available (cloud relay).

### Auth Header

```
Authorization: Bearer <access_token>
```

No HMAC signature is required for invoke — only the Bearer token.

### APK Behavior: No Automatic Interceptor

From `MaIoTApiService.java` and `MaIoTRequestHelper.serviceInvoke()`: there is **no
OkHttp `Authenticator` or 401 interceptor**. The app manually checks the response code
in the callback:

```java
// In MaIoTRequestHelper.serviceInvoke() callback:
if (code == 401 && retry) {
    refreshMaToken(new RefreshMaTokenReq(refreshToken));
    // then retries the original call once with retry=false
}
```

The `retry` boolean flag is passed in from the call site. If `retry=false`, a 401 is
passed straight through to the caller without another refresh attempt.

### Token Refresh Endpoint

`POST /oauth2/token` (same endpoint used for proactive refresh — not a separate path).

**Request body** (query params in practice, matching the APK's `RefreshMaTokenReq`):
```
client_id     = <APP_KEY>
refresh_token = <current_refresh_token>
grant_type    = "refresh_token"
```

**Signature header** — `Ma-Iot-Signature` is required and is computed as:

```
data_to_sign  = APP_KEY + timestamp_ms + "/oauth2/token" + json(body)
Ma-Iot-Signature = HMAC-SHA256(data_to_sign, APP_SECRET)  [lowercase hex]
```

On success the response returns a new `access_token` and `refresh_token`, which are
stored and used for all subsequent requests.

### Python Implementation

`MammotionHTTP.mqtt_invoke()` is decorated with `@refresh_token_decorator`, which
**proactively** checks token expiry before the call:

```python
if self.expires_in < time.time() + 300:   # 5-minute lookahead
    await self.refresh_login()
```

`refresh_login()` calls `refresh_token_v2()` if the token has not yet expired,
otherwise falls back to a full `login_v2()`. On a reactive 401 from the invoke
response, `UnauthorizedException` is raised and the caller (transport layer) is
responsible for triggering a re-login.

`refresh_token_v2()` calls `POST /oauth2/token` with the same body fields as the APK.
The signature string is assembled as:

```
str_to_sign = client_id + timestamp_ms + "/oauth2/token" + json(body, compact)
key         = MD5(client_secret).hexdigest()         # ← differs from APK
signature   = HMAC-SHA256(str_to_sign, key) [lowercase hex]
```

> **Note:** The Python implementation hashes the client secret with MD5 before using
> it as the HMAC key. The APK's `SignUtil` uses the raw `APP_SECRET` bytes directly.
> These are different credential pairs (`MAMMOTION_OAUTH2_CLIENT_ID/SECRET` vs
> `MA_IoT_APP_KEY/SECRET`) so both are internally consistent — they are not the same
> signing operation applied to the same secret.

---

## Aliyun IoT System (Pre-2025 / Legacy)

From `AliIoTLoginUtil.java` and `com.aliyun.iot.aep.sdk.*`.

### Credential Types

- **Aliyun IoT Token**: Managed by `IoTCredentialManageImpl` (Aliyun AEP SDK).
  Stored in `IoTCredentialData`; retrieved via `getIoTToken()`.
- **Auth code**: Short-lived code obtained from `/authorization/code` using
  `HttpConstants.OAUTH_ALI_CLIENT_ID`.

### Token Refresh Flow

From `AliIoTLoginUtil.refreshToken()`:

```
1. Acquire synchronized lock (CountDownLatch prevents concurrent refresh).
2. Compare current token with stored token — skip if already refreshed by another caller.
3. Call IotApi.getInstance().iotRefresh().
4. On failure: IotApi.getInstance().logout() → login() → refresh again.
5. On success: store new credentials via IoTCredentialManageImpl.
```

The Aliyun system has a fallback of full logout+login when refresh fails, unlike the
MA system which only retries once before propagating the error.

### MQTT Connection

Uses the Aliyun AEP SDK directly — the connection parameters (broker host, port,
HMAC-SHA1 credential assembly) are handled internally by `com.aliyun.iot.aep.sdk`.
The Python side uses `AliyunMQTTTransport` which replicates this manually:
- Broker: Aliyun IoT endpoint (product-key based hostname)
- Port: 8883 (TLS)
- Auth: HMAC-SHA1 signed credentials

### Product Key List (MA IoT devices)

From `MaIoTApp.java` — devices with these product keys use the MA system (`iot_type="1"`):

```
pdA6uJrBfjz, USpE46bNTC7, CDYuKXTYrSP, NnbeYtaEUGE, zkRuTK9KsXG,
6DbgVh2Qs5m, HR4H6GXNcMG, VzYKDtUJQhe, mxR26AUHJvc, 4hyGWnWvKZD,
uY54W5rM8YH, 3drMFnqGVNe, 5BMtap5Q3Yq, rBGTwYhfhyY, 3wGqhPzhxct,
a15Cq8FbCh1, GJzsmaVk5za, fEaKVY28tNz, FCtXbVnmd2C, YBRDhT2YTvY,
tBnCA8u2Aps, jvEDnj42DRK
```

All other product keys use the Aliyun system.

---

## Python Implementation Notes

The Python library (`TokenManager`, `MQTTTransport`, `AliyunMQTTTransport`) mirrors this:

| APK component | Python equivalent |
|---|---|
| `MaIoTRequestHelper.getJWTForAuth()` | `TokenManager.get_mammotion_mqtt_credentials()` |
| `MaIoTRequestHelper.refreshToken()` | `TokenManager.get_valid_http_token()` |
| `MQTTClient` + `MQTTService` | `MQTTTransport` (aiomqtt, JWT password) |
| Aliyun AEP SDK + `AliIoTLoginUtil` | `AliyunMQTTTransport` (paho, HMAC-SHA1, port 8883) |
| `Constants.MA_IoT_APP_KEY_VALUE` | hardcoded in `MammotionHTTP` |
| `SignUtil.signWithHmacSHA256()` | `MammotionHTTP._generate_signature()` |

Key divergence: the APK fetches a fresh MQTT JWT **before every connect attempt** (including
after automatic reconnect completes). The Python `TokenManager` proactively refreshes
30 minutes before expiry and also on `AuthError`, which achieves the same goal without
re-fetching on every reconnect.
