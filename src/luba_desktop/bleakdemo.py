import asyncio
from asyncio import Queue
import codecs
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from pyjoystick.sdl2 import Key, Joystick, run_event_loop
from timeit import default_timer as timer

from luba_desktop.blufi_impl import Blufi
from luba_desktop.blelibs.notifydata import BlufiNotifyData
from luba_desktop.utility.periodic import Periodic

import nest_asyncio

nest_asyncio.apply()

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


def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    """Simple notification handler which prints the data received."""
    print(f"Response {characteristic.description}: {data}")
    # print(data.decode("utf-8") )
    # BlufiNotifyData


def notification2_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    """Simple notification handler which prints the data received."""
    print(f"Response 2 {characteristic.description}: {data}")
    # print(data.decode("utf-8") )
    # BlufiNotifyData


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

    def __init__(self):
        pass

    async def scanForLubaAndConnect(self):
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
            try:
                await self.client.connect()
            except Exception as err:
                print(err)

    async def notifications(self):
        if(self.client.is_connected):
            await self.client.start_notify(
                UUID_NOTIFICATION_CHARACTERISTIC, notification_handler
            )
            await self.client.start_notify(
                SERVICE_CHANGED_CHARACTERISTIC, notification2_handler
            )

    def getClient(self):
        return self.client


# async def main(address, char_uuid_notification, moveEvt):

#     stop_event = asyncio.Event()
#     # 0000ffff-0000-1000-8000-00805f9b34fb 0000ff02-0000-1000-8000-00805f9b34fb
#     # TODO: add something that calls stop_event.set()

#     # print(bytes.fromhex('08F801100728013001380142020801') )
#     # print(b'\x08\xf8\x01\x10\x07(\x010\x018\x01B\x02\x08\x01'.decode('utf-8', 'slashescape'))

#     def callback(device, advertising_data):
#         # TODO: do something with incoming data
#         print(device)
#         print(advertising_data)
#         if device.address == '90:38:0C:6E:EE:9E':
#             stop_event.set()
#         if "Luba-" in advertising_data.local_name:
#             stop_event.set()

#     async with BleakScanner(callback) as scanner:
#         ...
#         # Important! Wait for an event to trigger stop, otherwise scanner
#         # will stop immediately.
#         await stop_event.wait()

#     # scanner stops when block exits
#     async with BleakClient(address) as client:

#         print(f"Connected: {client.is_connected}")

#         # model_number = await client.read_gatt_char(GENERIC_ATTRIBUTE_SERVICE)
#         # print("Model Number: {0}".format("".join(map(chr, model_number))))
#         print(f"Connected: {client.is_connected}")
#         blufiClient = Blufi(client)
#         # await blufiClient.requestDeviceStatus()
#         # await blufiClient.getDeviceInfo()
#         try:
#             # await blufiClient.getDeviceVersionMain()
#             # while(True):
#             # await blufiClient.setKnifeHight(35)

# # pretty sure this sends back all boundaries etc
#             await blufiClient.sendTodevBleSync()
#             #TOAPP_WIFI_IOT_STATUS
#             # TOAPP_DEVINFO_RESP
#             moveEvt += moveLuba
#             # await blufiClient.getDeviceVersionMain()

#             # await blufiClient.setKnifeControl(1)

#             # await blufiClient.setKnifeControl(0)


#         except Exception as err:
#             print(err)

#         await asyncio.sleep(5.0)
#         await client.stop_notify(char_uuid_notification)


class JoystickControl:
    """Joystick class for controlling Luba with a joystick"""

    angular_percent = 0
    linear_percent = 0
    linear_speed = 0
    angular_speed = 0

    def __init__(self):
        self._curr_time = timer()
        self._first_run = True

    async def controller(self, client: Blufi, queue: Queue, moveEvt):
        def print_add(joy):
            print("Added", joy)

        def print_remove(joy):
            print("Removed", joy)

        def key_received(key):
            # add key to control await blufiClient.setKnifeControl(1) turn blade on/off

            # simple debouncer

            if key.keytype is Key.BUTTON and key.value is 1:
                print(key, "-", key.keytype, "-", key.number, "-", key.value)
                if key.number == 0:  # x
                    asyncio.run(client.returnToDock())
                if key.number == 1:
                    asyncio.run(client.leaveDock())
                if key.number == 3:
                    asyncio.run(client.setKnifeControl(1))
                if key.number == 2:
                    asyncio.run(client.setKnifeControl(0))
                if key.number == 9:
                    # lower knife height
                    pass
                if key.number == 10:
                    # raise knife height
                    pass

            if key.keytype is Key.AXIS:
                elapsed_time = timer()
                if (elapsed_time - self._curr_time) < 0.5 and not self._first_run:
                    return
                else:
                    self._curr_time = timer()
                self._first_run = False
                if key.value > 0.09 or key.value < -0.09:
                    print(key, "-", key.keytype, "-", key.number, "-", key.value)

                    match key.number:
                        case 1:  # left (up down)
                            # take left right values and convert to linear movement
                            # -1 is forward
                            # 1 is back

                            # linear_speed==1000
                            # linear_speed==-1000
                            print("case 1")
                            if key.value > 0:
                                self.linear_speed = 270.0
                                self.linear_percent = abs(key.value * 100)
                            else:
                                self.linear_speed = 90.0
                                self.linear_percent = abs(key.value * 100)

                        case 2:  # right  (left right)
                            # take left right values and convert to angular movement
                            # -1 left
                            # 1 is right
                            # angular_speed==-450
                            # angular_speed==450
                            if key.value > 0:
                                self.angular_speed = 360.0
                                self.angular_percent = abs(key.value * 100)
                            else:
                                # angle=180.0
                                # linear_speed=0//angular_speed=-450
                                self.angular_speed = 180.0
                                self.angular_percent = abs(key.value * 100)

                    asyncio.run(
                        client.transformBothSpeeds(
                            self.linear_speed,
                            self.angular_speed,
                            self.linear_percent,
                            self.angular_percent,
                        )
                    )
                    
                else:
                    match key.number:
                        case 1:  # left (up down)
                            self.linear_speed = 0.0
                            self.linear_percent = 0
                        case 2:  # right  (left right)
                            self.angular_speed = 0.0
                            self.angular_percent = 0

        run_event_loop(print_add, print_remove, key_received)
