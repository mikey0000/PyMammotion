# Testing constitution

The rules every test in this repository follows, and that every agent writing a
test here obeys. `docs/architecture.md` is the map of the library; this is the
map of `tests/`.

The suite exists to make a regression impossible to merge quietly. A test that
passes whether or not the behaviour it names is intact is worse than no test:
it costs a run every commit and buys nothing, and it tells the next reader the
behaviour is covered. Most of the rules below are that one rule, applied.

Two enforcement layers back this document:

- `tests/meta/test_conventions.py` — the mechanical rules, asserted by the
  suite itself, with a frozen baseline of pre-existing offenders that may only
  shrink.
- the `test-reviewer` agent (`.claude/agents/test-reviewer.md`) — the
  judgement-shaped rules, run automatically against every test an agent writes
  (see [Automated review](#automated-review)).

---

## 1. Tiers

Three tiers, distinguished by what they are allowed to touch. Pick the cheapest
one that can observe the behaviour.

| Tier | Location | May touch | Must not touch | Budget |
|---|---|---|---|---|
| **unit** | `tests/unit/` | one module, its real collaborators, in-process doubles | sockets, Bluetooth, the real clock, the filesystem outside `tmp_path`, `tests/fakeserver` | < 100 ms/test |
| **integration** | `tests/integration/` | several real components wired together; `tests/fakeserver` over loopback | the real Mammotion cloud, real hardware | < 2 s/test |
| **live** | `tests/live/` | a real account and/or a real mower | — | unbounded |

**unit** is the default. Reach for **integration** only when the behaviour is
the *wiring* — a message crossing a transport, a credential restore driving
three objects, a saga completing against a broker. Reach for **live** only to
confirm the protocol matches the real device; live tests are marked `live`,
skip silently when their env vars are absent, and are never a gate on anything.

A unit test that needs `tests/fakeserver` is an integration test in the wrong
directory. Move it, don't loosen the rule.

---

## 2. Layout and file names

```
tests/
├── __init__.py            makes `tests.*` the one import root
├── conftest.py            global fixtures only — autouse safety nets
├── _helpers.py            cross-tier builders (rare; prefer a package-local one)
├── data/                  static payloads: *.json, *.geojson, captured frames
│                          (pending: today they sit in tests/fixtures/ — §13)
├── meta/                  tests about the tests (this document, asserted)
├── unit/                  mirrors pymammotion/ package for package
│   └── <package>/
│       ├── __init__.py
│       ├── _helpers.py    make_* builders for this package
│       ├── _fakes.py      hand-written fake classes for this package
│       └── test_<module>.py
├── regression/            cross-module defect pins (create it when the first one lands)
├── integration/
│   └── fake_cloud/        driven against tests/fakeserver
├── live/
└── fakeserver/            the fake Mammotion cloud — production-grade code, not a test
```

- **`tests/unit/` mirrors the package.** A test for
  `pymammotion/device/handle.py` lives at `tests/unit/device/test_handle.py`.
  One test module per source module; the mirror is what makes "is this already
  covered?" answerable by looking at one path.
- **Every test directory has an `__init__.py`.** Without it two directories may
  not share a test-module basename and `tests.*` imports resolve twice.
- **Split by concern, never by number.** When a test module passes ~600 lines,
  split it into `test_<module>_<concern>.py` —
  `test_handle_transport_selection.py`, not `test_handle_2.py`. The concern
  must be a real seam in the module, and the base `test_<module>.py` keeps
  whatever doesn't belong to a named concern.
- **A defect-shaped filename is a smell.** `test_broker_late_response_race.py`
  reads as a bug report, not as a unit of the codebase. If the defect belongs
  to one module, its pin belongs in that module's test file (see §7); if it
  spans modules, it belongs in `tests/regression/`.
- **Tests live under `tests/`.** A `test_*.py` at the repo root is scratch: a
  bare `pytest` collects it, it has no tier and no review. Move it into a tier
  or delete it. (`test_svg_implementation.py`, `generate_geojson_test.py` and
  `final_svg_test.py` are currently sitting there, untracked.)
- **No test data inline past a few lines.** Captured frames, JSON payloads and
  GeoJSON go in `tests/data/`, loaded through a helper, never pasted into a
  test module. The `tests/fixtures/` directory is the legacy of ignoring this
  and is folding into `tests/data/` (§13).

---

## 3. Test names

```python
def test_<subject>_<expected behaviour>[_when_<condition>]() -> None:
```

`test_send_raises_when_the_device_is_offline`, not `test_send_offline`, not
`test_offline_2`, and never `test_it_works`. The name is the failure report the
CI log shows; it should say what broke without opening the file.

Every test module carries a docstring saying what surface it covers and any
constraint a reader needs before editing it. A test function gets a docstring
only when the name cannot carry the *why* — the non-obvious setup, the reason a
value matters, or the defect a regression pins (§7). Do not restate the name.

---

## 4. Fixtures, builders and where shared code lives

Two mechanisms, and they are not interchangeable:

- **`@pytest.fixture`** for anything with a lifecycle: something to set up and
  tear down, an event loop resource, a `tmp_path`-backed file, a patch that
  must be undone. Scope it as narrowly as it can go (`function` unless proven
  otherwise) and yield.
- **A plain `make_<thing>()` builder** for anything that is just construction.
  Builders keep call sites terse and greppable, they take keyword overrides,
  and they compose — three fixtures that differ by one field should be one
  builder with a default.

Placement, in order of preference:

1. **In the test module** — used by that module only.
2. **`tests/unit/<package>/_helpers.py`** (builders) or **`_fakes.py`**
   (hand-written fake classes) — the moment a second module in the package
   needs it. Two modules defining `_make_handle` is the failure this rule
   exists to stop; the copies drift, and nothing type-checks or fails to warn
   you.
3. **`tests/_helpers.py`** — needed across tiers.
4. **`tests/conftest.py`** — only for genuinely global, usually autouse,
   safety nets (the BLE-polling suppressor is the model: it protects every test
   in the suite from a background loop).

Naming: builders are `make_<thing>()`, public within the test package — no
leading underscore, because they are imported by name from other modules. A
leading underscore means "this module only". One builder per concept per
package, a superset of what its callers need, documented where a default is
load-bearing (`make_mock_transport`'s explicit `charge_state = 0` is the
canonical example: `int(MagicMock())` is `1`, which silently changes a device
mode).

Do not add a `conftest.py` to a package just to hold builders. A conftest
fixture is invisible at the call site; an imported builder is not.

---

## 5. Test doubles

Prefer, in this order, and justify every step down:

1. **The real object.** Protobuf messages, dataclasses, enums, `MowingDevice`,
   `DeviceHandle`, the state reducer, the queue — all constructible in-process
   in microseconds. Mocking one of these means the test no longer knows whether
   the real thing still has that attribute.
2. **A hand-written fake** in `_fakes.py` — for a protocol that would otherwise
   do I/O (the aiomqtt client, bleak, an HTTP session). A fake has a real
   implementation you can read and assert against, and it fails loudly when the
   interface it stands in for changes shape.
3. **`unittest.mock`** — at the process boundary, or to observe a callback.

Rules for the third:

- **Spec every mock.** `create_autospec(Cls, instance=True)`,
  `MagicMock(spec=Cls)`, or `patch.object(Cls, "method", autospec=True)`. A
  bare `MagicMock()` answers every attribute truthily forever: rename the
  method under test and the assertion still passes.
- **Never mock the unit under test.** If the test constructs a `MagicMock` and
  then asserts on that mock's own configured behaviour, it is asserting on its
  own setup.
- **`patch.object(Cls, "name")` over `patch("dotted.string.path")`.** The
  attribute form is checked by the import; the string form silently no-ops when
  the path moves.
- **Assert on outcomes, not on plumbing.** `assert handle.state.online is False`
  beats `mock.on_state.assert_called_once()`. Call assertions are correct only
  when the *call itself* is the contract — "does not send to an offline device"
  is precisely `send.assert_not_awaited()`, and that is a legitimate use.
- **One mock per boundary, configured once.** If a test needs six mocks to
  stand up, the unit has six collaborators and the test is telling you
  something about the design; say so in review rather than growing the setup.

---

## 6. Time, sleeping and async determinism

The suite must produce the same result on a loaded CI runner as on an idle
laptop. Nothing in `tests/unit/` may depend on wall-clock progress.

- **Never `time.sleep()`.** Anywhere, in any tier.
- **`await asyncio.sleep(<literal>)` is not a synchronisation primitive.**
  `await asyncio.sleep(0.15)` means "I hope the other task got there." It is a
  flake on a busy runner and 150 ms of dead time on every run. Three helpers in
  `tests/_helpers.py` cover every case, and between them they are the only
  definitions in the suite allowed to call `asyncio.sleep` with a non-zero
  argument:
  - **`wait_until(predicate)`** — the default. Wait on *the thing the test then
    asserts*, not on a proxy for it: `wait_until(lambda: received)` before
    `assert received == [payload]`. It returns the moment the condition holds,
    so it is faster than the sleep it replaces and only spends its timeout when
    something is genuinely broken. For a *negative* assertion, wait for the
    work to have happened and then assert it had no effect — otherwise "never
    sent" just means "not sent yet".
  - **`let_others_run()`** — inside a stub that must stay in a critical section
    long enough for an unsynchronised caller to overlap it. Spends loop turns,
    not wall-clock, and keeps the test's ability to tell a working lock from a
    missing one.
  - **`advance_real_time(seconds)`** — the rare case where the passage of time
    *is* the stimulus: a debounce window that must genuinely age, or proving
    that nothing further happens over a window. Naming it keeps those honest
    and greppable instead of hiding among the banned sleeps.

  Otherwise synchronise on the real thing: an `asyncio.Event` the code sets,
  `await asyncio.wait_for(future, TIMEOUT)`, `await queue.join()`, `await task`,
  or `await asyncio.sleep(0)` for exactly one deterministic loop turn.
- **Freeze the clock.** Anything reading `time.time()`, `time.monotonic()`, or
  computing an expiry uses `time_machine.travel(..., tick=False)` (a dev
  dependency) or an explicitly injected clock. Never assert on elapsed real
  time, and never write a test whose pass depends on how long the assertions
  above it took.
- **Bound every wait.** Any `await` that could hang is wrapped in
  `asyncio.wait_for` with a named module-level constant, so a broken test
  fails in a second rather than sitting until `faulthandler_timeout` (120 s)
  dumps every thread.
- `asyncio_mode = "auto"` is set: **do not decorate tests with
  `@pytest.mark.asyncio`.** `async def test_...` is enough.
  `pytest.mark.asyncio(loop_scope="session")` is a different thing — it pins the
  loop scope, the fake-cloud suites need it, and it stays.

---

## 7. Regression tests

A regression test is not a location, it is a contract:

1. **It failed before the fix.** Write it against the broken code and watch it
   fail. A regression test authored after the fix and never seen red is a
   restatement of the implementation.
2. **Its docstring records the defect** — what the code did, what it should
   have done, and (when non-obvious) how the defect could be reached. Not the
   diff that fixed it; the behaviour that was wrong.
3. **It is named for the behaviour, not the ticket.** `test_from_cache_does_not_mutate_the_callers_cache`,
   not `test_issue_412`.
4. **It is marked `@pytest.mark.regression`** so the set is enumerable.
5. **It lives with the module it pins** — `tests/unit/<package>/test_<module>.py`
   — unless it pins an interaction no single module owns, in which case
   `tests/regression/`.

`tests/unit/test_review_invariants.py` is the model for the docstring: each
test states the invariant, then states what went wrong when it was not
asserted anywhere.

---

## 8. Assertions and isolation

- **One behaviour per test.** Several `assert`s are fine when they describe one
  outcome; two unrelated outcomes are two tests.
- **Give a non-obvious assertion a message.** `assert len(subs) == 1, f"expected one subscription for dev1, got {len(subs)}"`.
  The message is what a future reader sees in CI without the source.
- **Assert on logs only when the log is the contract** (a deliberate warning, a
  debug line a host depends on), via `caplog` scoped to the logger name.
  Otherwise log text is free to change.
- **No test depends on another test, or on order.** No module-level mutable
  state shared between tests, no writing into `tests/data/`.
- **`monkeypatch` for env vars and attributes**, so teardown is automatic;
  `tmp_path` for files. Never touch `~`, never write into the repo.
- **Nothing in the suite reaches the network.** Not even to fail fast: a DNS
  timeout in CI is indistinguishable from a bug.
- **Parametrize instead of copy-pasting**, with `ids=` when the parameter does
  not print legibly. But do not parametrize across behaviours — a parameter
  that flips which assertion matters is two tests.
- **Banned outright:** `print()`, `if __name__ == "__main__":` runners,
  `sys.exit`, commented-out tests, `@pytest.mark.skip`/`xfail` without a reason
  string naming the blocker.

---

## 9. Reaching into privates

Tests may touch a private attribute when there is no public way to observe the
state — `handle._pending`, `manager._handle_subscriptions`. The suite does this
a lot, and much of it is legitimate.

It stops being legitimate when the test *sets up* through privates. Building a
client by assigning `_account_registry`, `_device_registry` and `_inbound` by
hand is a builder's job (`tests/_helpers.py::make_bare_client`), done once, so
that a constructor change breaks one place instead of forty. If you are about
to poke a private in setup, look for the builder first; if there isn't one,
write it in `_helpers.py`.

If you need a private to *assert*, ask once whether the library should expose
it — HA consumes this library through the same public surface, so a missing
observable is usually a real gap (`docs/architecture.md`, dependency
direction).

---

## 10. What must be tested

- **Every bug fix ships with a regression test** meeting §7.
- **Every new branch in a send path, gate, or state transition** gets a test —
  these are the places where a silent regression costs a user their mower.
- **Every invariant this repo states in prose** (`CLAUDE.md`, `docs/decisions.md`)
  is fair game to assert; several already are (`tests/unit/utility/test_layering.py`
  pins the import direction, `tests/unit/http/test_token_refresh.py` pins "no
  refresh path may reach `login_v2`" against the AST).
- **Not tested:** generated protobuf code, third-party behaviour, and getters
  that only return a field.

---

## 11. Running

```bash
uv run pytest tests/                      # everything; live tests skip silently
uv run pytest tests/unit -q               # the fast tier
uv run pytest tests/unit/device/test_handle.py::test_name
uv run pytest -m regression               # the defect pins
uv run pytest -m live                     # needs MAMMOTION_EMAIL / MAMMOTION_PASSWORD
uv run pytest tests/meta                  # the conventions in this document
```

`uv run pytest tests/` is a pre-commit hook, so a red suite blocks the commit.
Activate `.venv` first if `uv run` complains.

---

## 12. Automated review

**Every test an agent writes or modifies is reviewed by the `test-reviewer`
agent before the work is reported complete.** Not "should be" — the work is not
done until it has happened.

Mechanically:

- A `PostToolUse` hook on `Write`/`Edit` under `tests/` queues the touched file
  and reminds the session (`.claude/hooks/test_review_gate.py`).
- A `Stop` hook refuses the first stop attempt while the queue is non-empty,
  listing the unreviewed files.
- Launching `test-reviewer` clears the queue.

A subagent's writes queue under the same session, so tests written by a
delegated agent are caught by the parent's stop, not lost.

The reviewer reads this document as its rubric, runs the tests it is reviewing,
and reports findings by severity. **Blocking** findings (a test that cannot
fail, a mock standing in for the unit under test, a wall-clock sleep, a
regression test never seen red) are fixed before the work is reported.
**Advisory** findings are reported to the user, not silently applied.

The author agent — not the reviewer — makes the fixes, then re-runs the tests.
A reviewer that rewrites the tests it reviews is just a second author.

---

## 13. Legacy debt

The rules above describe where the suite is going. `tests/meta/test_conventions.py`
carries a frozen baseline of the files that predate them. That baseline may
**shrink, never grow**: a new violation fails the suite, and fixing an old one
requires deleting its baseline entry (a meta-test asserts every entry is still
a genuine violation, so stale entries fail too).

Known debt, largest first:

| Debt | Count | Fix |
|---|---|---|
| 25 unit modules that mirror no source module | `tests/unit/` | §2 — rename to `test_<module>_<concern>.py`, or move to `tests/regression/` |
| 9 modules over the 600-line cap (`test_client.py` at 2045, `test_handle.py` at 1681) | `tests/unit/`, `tests/integration/` | §2 — split by concern |
| test data still under `tests/fixtures/` | 5 files | §2 — move to `tests/data/`, update the three loaders |

Paid down already, and now pinned at zero by `tests/meta/test_conventions.py`:
62 wall-clock sleeps (56 in the unit tier, 6 elsewhere), 127 redundant
`@pytest.mark.asyncio` decorators, 11 builders duplicated across modules, 632
divider comments, 69 unused imports and redefinitions, a `__main__` runner, and
`tests/fixtures.py` (pasted protobuf text that had not been valid Python since
it was committed, and that nothing imported).

Do not fix these in bulk as a side effect of unrelated work. Fix the ones your
change touches, delete their baseline entries, and leave the rest.
