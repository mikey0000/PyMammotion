from bleak import BleakClient, BleakScanner, BLEDevice
from bleak.backends.characteristic import BleakGATTCharacteristic

from pymammotion.bluetooth.const import SERVICE_CHANGED_CHARACTERISTIC, UUID_NOTIFICATION_CHARACTERISTIC
from pymammotion.event.event import BleNotificationEvent


class MammotionBLE:
    """Class for basic ble connections to mowers."""

    client: BleakClient

    def __init__(self, bleEvt: BleNotificationEvent) -> None:
        self._bleEvt = bleEvt

    async def scanForLubaAndConnect(self) -> bool:
        scanner = BleakScanner()

        def scanCallback(device, advertising_data) -> bool:
            # TODO: do something with incoming data
            print(device)
            print(advertising_data)
            if advertising_data.local_name and (
                "Luba-" in advertising_data.local_name or "Yuka-" in advertising_data.local_name
            ):
                return True
            return False

        device = await scanner.find_device_by_filter(scanCallback)
        if device is not None:
            return await self.create_client(device)
        return False

    async def create_client(self, device: BLEDevice):
        self.client = BleakClient(device.address)
        return await self.connect()

    async def connect(self) -> bool:
        if self.client is not None:
            return await self.client.connect()

    async def disconnect(self) -> bool:
        if self.client is not None:
            return await self.client.disconnect()

    async def notification_handler(self, _characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Simple notification handler which prints the data received."""
        await self._bleEvt.BleNotification(data)

    def service_changed_handler(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Simple notification handler which prints the data received."""
        print(f"Response 2 {characteristic.description}: {data}")
        print(data.decode("utf-8"))
        # BlufiNotifyData
        # run an event handler back to somewhere

    async def notifications(self) -> None:
        if self.client.is_connected:
            await self.client.start_notify(UUID_NOTIFICATION_CHARACTERISTIC, self.notification_handler)
            await self.client.start_notify(SERVICE_CHANGED_CHARACTERISTIC, self.service_changed_handler)

    def get_client(self):
        """Returns the ble client."""
        return self.client
