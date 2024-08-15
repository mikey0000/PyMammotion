"""Contains RTK models for robot location and RTK positions."""

from dataclasses import dataclass


@dataclass
class Point:
    """Returns a lat long."""

    latitude: float
    longitude: float

    def __init__(self, latitude=0.0, longitude=0.0):
        self.latitude = latitude
        self.longitude = longitude


@dataclass
class Dock(Point):
    """Stores robot dock position."""

    rotation: int

    def __init__(self):
        super().__init__()
        self.rotation = 0


@dataclass
class Location:
    """Stores/retrieves RTK GPS data."""

    device: Point
    RTK: Point
    dock: Dock
    position_type: int
    orientation: int # 360 degree rotation +-

    def __init__(self):
        self.device = Point()
        self.RTK = Point()
        self.dock = Dock()
