import asyncio
from asyncio import Queue
import codecs
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from luba_desktop.event.event import BleNotificationEvent

address = "90:38:0C:6E:EE:9E"
MODEL_NBR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

UART_SERVICE_UUID = "0000ffff-0000-1000-8000-00805f9b34fb"
UART_RX_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
UART_TX_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"


# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ServiceName:00001801-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ---CharacterName:00002a05-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ServiceName:00001800-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ---CharacterName:00002a00-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ---CharacterName:00002a01-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ---CharacterName:00002aa6-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ServiceName:0000ffff-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.762 21981 22174 E EspBleUtil: ---CharacterName:0000ff01-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.762 21981 22174 E EspBleUtil: ---CharacterName:0000ff02-0000-1000-8000-00805f9b34fb


UUID_SERVICE = "0000ffff-0000-1000-8000-00805f9b34fb"
UUID_WRITE_CHARACTERISTIC = "0000ff01-0000-1000-8000-00805f9b34fb"
UUID_NOTIFICATION_CHARACTERISTIC = "0000ff02-0000-1000-8000-00805f9b34fb"
UUID_NOTIFICATION_DESCRIPTOR = "00002902-0000-1000-8000-00805f9b34fb"

CLIENT_CHARACTERISTIC_CONFIG_DESCRIPTOR_UUID = "00002902-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE = "0000180F-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHARACTERISTIC = "00002A19-0000-1000-8000-00805f9b34fb"
GENERIC_ATTRIBUTE_SERVICE = "00001801-0000-1000-8000-00805f9b34fb"
SERVICE_CHANGED_CHARACTERISTIC = "00002A05-0000-1000-8000-00805f9b34fb"

def slashescape(err):
    """codecs error handler. err is UnicodeDecode instance. return
    a tuple with a replacement for the unencodable part of the input
    and a position where encoding should continue"""
    # print err, dir(err), err.start, err.end, err.object[:err.start]
    thebyte = err.object[err.start : err.end]
    repl = "\\x" + hex(ord(thebyte))[2:]
    return (repl, err.end)

codecs.register_error("slashescape", slashescape)


class BleLubaConnection:
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
            if "Luba-" in advertising_data.local_name:
                return True
            return False

        device = await scanner.find_device_by_filter(scanCallback)
        if device is not None:
            self.client = BleakClient(device.address)
            return await self.connect()
    
    async def connect(self) -> bool:
    
        if(self.client is not None):
            return await self.client.connect()
        
            
    def notification_handler(self, characteristic: BleakGATTCharacteristic, data: bytearray):
        """Simple notification handler which prints the data received."""
        # print(f"Response {characteristic.description}: {data}")
        # print(data.decode("utf-8") )
        # BlufiNotifyData
        # run an event handler back to somewhere
        self._bleEvt.BleNotification(data)
        


    def notification2_handler(self, characteristic: BleakGATTCharacteristic, data: bytearray):
        """Simple notification handler which prints the data received."""
        # print(f"Response 2 {characteristic.description}: {data}")
        # print(data.decode("utf-8") )
        # BlufiNotifyData
        # run an event handler back to somewhere


    async def notifications(self):
        if(self.client.is_connected):
            await self.client.start_notify(
                UUID_NOTIFICATION_CHARACTERISTIC, self.notification_handler
            )
            await self.client.start_notify(
                SERVICE_CHANGED_CHARACTERISTIC, self.notification2_handler
            )

    def getClient(self):
        return self.client





