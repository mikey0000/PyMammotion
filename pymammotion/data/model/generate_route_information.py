from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, NamedTuple

from pymammotion.data.model.hash_list import RESERVED_ECHO_OFFSET

if TYPE_CHECKING:
    from pymammotion.data.model.work import CurrentTaskSettings

logger = logging.getLogger(__name__)

#: ``NavReqCoverPath.task_settings_mode``: the app's basic/advanced task settings screen, not mower behaviour.
#: Always sent as advanced.
BASIC_TASK_SETTINGS = 0
ADVANCED_TASK_SETTINGS = 1


class PathOrderSettings(NamedTuple):
    """Operational settings decoded from the reserved/path_order bytes field.

    The APK encodes these as an 8-byte array via ``new String(bArr)`` and passes
    it as the ``reserved`` field on ``NavReqCoverPath``.  The device echoes the
    buffer with +10 on every byte; the values here have that offset removed.
    Byte layout (from WorkingOptionView / WorkSettingViewModel in the APK source):

      [0] edge_mode            — boundary laps (APK: border_mode)
      [1] obstacle_laps        — laps around obstacles (APK: mowing_laps_obs)
      [2] (not decoded)        — plan enable flag, 0 = enabled; see ``hash_list``
      [3] start_progress       — starting waypoint index
      [4] toward_mode          — toward/direction mode (Luba1); 0 for other types
      [5] device_tactics       — Yuka: mow/dump/edge combo 0–14; LubaPro: 8; others: 0
      [6] collect_grass_freq   — grass collection frequency (APK: collectGrassFrequency,
                                  defaults to 10 when not in dump mode)
      [7] reserved             — unused; the app sends 0, the device fills it in
    """

    edge_mode: int = 1
    obstacle_laps: int = 0
    start_progress: int = 0
    toward_mode: int = 0
    device_tactics: int = 0
    collect_grass_freq: int = 10
    reserved: int = 0


@dataclass
class GenerateRouteInformation:
    """Creates a model for generating route information and mowing plan before starting a job."""

    one_hashs: list[int] = field(default_factory=list)
    job_mode: int = 4  # taskMode
    job_version: int = 0
    job_id: int = 0
    speed: float = 0.3
    ultra_wave: int = 2  # touch no touch etc
    channel_mode: int = 0  # line mode is grid single double or single2
    channel_width: int = 25
    blade_height: int = 0
    path_order: str = ""
    toward: int = 0  # is just angle
    toward_included_angle: int = 0
    toward_mode: int = 0  # angle type relative etc
    edge_mode: int = 1  # border laps
    obstacle_laps: int = 1
    #: "Auto-reverse Mowing Direction", sent as byte 0 of the 32-byte ``NavReqCoverPath.auto_change_direction``
    #: (``reserved2``). Gate on ``DeviceType.supports_auto_change_direction``.
    auto_change_direction: int = 0
    #: The app's "Edge Coverage": its switch writes only 0.0 or 0.5 (app default 0.5), no unit; any float passes.
    #: A modify re-sends it, so leaving it 0.0 turns it off. Gate on ``DeviceType.supports_ride_boundary_distance``.
    ride_boundary_distance: float = 0.0

    @classmethod
    def from_current_task_settings(cls, settings: CurrentTaskSettings) -> GenerateRouteInformation:
        """Build a :class:`GenerateRouteInformation` from a received :class:`CurrentTaskSettings`.

        ``CurrentTaskSettings`` arrives via ``bidire_reqconver_path`` and
        describes the task the device is currently running.  This helper maps
        it back into the command-shape used to start a new route, which is
        useful for re-issuing or cloning an existing job.

        Field mapping:

        - ``job_id``, ``job_mode``, ``edge_mode``, ``channel_width``,
          ``ultra_wave``, ``channel_mode``, ``toward``, ``speed``,
          ``toward_mode``, ``toward_included_angle`` — direct copy.
        - ``auto_change_direction`` — 1 when reported on, else 0
        - ``ride_boundary_distance`` — direct copy
        - ``job_ver`` → ``job_version``
        - ``knife_height`` → ``blade_height``
        - ``zone_hashs`` → ``one_hashs`` (copied, not aliased)
        - ``reserved`` → ``path_order`` — additionally decoded via
          :meth:`decode_path_order` so ``obstacle_laps`` surfaces as a
          top-level field on the returned instance.
        """
        decoded = cls.decode_path_order(settings.reserved)
        return cls(
            one_hashs=list(settings.zone_hashs),
            job_mode=settings.job_mode,
            job_version=settings.job_ver,
            job_id=settings.job_id,
            speed=settings.speed,
            ultra_wave=settings.ultra_wave,
            channel_mode=settings.channel_mode,
            channel_width=settings.channel_width,
            blade_height=settings.knife_height,
            path_order=cls.normalise_path_order(settings.reserved),
            toward=settings.toward,
            toward_included_angle=settings.toward_included_angle,
            toward_mode=settings.toward_mode,
            edge_mode=settings.edge_mode,
            obstacle_laps=decoded.obstacle_laps,
            auto_change_direction=int(bool(settings.auto_change_direction)),
            ride_boundary_distance=settings.ride_boundary_distance,
        )

    @staticmethod
    def normalise_path_order(path_order: str) -> str:
        """Return a device-echoed ``reserved`` buffer as the app would send it: offset removed, byte 7 zeroed.

        A buffer of two bytes or fewer is not a settings buffer (see :meth:`decode_path_order`) and is returned as is.
        """
        if len(path_order) <= 2:
            return path_order
        raw = bytearray(path_order.encode("latin-1"))
        raw.extend(b"\x00" * (8 - len(raw)))
        for index in range(7):
            raw[index] = max(raw[index] - RESERVED_ECHO_OFFSET, 0)
        raw[7] = 0
        return raw.decode("latin-1")

    @staticmethod
    def decode_path_order(path_order: str) -> PathOrderSettings:
        """Decode a device-echoed ``reserved`` string into operational settings.

        The APK builds the buffer with ``new String(bArr)``; every byte is < 128, so
        latin-1 recovers it losslessly. The device adds ``RESERVED_ECHO_OFFSET`` to each
        byte, removed here (clamped at 0). A buffer of two bytes or fewer yields the
        defaults, as in the APK.
        """
        raw = path_order.encode("latin-1") if path_order else b""
        if len(raw) <= 2:
            return PathOrderSettings()
        raw = raw.ljust(8, b"\x00")
        values = [max(b - RESERVED_ECHO_OFFSET, 0) for b in raw[:8]]
        return PathOrderSettings(*values[:2], *values[3:])
