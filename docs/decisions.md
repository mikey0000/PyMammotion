# Decision Record

Why the architecture is shaped the way it is. Each entry is a decision that was
made against a real alternative, kept because the reasoning is not recoverable
from the code — someone will otherwise re-propose the rejected option.

Distilled from the review documents that used to live at the repo root
(`ARCH_ISSUES.md`, `TODO.md`, `dead_code.md`), which had gone stale and were
removed. Open items from those documents were carried into
`docs/review-2026-08.md`.

---

## D1. The pre-refactor god-object stack was deleted, not deprecated

`pymammotion/mammotion/devices/` (`Mammotion`, `MammotionDeviceManager`,
`MammotionBaseBLEDevice`, `MammotionBaseCloudDevice`, `MammotionMowerDevice`,
`MammotionRTKDevice`) and `pymammotion/mqtt/` (`AliyunMQTT`, `MammotionMQTT`,
`MQTTConnectionPool`) are gone, along with `homeassistant/rtk_api.py`,
`bluetooth/data/convert.py`, `utility/periodic.py` and `transport/watchdog.py`.
`pymammotion/__init__.py` no longer re-exports `AliyunMQTT` / `MammotionMQTT`.

Nothing in the new architecture called any of it; keeping it as a shim would
have meant maintaining two device models against one protocol. The entry point
is `from pymammotion.client import MammotionClient`.

## D2. Saga mechanics are free functions, not base-class helpers

The `Saga` base once carried `extract_nav_frame`, `_collect_frames` and
`_next_frame` as optional helpers. **Adoption was 1 saga out of 7** — nine
hand-rolled `which_one_of` sites remained across six files. Inheriting a base
class does not oblige you to use its utilities, so the duplication persisted
next to the fix for it.

`messaging/transfers.py` holds `ack_stream` and `indexed_fetch` as module-level
functions instead, which makes using them the path of least resistance.
`Saga.extract_frame` / `extract_nav_frame` delegate there so there is one
implementation.

**A declarative `Step` DSL was considered and rejected.** The sagas' *control
flow* genuinely differs — `mow_path` branches on `skip_planning` and falls back
to `zone_hashs`, `map_saga` loops on device state via `find_incomplete_hashes`,
`edge_saga` is paced by a physical border walk that must not restart. Only the
mechanics repeat, not the flow. Encoding that as data means reinventing
branching and looping, with an escape hatch in every saga.

Deliberately *not* extracted: `map_saga` step 4 (resume + `addressed_hashes` +
drain + no-progress) and `mow_path`'s cover-path loop (transaction filtering +
batching). Both contain frame reception but are different algorithms around it.

## D3. Saga retry counts consecutive fruitless attempts, not total runs

`max_attempts` caps attempts that made no progress; any advance reported by
`progress()` resets the budget.

Whole-run restart was the wrong granularity for a protocol where the device
retransmits unacked frames — an interruption at frame 47 of 50 discarded 46
banked frames. The old design needed `MowPathSaga._budget_reset_granted`, a
one-shot flag whose only job was to suppress a reset that fired on every run and
made `max_attempts` meaningless. A flag that exists to suppress itself is the
clearest possible evidence the design was wrong; a value derived from state
simply stops changing when the device stalls.

## D4. Two protocol details that look like off-by-one bugs and are not

- Stream completion is `len(frames) >= total_frame`, **not**
  `current_frame == total_frame`. A retransmitted final frame can arrive while an
  earlier one is still missing, which would end the transfer with a hole.
- Duplicate frames are **re-acked**, not skipped. A retransmit means the device
  did not hear the previous ack. Matches `HashDataManager.setRegionalData`.

## D5. No `MQTTBaseTransport`

`AliyunMQTTTransport` and `MQTTTransport` share ~30 lines of envelope handling
and two constants. Their reconnect loops do not: Aliyun has bind-reply handling,
auth-refresh cycles and `AccountInUseError`; Mammotion has the creds-refresher
and give-up semantics. A base class would have to accommodate both credential
models to share very little — and D2 had already shown what happens to optional
shared machinery on a base class.

What was shared instead: `transport/envelope.py` (one `unwrap_envelope`, −94
lines) and reconnect constants hoisted into `base.py` as
`MQTT_RECONNECT_MIN_SEC` + `MQTT_RECONNECT_MAX_SEC_ALIYUN` /
`..._MAMMOTION`, side by side so the 60-vs-120 asymmetry reads as intentional
rather than as an accident in two unrelated modules.

**A bug the audit found:** `base64.b64decode` raises `binascii.Error`, a
`ValueError` subclass, which the old `except (KeyError, TypeError)` did not
catch. A corrupt payload escaped `_unwrap_envelope`, hit `_run`'s catch-all, and
**reconnected the transport** — one bad message dropped the MQTT connection. The
shared unwrap never raises.

`b64decode` is lenient by default (`validate=False` discards non-alphabet
characters). That behaviour is preserved and pinned by test rather than changed.

## D6. Transport dispatch helpers parse inside the guard, call outside it

The broad `except Exception` in the per-message-kind dispatch helpers used to
wrap the `await self.on_device_*(...)` **callback**, not just the parse — so
anything a downstream handler raised (`SessionExpiredError`, `AuthError`) was
logged at DEBUG and dropped. Five sites across the two transports. The callback
now runs outside the guard so exceptions reach `_run`, which owns the taxonomy.

## D7. No automatic password re-login, and therefore no rate limiters

Auth recovery was once spread across four layers with five independent
throttles (`MammotionHTTP._refresh_failed_at`,
`TokenManager._force_refresh_failed_at`, `._invoke_refresh_failed_at`,
`._aliyun_refresh_failures`, `AccountSession.relogin_failed_at`) plus a circuit
breaker. Every one existed to throttle an automatic password re-login that
`MammotionHTTP` could fire from any of ~15 decorated endpoints, bypassing all
the policy above it. That is the shape of the `oauth2/token` hammering Mammotion
reported.

`login_v2` remains, but only `MammotionClient.login_and_initiate_cloud` may
reach it. All automatic renewal is refresh-token based, or — for Aliyun — the
existing login's authCode chain via `connect_iot`. With no automatic re-login
there is nothing left to throttle, so all five throttles and the breaker were
deleted. `tests/unit/http/test_token_refresh.py` asserts the constraint against
the AST.

Fixed on the way through: `refresh_login()` was unconditionally Aliyun-only, so
it raised `ReLoginRequiredError("No Aliyun cloud gateway configured")` for every
post-2025 account; the pre-emptive `sign_out()` in `check_or_refresh_session`'s
2401 handler destroyed the Aliyun session before trying to rebuild it; and the
refresh lock hold time is now bounded at the call site rather than relying on a
`ClientSession` timeout that does not apply when the host supplies its own
session.

## D8. `/user/oauth/check` must not come back

`validate_login` ends in a real authenticated call (`get_user_device_list`)
rather than a local expiry check alone, because a token revoked server-side
keeps its `exp` weeks in the future and nothing computed locally can see it.

`/user/oauth/check` 404s on live accounts. Treating that as a rejection made
every restore refresh — spending the cached refresh token — and then re-login
anyway. `get_user_device_list` is used instead because it is known to exist and
the restore fetches it moments later regardless.

## D9. Failures are scoped and terminal; there are no retry timers

A rejected refresh token does not become valid by waiting, so retrying it only
adds load. Account-scoped rejection sets `reauth_required` and prompts the user;
transport-scoped sets `aliyun_unavailable` / `mqtt_unavailable` and gives up on
that transport alone, keeping the login and the account's other transport;
transient network errors set neither and propagate by type.

The HA side needed the same distinction. `_on_unrecoverable_auth_error` used to
raise `ConfigEntryAuthFailed()` from inside the callback — which pymammotion
invokes under `contextlib.suppress(Exception)`, so it was silently discarded and
**no reauth flow ever started**. And `async_refresh_login` treated every
`ReLoginRequiredError` as grounds for `ConfigEntryAuthFailed`, which would force
a reauth prompt and discard working credentials every time one cloud transport
died.

## D10. Reactive refreshes are deduplicated by access token

`refresh_invoke_token(stale_token=...)` compares the token the failed request
actually used against the live one and returns early if they differ. Without it,
a burst of commands that all 401 on the same dead token produces one refresh
*each* (serialized by the lock), and every refresh rotates the refresh token
server-side, so later rotations race earlier ones. Ported from the Android app's
`SpecialCodeIntercepter.refreshToken`, which guards identically.

## D11. Fakes live in one place per suite

`FakeMessage`, `FakeAsyncMessages`, `FakeMQTTClient` and `NetworkErrorClient`
were duplicated between `test_aliyun_mqtt.py` and `test_mammotion_mqtt.py` and
had already drifted — one copy of `FakeAsyncMessages` was documented as yielding
"one message" when it yields all of them. **Drift in a fake is worse than drift
in production code**: no type checker or failing test notices, it just silently
weakens every test built on it. They now live in `tests/unit/transport/_fakes.py`.

`_MqttAuthFailClient` in `tests/integration/test_transport_auth_cascade.py` is a
third copy, deliberately not migrated: `tests/integration` importing from
`tests/unit` is a worse smell than one duplicate. Revisit if a fourth appears.

## D12. Two queue/broker invariants that came from real deadlocks

- `DeviceCommandQueue` releases `_exclusive_active` in an **unconditional
  `finally`**, on cancellation and unhandled exception alike. Without it, a saga
  that raised before its cleanup ran blocked the device's queue forever.
- `DeviceMessageBroker` resolves pending futures **inside** `async with
  self._lock`. Lookup-then-resolve outside the lock let a late response race the
  timeout cleanup, calling `set_result` on an orphaned future — losing the
  response and blocking the next request for the same field.

## D13. `CloudTransport` sits between `Transport` and the two MQTT transports

`Transport` used to carry, on the shared base, the 12-hour send quota
(`_SEND_LIMIT`, `record_send`, `is_rate_limited`, `is_send_blocked`,
`seconds_until_send_available`, …), the terminal auth flags (`on_auth_failure`,
`mark_auth_failed`, `mark_unrecoverable_auth_failure`) and the four `thing/*`
message callbacks. `BLETransport` inherited all of it and referenced **none** of
it.

Two symptoms made the coupling visible rather than merely untidy:

- `BLETransport.send` still takes `iot_id` and `firmware_version` — parameters it
  ignores, carrying a `# noqa: ARG002 — Transport.send signature`.
- `Transport.is_usable` was defined as `not self._auth_failed and not
  self._unrecoverable_auth_failure`, so BLE *had* to override it to say anything
  at all. One wrong default plus a mandatory override, where three honest
  implementations belonged.

**Not solved with no-op stubs on BLE.** A `record_send` that does nothing and an
`is_rate_limited` hardcoded to `False` would preserve one flat interface at the
cost of making every caller's assumption unfalsifiable. It is the same trade D2
already lost.

`base.py` (597 → 404 lines) now holds only what a link of any kind has: the
message callback and its receive timestamping, `last_send_monotonic`, the error
window, the availability listeners, and the six abstract members.
`transport/cloud.py` holds the broker surface, plus `RATE_LIMIT_REMOVED_VERSION`
and the `MQTT_RECONNECT_*` constants that were also cloud-only.

**What the split found.** `ty` immediately flagged three call sites that had been
passing only because the members were on the base:
`handle.py` calling `set_rate_limited()` on a `Transport`, and `mqtt_loop.py`
calling `is_send_blocked` / `seconds_until_send_available` on one. All three now
narrow with `isinstance(..., CloudTransport)`. The `_send_marked` pre-flight in
particular was written as `transport.transport_type != TransportType.BLE` — a
string-tag test standing in for "is this a cloud transport", which existed only
because the real distinction had no type to express it.

`on_fatal_auth_error` was also unified. It was the one cloud callback never
hoisted to the base, so it was declared twice and had drifted: `Callable[[Exception],
...]` on `MQTTTransport` versus `Callable[[ReLoginRequiredError], ...]` on
`AliyunMQTTTransport`. A handler accepting only the narrow type cannot safely
serve a caller that may pass any exception, so the shared declaration takes
`Exception` and `MammotionClient._on_aliyun_fatal_auth` widened to match.

Test coverage moved with the members: the quota and auth-flag tests are now
`tests/unit/transport/test_cloud.py` against a `CloudTransport` stub, and
`test_base.py` gained `test_base_transport_has_no_cloud_surface`, which asserts
none of the sixteen moved members is reachable from a non-cloud transport — the
guard against re-adding one to the base by reflex.

## D14. User-initiated commands bypass the queue, not the cloud's 429

`Priority.EMERGENCY` existed from the start, documented as "estop, return-to-dock
— never dropped, skips TTL/transport gates", and had **zero callers** anywhere in
the library. Its own comment explained why it could never deliver on the name:

```python
# NOTE: EMERGENCY items skip the TTL and transport gates, but the processor is
# strictly sequential — an item enqueued while an EXCLUSIVE saga is mid-flight
# still waits for that saga's work() to return.  True e-stop preemption needs a
# direct send path, not this queue.
```

Ranking inside a single-consumer queue cannot preempt. `Priority.USER` and
`Priority.EMERGENCY` are therefore *direct-send* levels: `MammotionClient`
dispatches them on the caller's own task, and `DeviceCommandQueue.enqueue` raises
`ValueError` if handed one, so the old shape cannot come back by reflex.

**What a direct command still obeys.** Transport selection, BLE reconnect and the
whole fallback chain in `send_raw` are untouched — that is the point; only the
*waiting* is skipped, not the routing. Error handling is shared rather than
copied: the queue's gateway-timeout retry and its DEBUG/WARNING/exception
demotion buckets moved into `command_queue.execute_command`, which both paths
call. The single difference is `reraise`: the queue swallows because there is
nobody left to tell, a direct send propagates because someone is waiting. That
also flips the no-transport case — the queued path logs at DEBUG and returns,
while a direct command raises `NoTransportAvailableError`, since a person who
pressed a button cannot act on silence.

**Only the self-imposed limit yields.** `CloudTransport` had one fused
`is_rate_limited` covering two very different things. They are now separate:
`is_cloud_banned` (the broker answered 429 and `set_rate_limited()` started a
fixed 12 h timer) and `is_quota_exhausted` (our own 600-per-12 h rolling window).
`is_send_blocked(fw, user_initiated=True)` skips the second and honours the
first. A 429 is the server explicitly saying stop; pushing through it risks a
longer ban and is the same shape of behaviour as the `oauth2/token` hammering in
D7. The self-imposed budget is different in kind — it exists to pace *polling*
(`mqtt_loop._MQTT_POLL_INTERVAL` is "tuned for cloud quotas"), and a person
pressing a button should not be starved by our own poll schedule.

`send_user()` is a third metering policy over the same unmetered `_invoke`
primitive that `send()` and `send_heartbeat()` already sit on — so `_invoke`
became abstract on `CloudTransport`. It still calls `record_send()`: the window
has to reflect real traffic, or the next cadence decision is made on a lie.
No `user_initiated` parameter was added to `Transport.send()`, which would have
put a broker concern back on the base signature BLE already ignores (D13).

**The default stays `NORMAL`, but not for the reason first argued.** An earlier
draft of this entry claimed that because every command `mower_api.py` exposes is
user-initiated, defaulting to `USER` would leave the quota governing nothing.
That is wrong, and the counting is worth recording so it is not re-derived:

| what spends the budget | volume |
|---|---|
| `transfers.ack_stream` | one send **per received frame**, duplicates included — a single map fetch is easily hundreds |
| MQTT poll loop | one one-shot report every 5–60 min per device mode (48–144 per 12 h) |
| `auto_fetch` watchers | a whole map/plan saga per qualifying state change |
| host periodic refresh | several reads per update cycle |

None of those is ever `Priority.USER`. Human button presses are noise against
that traffic, so exempting them does not meaningfully loosen the budget.

The real reason to keep `USER` selective is **ordering, not budget**: it decides
what may jump a running saga, and that is a property of the command, not of who
sent it. The rule is *does the command's value decay* — is running late worse
than not running at all? Manual movement, dock/undock, blades on/off and cancel
decay: a nudge delivered three minutes after the button press is the wrong nudge.
Settings persist, so a blade height or light toggle queued behind a map sync
still ends up correct and gains nothing from preempting it.

The residual budget caution is much narrower than first claimed: because `USER`
skips the self-imposed window, an automation hammering a marked command reaches
the cloud's real 429 sooner than it otherwise would. That argues against blanket
`USER` inside a generic wrapper — it does not argue against marking genuine UI
actions.

**A rejected send must not look like a successful one.** Two swallows were removed
so the direct path's `reraise=True` means something. `send_raw` used to catch
`TooManyRequestsException`, arm `set_rate_limited()` and return normally — so a
command the cloud had explicitly refused reported success, and the host's
`api_limit_exceeded` handler was unreachable. It now arms the ban and re-raises;
the queue still absorbs it via `execute_command`'s WARNING bucket, so only the
direct path is louder. The same reasoning had already retired the
`TransportRateLimitedError` swallow.

Both errors have to be catchable on the host side, which is a real constraint: a
`TransportRateLimitedError` escaping into HA-Luba matched none of its except
lists (`COMMAND_EXCEPTIONS` is Bleak/timeout/no-transport only) and would have
surfaced as a raw traceback. Its three send chokepoints now catch it alongside
`TooManyRequestsException` under one `api_limit_exceeded` message — the cloud's
429 and the ban it leaves behind are the same thing to a user.

**`AliyunMQTTTransport.send` was gated on the wrong predicate.** It checked bare
`is_rate_limited` while `MQTTTransport.send`, `send_user` and the `_send_marked`
pre-flight all check `is_send_blocked(firmware_version)`, so a device on
quota-free firmware passed the handle's gate and was then refused by the
transport. Harmless today — every Aliyun device predates
`RATE_LIMIT_REMOVED_VERSION`, so the exemption never fires — but the layers
disagreeing is the bug, not the current outcome, and `_send_marked`'s docstring
claims they cannot.

`send_command_and_wait` gained the same parameter, but note it never used the
queue in the first place — it drives `broker.send_and_wait` directly — so the
quota exemption is the only thing that changes there.
