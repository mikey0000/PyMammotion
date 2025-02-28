from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class GenerateRouteInformation:
    """Creates a model for generating route information and mowing plan before starting a job."""

    one_hashs: list[int] = list
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
