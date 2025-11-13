from dataclasses import dataclass
from typing import Any

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class TopicProperty(DataClassORJSONMixin):
    """TopicProperty."""

    id: str = ""
    method: str = ""
    params: dict[str, Any] | None = None
    sys: dict[str, Any] | None = None
    time: int = 0
    version: str = ""


@dataclass
class TopicDeviceStatus(DataClassORJSONMixin):
    """TopicDeviceStatus."""

    gmt_create: int = 0
    action: str = ""
    product_key: str = ""
    device_name: str = ""
    iot_id: str = ""


class TopicUtils:
    """Utility helpers ported from the Java TopicUtils."""

    @staticmethod
    def _split_topic(topic: str) -> list[str]:
        if topic is None:
            raise ValueError("topic must not be None")
        # preserve empty segments (leading/trailing slashes)
        return topic.split("/")

    @staticmethod
    def get_device_name(topic: str) -> str:
        parts = TopicUtils._split_topic(topic)
        # original code expects the device name at index 3 when topic is like:
        # /sys/{productKey}/{deviceName}/...
        try:
            return parts[3]
        except IndexError:
            return ""

    @staticmethod
    def get_identifier(topic: str) -> str:
        if "property" in (topic or ""):
            return ""
        parts = TopicUtils._split_topic(topic)
        if len(parts) < 2:
            return ""
        # second-last element (may be empty if trailing slash)
        return parts[-2] or ""

    @staticmethod
    def get_method(topic: str) -> str:
        """Get the method from a topic."""
        parts = TopicUtils._split_topic(topic)
        if len(parts) >= 2:
            return f"/{parts[-2]}/{parts[-1]}"
        return ""
