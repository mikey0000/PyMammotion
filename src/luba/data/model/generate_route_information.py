from typing import List


class GenerateRouteInformation:
    def __init__(self, one_hashs: List[int], job_mode: int, channel_width: int, speed: float, ultra_wave: int,
                 channel_mode: int, rain_tactics: int, knife_height: int, toward: int, edge_mode: int, path_order: int,
                 obstacle_laps: int):
        self.one_hashs = one_hashs
        self.rain_tactics = rain_tactics
        self.job_mode = job_mode
        self.knife_height = knife_height
        self.speed = speed
        self.ultra_wave = ultra_wave
        self.channel_width = channel_width
        self.channel_mode = channel_mode
        self.toward = toward
        self.edge_mode = edge_mode
        self.path_order = path_order  # border or grid first
        self.obstacle_laps = obstacle_laps

    def get_job_id(self):
        return self.job_id

    def set_job_id(self, job_id: int):
        self.job_id = job_id

    def get_job_ver(self):
        return self.job_ver

    def set_job_ver(self, job_ver: int):
        self.job_ver = job_ver

    def get_rain_tactics(self):
        return self.rain_tactics

    def set_rain_tactics(self, rain_tactics: int):
        self.rain_tactics = rain_tactics

    def get_job_mode(self):
        return self.job_mode

    def set_job_mode(self, job_mode: int):
        self.job_mode = job_mode

    def get_knife_height(self):
        return self.knife_height

    def set_knife_height(self, knife_height: int):
        self.knife_height = knife_height

    def get_speed(self):
        return self.speed

    def set_speed(self, speed: float):
        self.speed = speed

    def get_ultra_wave(self):
        return self.ultra_wave

    def set_ultra_wave(self, ultra_wave: int):
        self.ultra_wave = ultra_wave

    def get_channel_width(self):
        return self.channel_width

    def set_channel_width(self, channel_width: int):
        self.channel_width = channel_width

    def get_channel_mode(self):
        return self.channel_mode

    def set_channel_mode(self, channel_mode: int):
        self.channel_mode = channel_mode

    def get_toward(self):
        return self.toward

    def set_toward(self, toward: int):
        self.toward = toward

    def get_edge_mode(self):
        return self.edge_mode

    def set_edge_mode(self, edge_mode: int):
        self.edge_mode = edge_mode

    def get_path_order(self):
        return self.path_order

    def set_path_order(self, path_order: int):
        self.path_order = path_order

    def get_obstacle_laps(self):
        return self.obstacle_laps

    def set_obstacle_laps(self, obstacle_laps: int):
        self.obstacle_laps = obstacle_laps

    def get_one_hashs(self):
        return self.one_hashs

    def set_one_hashs(self, one_hashs: List[int]):
        self.one_hashs = one_hashs

    def __str__(self):
        return f"GenerateRouteInformation{{oneHashs={self.one_hashs}, jobId={self.job_id}, jobVer={self.job_ver}, " \
               f"rainTactics={self.rain_tactics}, jobMode={self.job_mode}, knifeHeight={self.knife_height}, " \
               f"speed={self.speed}, UltraWave={self.ultra_wave}, channelWidth={self.channel_width}, " \
               f"channelMode={self.channel_mode}, toward={self.toward}, edgeMode={self.edge_mode}}}"
