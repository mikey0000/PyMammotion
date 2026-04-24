from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pymammotion.data.model.work import CurrentTaskSettings

logger = logging.getLogger(__name__)


class PathOrderSettings(NamedTuple):
    """Operational settings decoded from the reserved/path_order bytes field.

    The APK encodes these as an 8-byte array via ``new String(bArr)`` and passes
    it as the ``reserved`` field on ``NavReqCoverPath``.  Byte layout (from
    WorkingOptionView / WorkSettingViewModel in the APK source):

      [0] edge_mode            — boundary laps (APK: border_mode)
      [1] obstacle_laps        — laps around obstacles (APK: mowing_laps_obs)
      [2] rain_tactics         — rain/schedule flag (APK: schedule enable or 0)
      [3] start_progress       — starting waypoint index
      [4] toward_mode          — toward/direction mode (Luba1); 0 for other types
      [5] device_tactics       — Yuka: mow/dump/edge combo 0–14; LubaPro: 8; others: 0
      [6] collect_grass_freq   — grass collection frequency (APK: collectGrassFrequency,
                                  defaults to 10 when not in dump mode)
      [7] reserved             — unused, always 0
    """

    edge_mode: int = 1
    obstacle_laps: int = 0
    rain_tactics: int = 0
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
    rain_tactics: int = 0
    blade_height: int = 0
    path_order: str = ""
    toward: int = 0  # is just angle
    toward_included_angle: int = 0
    toward_mode: int = 0  # angle type relative etc
    edge_mode: int = 1  # border laps
    obstacle_laps: int = 1

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
        - ``job_ver`` → ``job_version``
        - ``knife_height`` → ``blade_height``
        - ``zone_hashs`` → ``one_hashs`` (copied, not aliased)
        - ``reserved`` → ``path_order`` — additionally decoded via
          :meth:`decode_path_order` so ``obstacle_laps`` and ``rain_tactics``
          surface as top-level fields on the returned instance.
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
            rain_tactics=decoded.rain_tactics,
            blade_height=settings.knife_height,
            path_order=settings.reserved,
            toward=settings.toward,
            toward_included_angle=settings.toward_included_angle,
            toward_mode=settings.toward_mode,
            edge_mode=settings.edge_mode,
            obstacle_laps=decoded.obstacle_laps,
        )

    @staticmethod
    def decode_path_order(path_order: str) -> PathOrderSettings:
        """Decode the reserved/path_order string back into operational settings.

        The APK builds this field with ``new String(bArr)`` where bArr is an 8-byte
        array.  Protobuf transmits string fields as UTF-8, but all values used by
        the APK are in the ASCII range (0–127) so ``ord()`` recovers the raw byte
        value losslessly.  Values ≥ 128 (non-ASCII) are decoded via latin-1 to
        preserve the original byte value.
        """
        # Decode each character back to its original byte value.
        # latin-1 maps code points 0-255 directly to byte values 0-255.
        raw = path_order.encode("latin-1") if path_order else b""
        raw = raw.ljust(8, b"\x00")  # pad to 8 bytes if shorter
        return PathOrderSettings(
            edge_mode=raw[0],
            obstacle_laps=raw[1],
            rain_tactics=raw[2],
            start_progress=raw[3],
            toward_mode=raw[4],
            device_tactics=raw[5],
            collect_grass_freq=raw[6],
            reserved=raw[7],
        )
