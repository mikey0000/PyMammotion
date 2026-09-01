# PyMammotion Architecture

The durable structural guide for this repository: what the layers are, who owns
each concern, how the four flows run, and where to add things. `CLAUDE.md`
carries the agent-facing rules and the *invariants*; this file carries the *map*.

Read this before adding a module. The architecture is layered and almost every
concern already has exactly one home — a second copy is nearly always the wrong
fix.

---

## 1. What the library is

`pymammotion` drives Mammotion robot mowers (Luba, Luba 2, Yuka), RTK base
stations and Spino pool cleaners over three interchangeable links — Aliyun IoT
MQTT (pre-2025 devices), Mammotion direct MQTT (post-2025), and Bluetooth LE.
It is the backend for the Mammotion Home Assistant integration, which is its
only significant consumer and the reason the public surface is a stability
constraint rather than an implementation detail.

The wire protocol is protobuf (`betterproto2`) with **no request IDs**. Almost
every structural decision downstream follows from that one fact — see §4.2.

---

## 2. Layer map

```
┌───────────────────────────────────────────────────────────────────────────┐
│ HOST FACADE                                                               │
│   homeassistant/mower_api.py   HomeAssistantMowerApi — call pacing,       │
│                                plan locking, HA-shaped accessors          │
├───────────────────────────────────────────────────────────────────────────┤
│ CLIENT  (one per process)                                                 │
│   client.py          MammotionClient — device lifecycle, transport        │
│                      construction, saga entry points, command send        │
│   client_auth.py     CloudAuthMixin — login, restore, TokenManager        │
│                      lifecycle  (mixin: the dependency is bidirectional)  │
│   account/registry.py    AccountSession / AccountRegistry                 │
│   device/inbound_router.py   (account_id, iot_id) -> DeviceHandle         │
│   device/ble_inventory.py    BleInventory — owns BLETransportManager      │
│   device/auto_fetch.py       AutoFetchWatchers — "field changed -> fetch" │
├───────────────────────────────────────────────────────────────────────────┤
│ DEVICE  (one per account per device)                                      │
│   device/handle.py       DeviceHandle facade + DeviceRegistry             │
│   device/state_reducer.py  pure LubaMsg -> Device   (Mower/Pool/RTK)      │
│   device/modes.py          _DeviceMode cadence classification             │
│   device/loop_host.py      Protocol the poll loops require of the handle  │
│   device/mqtt_loop.py  ble_loop.py  dynamics_line_loop.py                 │
│   device/readiness.py      "is base-level data present yet"               │
│   state/device_state.py    DeviceStateMachine, immutable DeviceSnapshot   │
├───────────────────────────────────────────────────────────────────────────┤
│ MESSAGING                                                                 │
│   messaging/broker.py         request/response correlation + EventBus     │
│   messaging/command_queue.py  priority queue, saga exclusivity, TTL       │
│   messaging/saga.py           Saga ABC (progress-based retry budget)      │
│   messaging/transfers.py      ack_stream / indexed_fetch free functions   │
│   messaging/{map,mow_path,plan,spino_plan,svg,edge,common_data}_saga.py   │
├───────────────────────────────────────────────────────────────────────────┤
│ TRANSPORT                                                                 │
│   transport/base.py       Transport ABC (message callback, activity       │
│                           timestamps, error window, availability          │
│                           listeners), error taxonomy, EventBus,           │
│                           Subscription, TransportType/Availability        │
│   transport/cloud.py      CloudTransport — send quota, terminal auth      │
│                           flags, thing/* callbacks, reconnect constants   │
│   transport/aliyun_mqtt.py  CloudTransport; paho, HMAC-SHA1, port 8883    │
│   transport/mqtt.py         CloudTransport; aiomqtt, JWT password         │
│   transport/ble.py          Transport; bleak + bleak-retry-connector      │
│   transport/envelope.py     one shared unwrap_envelope()                  │
├───────────────────────────────────────────────────────────────────────────┤
│ AUTH / CLOUD                                                              │
│   auth/token_manager.py   one per account; clock-driven refresh scheduler │
│   http/http.py            MammotionHTTP — REST + OAuth                    │
│   aliyun/cloud_gateway.py CloudIOTGateway — authCode chain, invoke        │
│   aliyun/exceptions.py    the one cloud error-code table                  │
├───────────────────────────────────────────────────────────────────────────┤
│ DATA MODEL  (no I/O, no upward imports)                                   │
│   data/model/*   device, hash_list, report_info, pool_state, svg,         │
│                  coordinates, device_capabilities, generate_geojson       │
│   data/mqtt/*    wire payload dataclasses (status, events, properties)    │
│   proto/         generated betterproto2 — never hand-edit                 │
├───────────────────────────────────────────────────────────────────────────┤
│ LEAF UTILITIES  (bottom layer — must not import upward)                   │
│   utility/{device_type,enum_base,plan_id,conversions,mur_mur_hash,...}    │
│   utility/constant/*   device_enums, poll_policy, display, ble_order      │
│   render/map_renderer.py   PIL + OSM tile renderer                        │
└───────────────────────────────────────────────────────────────────────────┘
```

**Import direction is downward only.** `tests/unit/utility/test_layering.py`
enforces it for `utility/` and for `data/`: nothing under `utility/` may import
`data`, `device`, `transport`, `aliyun`, `http`, `messaging`, `state` or
`bluetooth`, and nothing under `data/` may import `device`. The four files
under `utility/` that do (`map.py`, `svg.py`, `device_config.py`,
`map_renderer.py`) are explicitly-listed re-export shims kept alive for the HA
integration's existing imports; deleting one is a coordinated release.

---

## 3. The unit of everything: `(account_id, device_id)`

`DeviceRegistry` is keyed by the pair, not by device. One `DeviceHandle` per
account per device.

- A handle no cloud account has claimed lives under the sentinel key
  `BLE_ONLY_ACCOUNT` (`"__ble__"`). It is a **registry key only** — no
  `AccountSession` is ever registered under it, and `AccountSession.device_ids`
  lists cloud-bound devices alone.
- A cloud login for a device that already has a sentinel handle **re-keys that
  same object** (`DeviceRegistry.rekey`) rather than building a second one, so
  BLE transport, accumulated state and `prefer_ble` survive. Sign-out re-keys it
  back with the cloud transports detached.
- **BLE is per-device; cloud transports are account-shared.** Exactly one handle
  owns a device's `BLETransport` (`find_ble_owner`) until
  `BleInventory.move_ble_to_account` hands it over. A handle *detaches* a cloud
  transport (`detach_transport`) and never disconnects it — the session does
  that once.
- Every registration funnels through `MammotionClient._ensure_device_handle`.

---

## 4. The four flows

### 4.1 Inbound message

```
Transport.on_message(raw bytes)
  └─ MammotionClient wires transport callbacks to InboundRouter (partial-bound
     to account_id); the router resolves (account_id, iot_id) -> DeviceKey and
     looks the handle up in DeviceRegistry (never holds handles itself, because
     a handle can be re-keyed underneath it)
       └─ DeviceHandle.on_raw_message()
            1. decode bytes -> LubaMsg
            2. StateReducer.apply(current, msg) -> new Device        (pure)
            3. DeviceStateMachine.apply(new) -> DeviceSnapshot + changed fields
            4. emit snapshot on the debounced state_changed bus  (HA subscribes)
            5. DeviceMessageBroker.on_message(luba_msg)
                 ├─ solicited   -> resolve the pending future
                 └─ unsolicited -> EventBus.emit  (sagas, watchers)
```

Step 2 is a *pure function*: it takes the current `Device` and a message and
returns an updated one. It performs no I/O and holds no references upward. That
is what makes device state testable without a transport.

Any inbound MQTT frame also clears `mqtt_reported_offline`, so natural device
traffic re-arms sending with no manual reset.

### 4.2 Outbound command

```
HomeAssistantMowerApi                     (call pacing, dedupe)
  └─ MammotionClient.send_command_with_args(name, key, **kwargs)
       ├─ resolve handle; record_user_command()
       ├─ build bytes: getattr(handle.commands, key)(**kwargs)
       └─ handle.queue.enqueue(_do_send, priority, skip_if_saga_active)
            └─ DeviceCommandQueue._process           (TTL, dedup, saga gate)
                 └─ _do_send: has_usable_transport gate
                      └─ MammotionClient._send_with_auth_retry
                           └─ DeviceHandle.send_raw(payload, prefer_ble)
                                └─ active_transport() -> Transport.send()
```

A **direct priority** (`USER`, `EMERGENCY`) skips the middle of that chain
entirely — no `queue.enqueue`, no TTL, no exclusive-slot wait:

```
MammotionClient.send_command_with_args(..., priority=Priority.USER)
  └─ execute_command(_do_send, reraise=True)   (same retry + error buckets)
       └─ _send_with_auth_retry
            └─ DeviceHandle.send_raw(..., user_initiated=True)
                 └─ active_transport() -> CloudTransport.send_user()
                                          (or Transport.send() for BLE)
```

It is dispatched on the caller's task, because the queue processor is strictly
sequential: an item enqueued behind an in-flight saga waits for that saga's
`work()` to return however it is ranked. `DeviceCommandQueue.enqueue` raises
`ValueError` on a direct priority so this cannot be reintroduced by accident.

**Request/response correlation has no request ID.** The protobuf `oneof` field
name (e.g. `toapp_gethash_ack`) *is* the key. `DeviceMessageBroker.send_and_wait`
registers a future under that field name and resolves it under a lock;
`ConcurrentRequestError` is raised if the same field is already pending. This is
the constraint the saga layer is built around.

### 4.3 Saga

Sagas are restartable multi-step operations that must not interleave with other
traffic. They occupy the queue's `Priority.EXCLUSIVE` slot.

- They call `subscribe_unsolicited()` **before** sending, because the device can
  answer before the handler would otherwise be registered. The RAII
  `Subscription` unsubscribes on context exit.
- Protocol mechanics live in `messaging/transfers.py` as **free functions**
  (`ack_stream`, `indexed_fetch`, frame extraction) rather than base-class
  methods. That is deliberate: optional utilities hanging off a base class do
  not get adopted (measured: 1 saga in 7).
- `max_attempts` caps *consecutive fruitless* attempts. Any advance reported by
  the `progress()` hook resets the budget, because whole-run restart is the wrong
  granularity for a protocol where the device retransmits unacked frames.
- Stream completion is `len(frames) >= total_frame`, **not**
  `current_frame == total_frame` — a retransmitted final frame can arrive while
  an earlier one is still missing. Duplicate frames are **re-acked**, not
  skipped: a retransmit means the device did not hear the previous ack.
- The queue's `finally` always releases `_exclusive_active`, on cancellation and
  unhandled exception alike, or the device's queue deadlocks forever.

### 4.4 Credentials

One account = one login session = one `TokenManager`, and the login comes first.
`MammotionClient._ensure_token_manager` is the only construction site.

```
login_and_initiate_cloud ─┐                      (the only password grant)
restore_credentials ──────┤─> MammotionHTTP  ──> validate_login()
                          │        │              (local expiry, then one real
                          │        │               authenticated call)
                          │        ├──> _restore_aliyun     -> AliyunMQTTTransport
                          │        └──> _restore_mammotion  -> MQTTTransport
                          └─> TokenManager.start_refresh_scheduler()
```

Three renewal mechanisms, all clock-driven, one task per account that *sleeps
until* the earliest credential enters its lead window — it does not poll:

| credential          | lead window |
|---------------------|-------------|
| HTTP OAuth          | 5 min       |
| Mammotion MQTT JWT  | 30 min      |
| Aliyun IoT session  | 1 h         |

HTTP refreshes first: both the JWT and the Aliyun session are minted with the
HTTP access token. The scheduler exists because every *other* refresh path is
lazy — when all of an account's devices are offline nothing asks for a
credential, and the tokens would rot until the refresh tokens themselves expire.

**Failure is scoped, and a rejection is terminal.** There are no retry timers:
a rejected refresh token does not become valid by waiting.

| scope     | trigger                          | flag                     | effect |
|-----------|----------------------------------|--------------------------|--------|
| account   | `refresh_token_v2` rejected      | `reauth_required`        | `ReLoginRequiredError`, `on_unrecoverable_auth_error` fires, host prompts |
| transport | Aliyun/JWT unrenewable, login OK | `aliyun_unavailable` / `mqtt_unavailable` | that transport only; per-device bus signalled, global callback does **not** fire |
| neither   | transient network error          | none                     | propagates by type (`is_transient_network_error`) so callers back off |

---

## 5. Single homes — do not add a second one

| Question | The one place that answers it |
|---|---|
| Is anything sendable right now? | `DeviceHandle.has_usable_transport` / `active_transport()` |
| Is BLE usable? | `BLETransport.is_usable` (BLEDevice, RSSI, cooldown) |
| Is a cloud transport usable? | `CloudTransport.is_usable` (terminal auth flags) |
| Is a send within quota? | `CloudTransport.is_send_blocked(firmware, user_initiated=...)` — never `is_rate_limited`, `is_cloud_banned` or `is_quota_exhausted` directly |
| Should this exception be treated as expected? | `messaging.command_queue.execute_command` — the queue and the direct path share it |
| Does this command queue at all? | `Priority.is_direct` |
| What cadence does this device need? | `DeviceHandle.cadence_mode()` + the `_MQTT_POLL_INTERVAL` / `_BLE_POLL_INTERVAL` tables |
| Is this exception expected by the queue? | the demotion buckets in `DeviceCommandQueue._process` |
| What does this cloud error code mean? | `aliyun/exceptions.py` (`DEVICE_OFFLINE_CODES`, `DEVICE_UNBOUND_CODES`, `GATEWAY_TIMEOUT_CODES`) |
| Which handle owns this device's BLE? | `DeviceRegistry.find_ble_owner` |
| Which handle does this cloud frame belong to? | `InboundRouter` |
| What are this model's limits? | `data/model/device_capabilities.py::DeviceConfig` |
| What device variant is this? | `utility/device_type.py::DeviceType` |
| Is this work mode "active"/"no-request"? | `utility/constant/poll_policy.py` |

**Never send MQTT to a device the cloud reported offline.** Four gates enforce
it — `active_transport()`, `_mqtt_activity_loop`'s pre-flight,
`send_command_with_args`' short-circuit, and the automatic clear on any inbound
frame. A new send path must route through `send_raw` / `send_command_with_args`
or replicate the gate.

---

## 6. Extension recipes

**A new transport** — subclass `CloudTransport` if it talks to a broker (it
inherits the send quota, the terminal auth flags and the `thing/*` callbacks),
otherwise `Transport`. Implement `connect`, `disconnect`, `send`, `is_connected`,
`availability`, `transport_type`, and add the enum member to `TransportType`.
Shared behaviour goes on the *narrowest* base that needs it — putting a broker
concern on `Transport` puts it on BLE too. Wire construction in
`MammotionClient`, not in `DeviceHandle`.

**A new saga** — subclass `Saga` in `messaging/`, implement `_run(broker)` and
`progress()`. Use `ack_stream` / `indexed_fetch` from `transfers.py`; add an
`envelope` entry to `LEAF_GROUPS` if the leaf lives under a new oneof group.
Expose it as one `start_*` method on `MammotionClient` that resolves the handle
and calls `enqueue_saga`.

**A new command** — add the builder method to the right
`mammotion/commands/messages/*.py`; callers reach it by name through
`send_command_with_args`.

**A new device variant** — add the product key to `utility/device_type.py` and a
capability row to `data/model/device_capabilities.py`. Add a `DeviceType`
predicate rather than comparing product keys at the call site.

**A new cloud error code** — add it to the right set in `aliyun/exceptions.py`.
Both cloud send paths classify against those sets; never pattern-match a raw
code inline.

**A new poll cadence rule** — extend the interval table keyed by `_DeviceMode`.
Do not add an `if mode == ...` branch in a send path.

**A firmware-gated behaviour** — put the version comparison in a
`DeviceType`/strategy predicate (see `DetectionStrategy.for_device`), not inline.

---

## 7. Conventions and quality gates

- **Python 3.13+**, async throughout, 120-column lines.
- **Top-level imports only.** The single exception is a `TYPE_CHECKING` guard for
  hint-only imports that would otherwise cycle.
- **Prefer the walrus** wherever it removes a separate assignment line.
- **Direct key access** (`data["key"]`) where validation guarantees the key —
  surface contract violations instead of masking them.
- **Comments explain *why*.** No restating the next line, no section dividers, no
  "this used to be…".
- **Widen API response types** rather than swapping them: endpoint `data` shapes
  vary by device and firmware, so `Response[dict | bool]`, never the newly
  observed shape alone.
- **Wire-coerced enums subclass `UnknownTolerantIntEnum`** so unknown firmware
  values log once instead of crashing.
- **Time-dependent tests freeze the clock** (`time-machine` for `monotonic`).

Gates:

| gate | where |
|---|---|
| `ruff check` / `ruff format --check` | pre-commit (all) + CI (**changed files only**) |
| `ty check pymammotion/` | pre-commit only — **not in CI** |
| `pytest tests/ -m "not live"` | pre-commit + CI |
| proto codegen drift (`git diff --exit-code`) | CI |
| layering rules | `tests/unit/utility/test_layering.py` |
| documented invariants | `tests/unit/test_review_invariants.py` |

`pymammotion/proto/` is generated. Regenerate, never hand-edit:

```bash
uv run protoc -I=. --python_out=. --python_betterproto2_out=pymammotion/proto ./pymammotion/proto/*.proto
```

---

## 8. Reference material

Decompiled APK sources are the protocol ground truth; `docs/apk_*.md` records
what has been read out of them. When behaviour and the APK disagree, the APK
wins — several invariants above (frame re-acking, the 100003 dynamics-line
timer, the reactive-refresh token comparison) are ports of specific APK methods.
