# Triage Graph: mikey0000/PyMammotion

**Repository**: [mikey0000/PyMammotion](https://github.com/mikey0000/PyMammotion)  
**Stars**: 213  
**Language**: Python  
**Domain**: Robotic lawn mower IoT library (Mammotion Luba/Yuka devices)

## Scan Summary

- **Open Issues**: 5  
- **Open PRs**: 2 (both addressing issue #137)  
- **Competing PRs**: Yes (#136, #138 both fix login_v2)  
- **Selected Issue**: #130 (expose MQTT envelope timestamp)

## Issues Evaluated

### #137: login_v2 returns "Access denied" for shared accounts
- **Status**: Has 2 competing PRs (#136, #138)
- **Decision**: Skip — competing work already in progress
- **Hypothesis**: H1 (competing-pr)

### #132: Custom mowing patterns
- **Status**: Feature request, maintainer redirected to ESP32 project
- **Decision**: Skip — out of library scope, hardware layer required
- **Hypothesis**: N/A (external dependency)

### #130: MQTT envelope delivers stale field values ⭐ **SELECTED**
- **Status**: Maintainer engaged, clear implementation path
- **Community input**: Detailed field investigation from @alxlo with local patch
- **Maintainer response**: "I'll look to drop old messages based off this"
- **Follow-up**: Maintainer clarified business logic should handle staleness, library should expose timestamp
- **Smallest fix**: Yes — exposes `params.time` via property, no behavior change
- **Decision**: Implement as infrastructure addition
- **Hypothesis**: H2 (missing-infra)

### #109: Account without email raises exception
- **Status**: User found workaround, last update Sept 2025
- **Decision**: Skip — stale, workaround exists
- **Hypothesis**: N/A (stale)

### #6: Black formatting and pylinting
- **Status**: Partially done via Ruff, open-ended
- **Decision**: Skip — low priority housekeeping
- **Hypothesis**: N/A (meta)

## Implementation: Issue #130

### Problem
`sys.toapp_report_data` occasionally delivers stale field values due to cloud buffering. Messages can arrive 70+ minutes late. `LubaMsg.timestamp` is unreliable (firmware counter, not Unix time). The Aliyun envelope field `params.time` (Unix ms) reliably reflects generation time and survives buffering.

### Solution
Expose `params.time` on `DeviceHandle` so subscribers can detect/handle delayed delivery without patching the library.

**Changes**:
1. Store `params.time` in `DeviceHandle._last_mqtt_envelope_time_ms` when `on_device_event()` is called
2. Add public property `DeviceHandle.last_mqtt_envelope_time_ms` returning the stored value (0 if never set)
3. Add comprehensive test coverage in `tests/test_envelope_timestamp_exposure.py`

**Test coverage**:
- ✅ Timestamp accessible after event processing
- ✅ Defaults to 0 before any event
- ✅ Updates on each successive event
- ✅ Handles time=0 explicitly

**Verification**: All existing tests pass (`pytest tests/test_client.py` — 62/62 passed)

### Rationale
- Maintainer explicitly approved exposing the timestamp (not dropping messages in library)
- Minimal change: add property + private field, zero behavior modification
- Clean separation of concerns: library provides data, caller decides staleness policy
- Smallest actionable fix from available issues
- H2 (missing-infra): fills a diagnosed broken role (timestamp provenance for out-of-order detection)

## Hypothesis Mapping

- **H0 (docs)**: None applicable
- **H1 (competing-pr)**: #137 (skipped)
- **H2 (missing-infra)**: #130 ⭐ **selected**
- **H3 (edge-case-bug)**: None found
- **H4 (test-gap)**: None found
- **H5 (maintainer-blocked)**: None found
- **H6 (community-stalled)**: None applicable

## Artifacts

- **Branch**: `fix-expose-mqtt-envelope-timestamp`
- **Test file**: `tests/test_envelope_timestamp_exposure.py` (4 tests, all passing)
- **Modified files**:
  - `pymammotion/device/handle.py` (add property + field + extraction logic)
  - `tests/test_envelope_timestamp_exposure.py` (new file)

## Next Steps

1. ✅ Implementation complete
2. ✅ Tests passing (local pytest)
3. ⏳ Create PR (blocked per user request — "NEVER run gh pr create")
4. ⏳ Wait for maintainer review
5. ⏳ Address feedback if any
6. ⏳ Merge

**Status**: `triaged`, ready for drip queue.  
**PR creation**: Blocked by pipeline protocol — drip queue entry created, awaiting /ship invocation.
