from asyncio import Future

import async_timeout


class MammotionFuture:
    """Create futures for each MQTT Message."""

    def __init__(self, iot_id) -> None:
        self.iot_id = iot_id
        self.fut: Future = Future()
        self.loop = self.fut.get_loop()

    def _resolve(self, item: bytes) -> None:
        if not self.fut.cancelled():
            self.fut.set_result(item)

    def resolve(self, item: bytes) -> None:
        self.loop.call_soon_threadsafe(self._resolve, item)

    async def async_get(self, timeout: float | int) -> bytes:
        try:
            async with async_timeout.timeout(timeout):
                return await self.fut
        finally:
            self.fut.cancel()
