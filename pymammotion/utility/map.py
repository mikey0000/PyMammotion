import math

import numpy as np

from pymammotion.data.model.location import Point


class CoordinateConverter:
    def __init__(self, latitude_rad: float, longitude_rad: float) -> None:
        # Initialize constants
        self.WGS84A = 6378137.0
        self.f_ = 3.3528106647474805e-21
        self.b_ = (1.0 - self.f_) * self.WGS84A
        self.e2_ = (2.0 - self.f_) * self.f_
        self.e2m_ = (1.0 - self.f_) * (1.0 - self.f_)
        self.ep2_ = ((self.WGS84A**2) - (self.b_**2)) / (self.b_**2)

        # Initialize rotation matrix
        self.R_ = np.zeros((3, 3))

        # Variables to store initial LLA
        self.x0_ = 0.0
        self.y0_ = 0.0
        self.z0_ = 0.0

        # Call set_init_lla with provided lat/lon
        self.set_init_lla(latitude_rad, longitude_rad)

    def set_init_lla(self, lat_rad, lon_rad) -> None:
        sin_lat = math.sin(lat_rad)
        cos_lat = math.cos(lat_rad)
        sin_lon = math.sin(lon_rad)
        cos_lon = math.cos(lon_rad)

        sqrt = self.WGS84A / math.sqrt(1.0 - (self.e2_ * (sin_lat**2)))
        d3 = sqrt * cos_lat

        self.x0_ = d3 * cos_lon
        self.y0_ = d3 * sin_lon
        self.z0_ = self.e2m_ * sqrt * sin_lat

        self.R_[0][0] = -sin_lon
        self.R_[0][1] = cos_lon
        self.R_[0][2] = 0.0

        self.R_[1][0] = -cos_lon * sin_lat
        self.R_[1][1] = -sin_lon * sin_lat
        self.R_[1][2] = cos_lat

        self.R_[2][0] = cos_lon * cos_lat
        self.R_[2][1] = sin_lon * cos_lat
        self.R_[2][2] = sin_lat

    def enu_to_lla(self, e, n) -> Point:
        d3 = self.R_[0][0] * n + self.R_[1][0] * e + self.x0_
        d4 = self.R_[0][1] * n + self.R_[1][1] * e + self.y0_
        d5 = self.R_[0][2] * n + self.R_[1][2] * e + self.z0_

        hypot = math.hypot(d3, d4)
        atan2_lat = math.atan2(self.WGS84A * d5, self.b_ * hypot)

        sin_lat = math.sin(atan2_lat)
        cos_lat = math.cos(atan2_lat)

        lon = math.atan2(d4, d3) * 180.0 / math.pi
        lat = (
            math.atan2(d5 + self.ep2_ * self.b_ * (sin_lat**3), hypot - self.e2_ * self.WGS84A * (cos_lat**3))
            * 180.0
            / math.pi
        )

        return Point(latitude=lat, longitude=lon)
