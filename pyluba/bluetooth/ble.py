
from bleak import BleakClient, BleakScanner, BLEDevice
from bleak.backends.characteristic import BleakGATTCharacteristic

from pyluba.bluetooth.const import (
    SERVICE_CHANGED_CHARACTERISTIC,
    UUID_NOTIFICATION_CHARACTERISTIC,
)
from pyluba.event.event import BleNotificationEvent

# TODO setup for each Luba
address = "90:38:0C:6E:EE:9E"

class LubaBLE:
    client: BleakClient

    def __init__(self, bleEvt: BleNotificationEvent):
        self._bleEvt = bleEvt

    async def scanForLubaAndConnect(self) -> bool:
        scanner = BleakScanner()

        def scanCallback(device, advertising_data):
            # TODO: do something with incoming data
            print(device)
            print(advertising_data)
            if device.address == "90:38:0C:6E:EE:9E":
                return True
            if  advertising_data.local_name and "Luba-" in advertising_data.local_name:
                return True
            return False

        device = await scanner.find_device_by_filter(scanCallback)
        if device is not None:
            return await self.create_client(device)

    async def create_client(self, device: BLEDevice):
        self.client = BleakClient(device.address)
        return await self.connect()

    async def connect(self) -> bool:
        if self.client is not None:
            return await self.client.connect()

    async def disconnect(self) -> bool:
        if self.client is not None:
            return await self.client.disconnect()

    async def notification_handler(self, _characteristic: BleakGATTCharacteristic, data: bytearray):
        """Simple notification handler which prints the data received."""
        await self._bleEvt.BleNotification(data)

    def service_changed_handler(self, characteristic: BleakGATTCharacteristic, data: bytearray):
        """Simple notification handler which prints the data received."""
        print(f"Response 2 {characteristic.description}: {data}")
        print(data.decode("utf-8") )
        # BlufiNotifyData
        # run an event handler back to somewhere

    async def notifications(self):
        if self.client.is_connected:
            await self.client.start_notify(
                UUID_NOTIFICATION_CHARACTERISTIC, self.notification_handler
            )
            await self.client.start_notify(
                SERVICE_CHANGED_CHARACTERISTIC, self.service_changed_handler
            )

    def getClient(self):
        return self.client
