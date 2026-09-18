"""Mode-set policy derived from ``WorkMode``.

Not protocol constants — decisions this library makes about when to send and
what counts as an active job.  The matching cadence *intervals* live with the
loops that read them (``pymammotion/device/mqtt_loop.py``, ``ble_loop.py``).
"""

from __future__ import annotations

from pymammotion.utility.constant.device_enums import WorkMode

#: Modes where an unsolicited poll is unwelcome: map planning/editing, anything
#: rewriting device storage (OTA, backup, restore), and ``MODE_SLEEPING``.
NO_REQUEST_MODES = (
    WorkMode.MODE_JOB_DRAW,
    WorkMode.MODE_OBSTACLE_DRAW,
    WorkMode.MODE_CHANNEL_DRAW,
    WorkMode.MODE_ERASER_DRAW,
    WorkMode.MODE_AUTO_ERASER_DRAW,
    WorkMode.MODE_CORRIDOR_DRAW,
    WorkMode.MODE_UPDATING,
    WorkMode.MODE_EDIT_BOUNDARY,
    WorkMode.MODE_LOCK,
    WorkMode.MODE_MANUAL_MOWING,
    WorkMode.MODE_SLEEPING,
    WorkMode.MODE_BACKING_UP,
    WorkMode.MODE_RECOVERY,
)

#: sys_status values that indicate a mowing job is active (moving, returning, or
#: paused mid-job).  Used to: (1) preserve mow-path / zone caches that must not
#: be cleared until the job ends; (2) pick the short keep-alive / watchdog
#: interval; (3) detect the job-done transition in maintenance coordinator.
MOWING_ACTIVE_MODES: frozenset[int] = frozenset(
    {
        WorkMode.MODE_WORKING.value,
        WorkMode.MODE_RETURNING.value,
        WorkMode.MODE_PAUSE.value,
        WorkMode.MODE_CHARGING_PAUSE.value,
    }
)
