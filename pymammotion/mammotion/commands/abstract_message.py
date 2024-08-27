from abc import abstractmethod


class AbstractMessage:
    @abstractmethod
    def get_device_name(self) -> str:
        """Get device name."""

    def get_device_product_key(self) -> str:
        """Get device name."""
