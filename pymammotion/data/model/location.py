"""Contains RTK models for robot location and RTK positions."""

from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class LocationPoint(DataClassORJSONMixin):
    """Returns a lat long."""

    latitude: float = 0.0
    longitude: float = 0.0

    def __init__(self, latitude: float = 0.0, longitude: float = 0.0) -> None:
        self.latitude = latitude
        self.longitude = longitude


@dataclass
class Dock(LocationPoint):
    """Stores robot dock position."""

    rotation: int = 0


@dataclass
class Location(DataClassORJSONMixin):
    """Stores/retrieves RTK GPS data."""

    device: LocationPoint = field(default_factory=LocationPoint)
    RTK: LocationPoint = field(default_factory=LocationPoint)
    dock: Dock = field(default_factory=Dock)
    position_type: int = 0
    orientation: int = 0  # 360 degree rotation +-
    work_zone: int = 0
