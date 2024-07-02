import logging
from typing import List

logger = logging.getLogger(__name__)


class GenerateRouteInformation:
    """Creates a model for generating route information and mowing plan before starting a job."""

    def __init__(
        self,
        one_hashs: List[int],
        job_mode: int,
        channel_width: int,
        speed: float,
        ultra_wave: int,
        channel_mode: int,
        rain_tactics: int,
        toward: int,
        knife_height: int,
        path_order: str,
        toward_included_angle: int,
    ):
        self.path_order = ""
        self.toward_mode = 0
        self.one_hashs = one_hashs
        self.rain_tactics = rain_tactics
        self.job_mode = job_mode
        self.knife_height = knife_height
        self.speed = speed
        self.ultra_wave = ultra_wave
        self.channel_width = channel_width
        self.channel_mode = channel_mode
        self.toward = toward
        self.edge_mode = rain_tactics
        self.path_order = path_order
        self.toward_included_angle = toward_included_angle
        logger.debug(
            f"Mode route command parameters jobMode={job_mode}//channelWidth={channel_width}//speed={speed}//UltraWave={ultra_wave}//channelMode={channel_mode}//edgeMode={rain_tactics}//knifeHeight={knife_height}  pathOrder:{path_order.encode('utf-8')}"
        )

    def get_job_id(self) -> int:
        return self.job_id

    def set_job_id(self, job_id: int) -> None:
        self.job_id = job_id

    def get_job_ver(self) -> int:
        return self.job_ver

    def set_job_ver(self, job_ver: int) -> None:
        self.job_ver = job_ver

    def get_rain_tactics(self) -> int:
        return self.rain_tactics

    def set_rain_tactics(self, rain_tactics: int) -> None:
        self.rain_tactics = rain_tactics

    def get_job_mode(self) -> int:
        return self.job_mode

    def set_job_mode(self, job_mode: int) -> None:
        self.job_mode = job_mode

    def get_knife_height(self) -> int:
        return self.knife_height

    def set_knife_height(self, knife_height: int) -> None:
        self.knife_height = knife_height

    def get_speed(self) -> float:
        return self.speed

    def set_speed(self, speed: float) -> None:
        self.speed = speed

    def get_ultra_wave(self) -> int:
        return self.ultra_wave

    def set_ultra_wave(self, ultra_wave: int) -> None:
        self.ultra_wave = ultra_wave

    def get_channel_width(self) -> int:
        return self.channel_width

    def set_channel_width(self, channel_width: int) -> None:
        self.channel_width = channel_width

    def get_channel_mode(self) -> int:
        return self.channel_mode

    def set_channel_mode(self, channel_mode: int) -> None:
        self.channel_mode = channel_mode

    def get_toward(self) -> int:
        return self.toward

    def set_toward(self, toward: int) -> None:
        self.toward = toward

    def get_one_hashs(self) -> List[int]:
        return self.one_hashs if self.one_hashs else []

    def set_one_hashs(self, one_hashs: List[int]) -> None:
        self.one_hashs = one_hashs

    def get_path_order(self) -> str:
        return self.path_order

    def set_path_order(self, path_order: str) -> None:
        self.path_order = path_order

    def get_toward_included_angle(self) -> int:
        return self.toward_included_angle

    def set_toward_included_angle(self, toward_included_angle: int) -> None:
        self.toward_included_angle = toward_included_angle

    def get_toward_mode(self) -> int:
        return self.toward_mode

    def get_edge_mode(self) -> int:
        return self.edge_mode

    def set_edge_mode(self, edge_mode: int) -> None:
        self.edge_mode = edge_mode

    def __str__(self) -> str:
        try:
            return f"GenerateRouteInformation{{oneHashs={self.one_hashs}, jobId={self.job_id}, jobVer={self.job_ver}, rainTactics={self.rain_tactics}, jobMode={self.job_mode}, knifeHeight={self.knife_height}, speed={self.speed}, UltraWave={self.ultra_wave}, channelWidth={self.channel_width}, channelMode={self.channel_mode}, toward={self.toward}, pathOrder='{self.path_order.encode('utf-8')}', edgeMode={self.edge_mode}, towardIncludedAngle={self.toward_included_angle}}}"
        except Exception as e:
            return str(e)
