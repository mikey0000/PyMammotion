# Mammotion MA-IoT Proxy: Architecture & Current Status

> **Status (2026-04-16):** *Parked.* The MA-IoT client is implemented and
> verified end-to-end (auth, region resolution, device list) but it is **not
> wired into the transport/coordinator** because this repo's current users own
> Luba 2 hardware that Mammotion routes through the legacy Aliyun stack. When
> a MA-IoT–eligible device is added, this client can be activated with a
> single product-key check — see [Resurrection Checklist](#resurrection-checklist)
> below.

---

## Background: two parallel device platforms

Starting with app version 2.2.4.x, Mammotion has been migrating off Aliyun
IoT. The resulting split shows up clearly in the decompiled app:

1. **Legacy Aliyun stack** (Luba 1, Luba 2, original Yuka/Yuka Plus, Luba V/VP,
   Luba Mini, Luba LD, RTK, etc.)
    - Auth: `/uc/*` on `eu-central-1.api-iot.aliyuncs.com` + `session_by_authcode`.
    - Commands: Aliyun IoT "cloud gateway" (`/thing/service/*`) with HMAC-SHA256.
    - MQTT: Aliyun IoT broker (`*.iot-as-mqtt.*.aliyuncs.com`).
    - Rate limits: strict per-account quotas → the `TooManyRequestsException`
      and `refreshToken invalid!!` (`code=2401`) errors that motivated this
      work.

2. **MA-IoT proxy** (Yuka Mini V, Luba LA HM432, Yuka MN100, Kumar CM900, and
   a broad list of 2024/2025 SKUs).
    - Auth: `Authorization: Bearer <access_token>` from the encrypted
      `/oauth/token` login.
    - Commands: Mammotion's own HTTPS proxy at
      `api-iot-business-<region>-dcdn.mammotion.com`.
    - MQTT: broker + JWT credentials issued by `/v1/mqtt/auth/jwt`.
    - Rate limits: **much** more generous in practice (proxy-side enforcement,
      not Aliyun's per-account quotas).

The app decides which system to use *per device* via
`MaIoTApp.isMaIotDevice(productKey)`, a hard-coded whitelist (see below).
A user account can legitimately have devices on **both** systems
simultaneously.

---

## MA-IoT product-key whitelist

From `apk_analysis/decompiled/sources/com/agilexrobotics/maiot_module/MaIoTApp.java`
line 754 (app 2.2.4.13):

| Product key    | Model (best known mapping)     |
|----------------|--------------------------------|
| `pdA6uJrBfjz`  | Yuka Mini V (MN231) — see `YukaMVProductKey` |
| `USpE46bNTC7`  | Yuka Mini V (MN231) |
| `CDYuKXTYrSP`  | Luba LA (HM432) — see `LubaLAProductKey` |
| `NnbeYtaEUGE`  | Ezy-VT / Yuka MN100 — see `YukaMN100ProductKey` |
| `zkRuTK9KsXG`  | Kumar CM900 (KM01) — see `Cm900ProductKey` |
| `6DbgVh2Qs5m`  | Kumar CM900 (KM01) |
| `HR4H6GXNcMG`  | Unmapped — newer 2024+ model |
| `VzYKDtUJQhe`  | Unmapped |
| `mxR26AUHJvc`  | Unmapped |
| `4hyGWnWvKZD`  | Unmapped |
| `uY54W5rM8YH`  | Unmapped |
| `3drMFnqGVNe`  | Unmapped |
| `5BMtap5Q3Yq`  | Unmapped |
| `rBGTwYhfhyY`  | Unmapped |
| `3wGqhPzhxct`  | Unmapped |
| `a15Cq8FbCh1`  | Unmapped |
| `GJzsmaVk5za`  | Unmapped |
| `fEaKVY28tNz`  | Unmapped |
| `FCtXbVnmd2C`  | Unmapped |
| `YBRDhT2YTvY`  | Unmapped |
| `tBnCA8u2Aps`  | Unmapped |
| `jvEDnj42DRK`  | Unmapped |

Keys on *this* list use the new short (11-char, no `a1` prefix) Mammotion
format. Legacy Aliyun product keys use `a1…` (e.g. Luba 2: `a1UBFdq6nNz`,
`a1iMygIwxFC`, `a1mb8v6tnAa`, `a1L5ZfJIxGl`). None of the `a1…` keys are on
the MA-IoT whitelist, so **every currently-supported Luba 2 variant is
Aliyun-only**.

---

## MA-IoT endpoints (reference)

All paths are relative to the per-region base URL (e.g.
`https://api-iot-business-eu-dcdn.mammotion.com`). All responses are wrapped
in the `{code, msg, requestId, data}` envelope.

| Endpoint                                   | Purpose                                        | Auth            |
|-------------------------------------------|------------------------------------------------|-----------------|
| `POST /v1/ma-user/region`                 | Resolve regional base URL                       | Bearer          |
| `POST /v1/user/region`                    | (Legacy) resolve region                         | Signed Ma-Iot-* |
| `POST /v1/user/device/page`               | List owned devices (`pageNumber`, `pageSize`)  | Bearer          |
| `POST /v1/user/device/window/bind`        | Bind a device                                   | Bearer          |
| `POST /v1/user/device/unbind`             | Unbind a device                                 | Bearer          |
| `PUT  /v1/user/device/nick-name`          | Rename a device                                 | Bearer          |
| `POST /v1/mqtt/auth/jwt`                  | Issue MQTT broker host + JWT credential        | Bearer          |
| `POST /v1/mqtt/rpc/thing/properties/get`  | Read device property set                        | Bearer          |
| `POST /v1/mqtt/rpc/thing/properties/set`  | Write device properties                         | Bearer          |
| `POST /v1/mqtt/rpc/thing/service/invoke`  | Invoke a device service (protobuf command)     | Bearer          |
| `POST /authorization/code`                | Issue Aliyun-compatible auth code (bridge)     | Bearer          |

The `Ma-Iot-App-Key` / `Ma-Iot-Signature` / `Ma-Iot-Timestamp` /
`Ma-Iot-Sign-Version` headers only apply to `getRegion`, `login`, and the
legacy `refreshToken` variant; all modern endpoints take a plain
`Authorization: Bearer <access_token>` header. The app uses app-key value
`VJd2Q3zDXW` (production) or `ZyZkcxZjDq` (sandbox).

---

## JWT claims on the OAuth access token

The access token minted by the encrypted `/oauth/token` flow (see
`pymammotion/http/http.py::login_v2`) is a JWT whose payload contains two
claims the MA-IoT client depends on:

```json
{
  "iot":   "api-iot-business-eu-dcdn.mammotion.com",
  "robot": "api-robot-eu.mammotion.com"
}
```

`iot` is the per-region base URL for every MA-IoT call — it matches the value
returned by `POST /v1/ma-user/region`, so the app (and this client) skip the
extra round-trip and use the claim directly. `robot` is used for a separate
set of endpoints (recording uploads, OTA, support tickets) that are out of
scope for the HA integration.

Decoding is handled in `MammotionHTTP.response.setter` and stored on
`MammotionHTTP.jwt_info: JWTTokenInfo`.

---

## What's already implemented in this repo

The MA-IoT infrastructure is committed but dormant. Files:

- `pymammotion/http/ma_iot.py` — `MammotionMaIoT` client class. Handles region
  resolution (prefers JWT claim, falls back to `/v1/ma-user/region`), device
  list, MQTT credentials, properties get/set, and service invoke. Pure
  transport, no coordinator coupling.
- `pymammotion/http/model/ma_iot.py` — request/response dataclasses (mashumaro
  `DataClassORJSONMixin`).
- `pymammotion/const.py::MA_IOT_REGION_DOMAIN = "https://api-iot-region.mammotion.com"`.
- `test_ma_iot.py` — end-to-end smoke test that logs in, resolves the base
  URL, and lists devices.

### Verified working (2026-04-16)

Running `test_ma_iot.py` against `willbeeching@gmail.com` produced:

```
✓ logged in as 62224713 (userId=780108121170247680)
  JWT iot claim  : https://api-iot-business-eu-dcdn.mammotion.com
  JWT robot claim: api-robot-eu.mammotion.com
✓ MA-IoT base URL from JWT: https://api-iot-business-eu-dcdn.mammotion.com
  explicit region lookup: status=200 body={"code":0,"msg":"Request success",
    "data":{"regionEndpoint":"https://api-iot-business-eu-dcdn.mammotion.com"}}
✓ devices: total=0 pages=0 size=100 current=1
```

0 devices is the expected outcome for this user — their Luba 2 is on Aliyun,
not MA-IoT.

---

## Why it's parked

The integration's current primary pain point is `TooManyRequestsException`
from Aliyun on Luba 2 hardware. Since MA-IoT doesn't serve Luba 2, shipping
the MA-IoT client doesn't address that — it's infrastructure for *future*
hardware. The active work is therefore happening in the Aliyun path (see
`cloud_gateway.py`, `DeviceCommandQueue`, and the saga stack).

---

## Resurrection checklist

When it's time to wire MA-IoT into the transport (because a user gets an
MA-IoT-eligible device, or Mammotion migrates existing devices server-side):

1. **Detect eligibility.** Add a helper mirroring the app's whitelist:

   ```python
   _MA_IOT_PRODUCT_KEYS = frozenset({
       "pdA6uJrBfjz", "USpE46bNTC7", "CDYuKXTYrSP", "NnbeYtaEUGE",
       "zkRuTK9KsXG", "6DbgVh2Qs5m", "HR4H6GXNcMG", "VzYKDtUJQhe",
       "mxR26AUHJvc", "4hyGWnWvKZD", "uY54W5rM8YH", "3drMFnqGVNe",
       "5BMtap5Q3Yq", "rBGTwYhfhyY", "3wGqhPzhxct", "a15Cq8FbCh1",
       "GJzsmaVk5za", "fEaKVY28tNz", "FCtXbVnmd2C", "YBRDhT2YTvY",
       "tBnCA8u2Aps", "jvEDnj42DRK",
   })

   def is_ma_iot_device(product_key: str | None) -> bool:
       return product_key in _MA_IOT_PRODUCT_KEYS
   ```

   Ideally live under `pymammotion.utility.device_type`, next to the existing
   per-family product-key constants.

2. **Plumb through `DeviceHandle`.** Route `send_raw` to a new
   `MaIoTTransport` when `is_ma_iot_device(handle.product_key)` — otherwise
   keep the existing Aliyun transport. The transport API already has an
   async `send(payload, iot_id=…)` contract; the MA-IoT transport just needs
   to wrap `MammotionMaIoT.service_invoke(iot_id, product_key, device_name,
   identifier="thing.service.<cmd>", args={"content": base64(payload)})`.

3. **Replace Aliyun MQTT with MA-IoT MQTT** for eligible devices. Use
   `get_mqtt_credentials(client_id, username)` to obtain the broker host +
   JWT, then reuse the existing MQTT transport's connect path with the
   returned credentials (auth is JWT in the `password` field per Mammotion's
   Paho config; no other protocol changes required).

4. **Subscribe to the right topics.** `MaIoTApp.java` subscribes to:

   ```
   /sys/<productKey>/<deviceName>/thing/event/+/post
   /sys/proto/<productKey>/<deviceName>/thing/event/+/post
   /sys/<productKey>/<deviceName>/_thing/status
   ```

   The `proto` variant delivers protobuf events; the others are JSON.

5. **Refresh tokens via `/v1/ma-user/oauth2/token`.** The OAuth access token
   expires (see `expires_in`); refresh by re-calling the encrypted login flow
   or using the `refreshMaToken` endpoint with the same app-key/signature
   scheme as `getRegion`.

6. **Add a coordinator-level switch.** Expose a per-device flag
   (`transport: "ma_iot" | "aliyun"`) on the HA config entry so users can opt
   in/out while the migration settles.

7. **Run `test_ma_iot.py` with MA-IoT credentials** (an account that owns,
   say, a Yuka Mini V) to confirm `devices` is non-empty and the MQTT / get
   properties paths return real data.

If Mammotion ever publishes an API that returns `isMaIot` per device (the
`sharedNotifiyBean.isMaIot()` hook in `NotificationAcativity.java` suggests
they already track it server-side), prefer that over the hard-coded
whitelist.

---

## Known unknowns

- **Cross-platform device sharing.** `NotificationAcativity` hands out
  `isMaIot` on share invites, which implies shared devices can belong to
  either platform independently of the receiver's other devices. We haven't
  exercised that code path.
- **`/authorization/code` bridge.** The endpoint exists to obtain an
  Aliyun-compatible auth code from an MA-IoT session. It may let us run a
  *single* auth flow that services both platforms in a mixed-fleet account —
  worth exploring when we need it.
- **Rate limits on the proxy.** The MA-IoT proxy clearly has *some* quota (it
  reports `code=2401` for expired tokens just like Aliyun), but the practical
  ceiling is unknown. The app has no visible backoff logic, which hints the
  ceiling is high enough not to matter for one-user-one-mower workloads.
