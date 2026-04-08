"""Optional device readiness checking — ensures base-level data is present."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymammotion.data.model.device import MowingDevice

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadinessStatus:
    """Result of a readiness check."""

    is_ready: bool
    missing: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        """Format as human-readable string."""
        if self.is_ready:
            return "ready"
        return f"not ready — missing: {', '.join(self.missing)}"


class ReadinessChecker(ABC):
    """Abstract readiness checker. Subclass per device family."""

    @abstractmethod
    def check(self, device: MowingDevice) -> ReadinessStatus:
        """Check if the device has the minimum required data."""

    @abstractmethod
    def commands_to_fetch_missing(self, device: MowingDevice) -> list[str]:
        """Return command names needed to populate missing data.

        These are method names on MammotionCommand that should be called
        to fetch the missing information.
        """


class NoReadinessChecker(ReadinessChecker):
    """No-op readiness checker that always reports the device as ready."""

    def check(self, device: MowingDevice) -> ReadinessStatus:
        return ReadinessStatus(is_ready=True)

    def commands_to_fetch_missing(self, device: MowingDevice) -> list[str]:
        return []


class MowerReadinessChecker(ReadinessChecker):
    """Readiness checker for Luba mowers (Luba 1, Luba 2, Luba 3000)."""

    def check(self, device: MowingDevice) -> ReadinessStatus:
        """Check mower readiness — requires product key, report data, map, firmware."""
        missing: list[str] = []

        if not device.mower_state.product_key:
            missing.append("product_key")

        if device.report_data.dev.sys_status == 0 and device.report_data.dev.battery_val == 0:
            missing.append("report_data")

        if len(device.map.root_hash_lists) == 0:
            missing.append("map_hash_list")

        if not device.mower_state.swversion:
            missing.append("firmware_version")

        return ReadinessStatus(is_ready=len(missing) == 0, missing=missing)

    def commands_to_fetch_missing(self, device: MowingDevice) -> list[str]:
        """Return commands to fetch missing mower data."""
        status = self.check(device)
        commands: list[str] = []
        for item in status.missing:
            match item:
                case "product_key":
                    commands.append("get_device_product_model")
                case "report_data":
                    commands.append("get_report_cfg")
                case "firmware_version":
                    commands.append("get_device_version_main")
                # map_hash_list is handled by MapFetchSaga, not a simple command
        return commands


def get_readiness_checker(device_name: str) -> ReadinessChecker:
    """Return the appropriate readiness checker for the device type."""
    from pymammotion.utility.device_type import DeviceType

    if not DeviceType.is_swimming_pool(device_name) or not DeviceType.is_rtk(device_name):
        return MowerReadinessChecker()
    return NoReadinessChecker()
