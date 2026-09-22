# Decision Record

Why the architecture is shaped the way it is. Each entry names a decision that
was made against a real alternative and states the reason, because the reason is
not recoverable from the code and someone will otherwise re-propose the rejected
option. `docs/architecture.md` is the map; `CLAUDE.md` carries the rules;
`docs/backlog.md` lists what is still open.

Entry numbers are stable — `CLAUDE.md` and code docstrings cite them.

---

## D1. The pre-refactor stack was deleted, not shimmed

`mammotion/devices/*`, `mqtt/*` (`AliyunMQTT`, `MammotionMQTT`,
`MQTTConnectionPool`), `homeassistant/rtk_api.py`, `utility/periodic.py` and
`transport/watchdog.py` are gone. Nothing in the layered architecture called
them, and a compatibility shim would have meant maintaining two device models
against one protocol. The entry point is `pymammotion.client.MammotionClient`.

## D2. Saga mechanics are free functions, not base-class helpers

`messaging/transfers.py` holds `ack_stream`, `indexed_fetch` and frame
extraction as module-level functions. They were once optional helpers on the
`Saga` base and one saga in seven used them — inheriting a class does not oblige
you to use its utilities, so nine hand-rolled copies persisted next to the fix.
A free function is the path of least resistance.

**Rejected:** a declarative `Step` DSL. The sagas' *control flow* genuinely
differs (`mow_path` branches and falls back, `map_saga` loops on device state,
`edge_saga` is paced by a physical walk). Only the mechanics repeat; encoding the
flow as data means reinventing branching and looping with an escape hatch in
every saga. `map_saga`'s resume/drain step and `mow_path`'s cover-path loop are
deliberately left as different algorithms around shared frame reception.

## D3. Saga retry counts consecutive fruitless attempts, not total runs

`max_attempts` caps attempts that made no progress; any advance reported by
`progress()` resets the budget. The device retransmits unacked frames, so
whole-run restart was the wrong granularity: an interruption at frame 47 of 50
threw away 46 banked frames. The previous design needed a one-shot flag whose
only job was to suppress a budget reset that fired on every run — a flag that
exists to suppress itself is the tell that the design is wrong.

## D4. Two protocol details that look like off-by-one bugs and are not

- Stream completion is `len(frames) >= total_frame`, **not**
  `current_frame == total_frame`. A retransmitted final frame can arrive while an
  earlier one is still missing.
- Duplicate frames are **re-acked**, not skipped. A retransmit means the device
  did not hear the previous ack (matches `HashDataManager.setRegionalData`).

## D5. No `MQTTBaseTransport`

The two MQTT transports share ~30 lines of envelope handling and two constants;
their reconnect loops share nothing (Aliyun has bind replies, auth-refresh
cycles and `AccountInUseError`; Mammotion has the creds refresher and give-up
semantics). A base class would have to accommodate both credential models to
share very little, and D2 already showed what happens to optional shared
machinery on a base. What is shared lives in `transport/envelope.py`
(`unwrap_envelope`, which never raises — a corrupt base64 payload once escaped
the old guard and reconnected the transport) and as `MQTT_RECONNECT_*`
constants on `CloudTransport`, side by side so the 60 s vs 120 s asymmetry reads
as intentional. `b64decode` stays lenient (`validate=False`); a test pins it.

## D6. Dispatch helpers parse inside the guard and call outside it

The per-message-kind helpers in both MQTT transports catch parse errors around
the decode only. The `await self.on_device_*(...)` callback runs outside that
guard, so an exception raised downstream (`SessionExpiredError`, `AuthError`)
reaches `_run`, which owns the error taxonomy, instead of being logged at DEBUG
and dropped.

## D7. No automatic password re-login, and therefore no rate limiters

Auth recovery once had five independent throttles and a circuit breaker across
four layers, every one of them there to slow an automatic password re-login that
`MammotionHTTP` could fire from any of ~15 endpoints. That is the shape of the
`oauth2/token` hammering Mammotion reported. `login_v2` is now reachable only
from `MammotionClient.login_and_initiate_cloud`; every automatic renewal uses a
refresh token or, for Aliyun, the existing login's authCode chain
(`connect_iot`). With nothing to throttle, the throttles were deleted.
`tests/unit/http/test_token_refresh.py` asserts the constraint against the AST.

## D8. `/user/oauth/check` must not come back

`validate_login` ends in a real authenticated call because a token revoked
server-side keeps its `exp` weeks in the future. The call is
`get_user_device_list`, which is known to exist and is fetched moments later
anyway. `/user/oauth/check` 404s on live accounts, and treating that as a
rejection made every restore spend the refresh token and re-login regardless.

## D9. Failures are scoped and terminal; there are no retry timers

A rejected refresh token does not become valid by waiting. An account-scoped
rejection sets `reauth_required` and prompts the user; a transport-scoped one
sets `aliyun_unavailable` / `mqtt_unavailable` and gives up on that transport
alone, keeping the login and the other transport; a transient network error sets
neither and propagates by type. The host has to keep the same distinction: a
transport failure must not raise `ConfigEntryAuthFailed`, or one dead cloud
transport discards working credentials. And `on_unrecoverable_auth_error` is
invoked under `contextlib.suppress(Exception)`, so raising from inside it does
nothing — the host must schedule its reauth flow instead.

The fresh login applies the same scoping to Aliyun setup, matching the app
(`DeviceManager.getAliDeviceListCheckLogin`): it is attempted whenever the login
carries an authorization code, and a failure costs only the Aliyun devices. It
propagates only when the account has no Mammotion devices to fall back on.

## D10. Reactive refreshes are deduplicated by access token

`refresh_invoke_token(stale_token=...)` returns early when the token the failed
request used is no longer the live one: another caller already refreshed. Without
it a burst of 401s on one dead token produces one refresh each, and every refresh
rotates the refresh token server-side, so later rotations race earlier ones.
Ported from the Android app's `SpecialCodeIntercepter.refreshToken`.

## D11. Fakes live in one place per suite

The MQTT client fakes live in `tests/unit/transport/_fakes.py`. Two copies had
drifted — one documented as yielding "one message" while yielding all of them —
and drift in a fake is worse than drift in production code because nothing
notices; it silently weakens every test built on it. The integration tier keeps
its own `_MqttAuthFailClient` because `tests/integration` importing from
`tests/unit` is the worse smell. Revisit if a third copy appears.

## D12. Two queue/broker invariants that came from real deadlocks

- `DeviceCommandQueue` releases `_exclusive_active` in an unconditional
  `finally`. A saga that raised before its cleanup once blocked the device's
  queue forever.
- `DeviceMessageBroker` resolves pending futures inside `async with self._lock`.
  Lookup-then-resolve outside it let a late response race the timeout cleanup and
  `set_result` an orphaned future, losing the response and blocking the next
  request for that field.

## D13. `CloudTransport` sits between `Transport` and the two MQTT transports

`Transport` once carried the send quota, the terminal auth flags and the four
`thing/*` callbacks; `BLETransport` inherited all of it and used none. The
symptoms: `BLETransport.send` takes `iot_id` and `firmware_version` it ignores,
and `Transport.is_usable` was computed from auth flags BLE had to override to say
anything. `transport/cloud.py` now holds the broker surface; `base.py` holds
only what any link has (message callback, activity timestamps, error window,
availability listeners, the abstract members).

**Rejected:** no-op stubs on BLE to keep one flat interface. A `record_send`
that does nothing makes every caller's assumption unfalsifiable — the trade D2
already lost. Callers that need the cloud surface narrow with
`isinstance(..., CloudTransport)`; the split immediately exposed three sites that
had been calling cloud members on a `Transport`, one via a
`transport_type != BLE` string test standing in for the missing type.
`test_base_transport_has_no_cloud_surface` guards against re-adding a member to
the base by reflex.

## D14. User-initiated commands bypass the queue, not the cloud's 429

`Priority.USER` and `Priority.EMERGENCY` are *direct-send* levels: the client
dispatches them on the caller's task and `DeviceCommandQueue.enqueue` raises
`ValueError` if handed one. Ranking inside a single-consumer queue cannot
preempt — an item behind an in-flight saga waits for its `work()` however it
sorts — and `EMERGENCY` had sat in the queue with zero callers because of it.
Routing is unchanged (`send_raw`, transport selection, BLE fallback); only the
waiting is skipped. Error classification is shared through
`command_queue.execute_command`; the one difference is `reraise`, so a direct
send propagates `NoTransportAvailableError` where the queue logs and returns.

**Two block sources, treated differently.** `is_cloud_banned` (the broker
answered 429, 12 h fixed timer) is honoured by everyone — pushing through it is
the `oauth2/token` shape again. `is_quota_exhausted` (our own 600-per-12 h
window) exists to pace *polling* and is skipped for `user_initiated=True` via
`CloudTransport.send_user()`, which still calls `record_send()` so the window
reflects real traffic. No `user_initiated` parameter was added to
`Transport.send()` (D13).

**The default stays `NORMAL`, for ordering rather than budget.** Library traffic
(per-frame acks, poll loops, auto-fetch sagas, host refreshes) spends the budget;
button presses are noise against it, so exempting them changes nothing there.
`USER` decides what may jump a running saga, and the rule is *does the command's
value decay*: manual movement, dock/undock, blades and cancel do (a nudge three
minutes late is the wrong nudge); a blade height or light toggle persists and
gains nothing from preempting a map sync. Blanket `USER` inside a generic
wrapper would let an automation reach the real 429 sooner.

**A rejected send must not look like a successful one.** `send_raw` used to
swallow `TooManyRequestsException` and `TransportRateLimitedError`, so a command
the cloud refused reported success and the host's `api_limit_exceeded` handler
was unreachable. Both now propagate; the queue absorbs them in its WARNING
bucket, the direct path surfaces them, and HA-Luba catches both under one
message.
