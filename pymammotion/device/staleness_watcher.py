"""MapStalenessWatcher — auto-triggers map/plan re-fetch on data invalidation."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.state.device_state import DeviceSnapshot
    from pymammotion.transport.base import Subscription

_logger = logging.getLogger(__name__)

_REFETCH_COOLDOWN_SECONDS = 60.0


class MapStalenessWatcher:
    """Watches device state for map/plan staleness and auto-enqueues refetch sagas.

    Subscribes to the device's state_changed bus. When the snapshot shows
    missing hash data or stale plans, it calls the provided trigger callbacks
    after a cooldown period (to avoid re-triggering during an active saga).
    """

    def __init__(
        self,
        *,
        on_maps_stale: Callable[[], Awaitable[None]],
        on_plans_stale: Callable[[], Awaitable[None]],
        is_saga_active: Callable[[], bool],
        cooldown: float = _REFETCH_COOLDOWN_SECONDS,
    ) -> None:
        """Initialise the watcher with callbacks and cooldown settings."""
        self._on_maps_stale = on_maps_stale
        self._on_plans_stale = on_plans_stale
        self._is_saga_active = is_saga_active
        self._cooldown = cooldown
        self._last_map_trigger: float = 0.0
        self._last_plan_trigger: float = 0.0
        self._subscription: Subscription | None = None

    async def on_state_changed(self, snapshot: DeviceSnapshot) -> None:
        """Check for map/plan staleness on state change."""
        now = time.monotonic()
        device = snapshot.raw

        # Don't trigger during an active saga
        if self._is_saga_active():
            return

        # Check map staleness
        if device.map.missing_hashlist() and (now - self._last_map_trigger) > self._cooldown:
            self._last_map_trigger = now
            _logger.info("MapStalenessWatcher: map data invalidated, triggering re-fetch")
            try:
                await self._on_maps_stale()
            except Exception:  # noqa: BLE001
                _logger.warning("MapStalenessWatcher: map refetch trigger failed", exc_info=True)

        # Check plan staleness
        if device.map.plans_stale and (now - self._last_plan_trigger) > self._cooldown:
            self._last_plan_trigger = now
            _logger.info("MapStalenessWatcher: plans stale, triggering re-fetch")
            try:
                await self._on_plans_stale()
            except Exception:  # noqa: BLE001
                _logger.warning("MapStalenessWatcher: plan refetch trigger failed", exc_info=True)

    def stop(self) -> None:
        """Cancel the state-change subscription."""
        if self._subscription is not None:
            self._subscription.cancel()
            self._subscription = None
