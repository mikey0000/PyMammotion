from dataclasses import dataclass, field


@dataclass
class RangeLimit:
    min: float
    max: float


@dataclass
class DeviceLimits:
    cutter_height: RangeLimit = field(default_factory=RangeLimit)
    working_speed: RangeLimit = field(default_factory=RangeLimit)
    working_path: RangeLimit = field(default_factory=RangeLimit)
    work_area_num_max: int = 60
    display_image_type: int = 0

    def to_dict(self) -> dict:
        """Convert the device limits to a dictionary format."""
        return {
            "cutter_height": {"min": self.cutter_height.min, "max": self.cutter_height.max},
            "working_speed": {"min": self.working_speed.min, "max": self.working_speed.max},
            "working_path": {"min": self.working_path.min, "max": self.working_path.max},
            "work_area_num_max": self.work_area_num_max,
            "display_image_type": self.display_image_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceLimits":
        """Create a DeviceLimits instance from a dictionary."""
        return cls(
            cutter_height=RangeLimit(min=data["cutter_height"]["min"], max=data["cutter_height"]["max"]),
            working_speed=RangeLimit(min=data["working_speed"]["min"], max=data["working_speed"]["max"]),
            working_path=RangeLimit(min=data["working_path"]["min"], max=data["working_path"]["max"]),
            work_area_num_max=data["work_area_num_max"],
            display_image_type=data["display_image_type"],
        )

    def validate(self) -> bool:
        """Validate that all ranges are logical (min <= max)."""
        return all(
            [
                self.cutter_height.min <= self.cutter_height.max,
                self.working_speed.min <= self.working_speed.max,
                self.working_path.min <= self.working_path.max,
                self.work_area_num_max > 0,
                self.display_image_type in (0, 1),
            ]
        )
