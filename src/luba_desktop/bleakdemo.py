import asyncio
import codecs
import math
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from pyjoystick.sdl2 import Key, Joystick, run_event_loop


from luba_desktop.blufi_impl import Blufi
from luba_desktop.blelibs.notifydata import BlufiNotifyData

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
    """ codecs error handler. err is UnicodeDecode instance. return
    a tuple with a replacement for the unencodable part of the input
    and a position where encoding should continue"""
    #print err, dir(err), err.start, err.end, err.object[:err.start]
    thebyte = err.object[err.start:err.end]
    repl = u'\\x'+hex(ord(thebyte))[2:]
    return (repl, err.end)

codecs.register_error('slashescape', slashescape)


class BleLubaConnection():
    client: BleakClient

    def __init__(self):
        pass


    async def scanForLubaAndConnect(self):
        scanner = BleakScanner()

        def scanCallback(device, advertising_data):
            # TODO: do something with incoming data
            print(device)
            print(advertising_data)
            if device.address == '90:38:0C:6E:EE:9E':
                return True
            if "Luba-" in advertising_data.local_name:
                return True
            return False

        device = await scanner.find_device_by_filter(scanCallback)


        self.client = BleakClient(device.address)
        try:
            await self.client.connect()
        except Exception as e:
            print(e)

    async def notifications(self):
        await self.client.start_notify(UUID_NOTIFICATION_CHARACTERISTIC, notification_handler)
        await self.client.start_notify(SERVICE_CHANGED_CHARACTERISTIC, notification2_handler)

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

#         await client.start_notify(char_uuid_notification, notification_handler)
#         await client.start_notify(SERVICE_CHANGED_CHARACTERISTIC, notification2_handler)
        
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
#             async def moveLuba(angularSpeed, linearSpeed, angularPercent, linearPercent):
#                 await blufiClient.transformBothSpeeds(angularSpeed, linearSpeed, angularPercent, linearPercent)
#             # TOAPP_DEVINFO_RESP
#             moveEvt += moveLuba
#             # await blufiClient.getDeviceVersionMain()


#             # await blufiClient.transformSpeed(0.0, 0.0)
#             # await blufiClient.transformSpeed(90.0, 100.0)
#             # await asyncio.sleep(1)
#             # await blufiClient.transformSpeed(0.0, 100.0)
#             # await blufiClient.transformSpeed(0.0, 0.0)
#             # await blufiClient.setKnifeControl(1)

#             # await blufiClient.setKnifeControl(0)

             
#         except Exception as err:
#             print(err)

#         await asyncio.sleep(5.0)
#         await client.stop_notify(char_uuid_notification)


async def controller(client: Blufi, moveEvt):
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    

    def print_add(joy):
        print('Added', joy)

    def print_remove(joy):
        print('Removed', joy)

    def key_received(key):
        # case R.id.iv_rocker_botton /* 2131296681 */:
        #     transfromSpeed(270.0f, 100.0f);
        #     break;
        # case R.id.iv_rocker_left /* 2131296682 */:
        #     transfromSpeed(180.0f, 100.0f);
        #     break;
        # case R.id.iv_rocker_right /* 2131296683 */:
        #     transfromSpeed(0.0f, 100.0f);
        #     break;
        # case R.id.iv_rocker_top /* 2131296684 */:
        #     transfromSpeed(90.0f, 100.0f);

        angularPercent = 0
        linearPercent = 0
        linearSpeed = 0
        angularSpeed = 0
        if(key.keytype is Key.AXIS):
            if(key.value > 0.2 or key.value < -0.2):
                print(key, '-', key.keytype, '-', key.number, '-', key.value)

                match key.number:
                    case 0: #left (left right)
                        pass
                    case 1: #left (up down)
                        #take left right values and convert to linear movement 
                        # -1 is forward
                        # 1 is back
                        
                        # linearSpeed==1000
                        # linearSpeed==-1000
                        print("case 1")
                        if(key.value > 0):
                            linearSpeed = 270.0
                            linearPercent = abs(key.value*100)
                        else:
                            linearSpeed = 90.0
                            linearPercent = abs(key.value*100)
                        
                    case 2: # right  (left right)
                        #take left right values and convert to angular movement 
                        # -1 left
                        # 1 is right
                        # angularSpeed==-450
                        # angularSpeed==450
                        if(key.value > 0):
                            angularSpeed = 360.0
                            angularPercent = abs(key.value*100)
                        else:
                            # angle=180.0
                            # linearSpeed=0//angularSpeed=-450
                            angularSpeed = 180.0
                            angularPercent = abs(key.value*100)
                        
                        
                        pass
                    case 3: #right (up down)
                        pass
                
                asyncio.run(client.transformBothSpeeds(linearSpeed, angularSpeed, linearPercent, angularPercent))
                # loop = asyncio.get_event_loop()
                # loop.run_until_complete(client.transformBothSpeeds(angularSpeed, linearSpeed, angularPercent, linearPercent))
                # await client.transformBothSpeeds(angularSpeed, linearSpeed, angularPercent, linearPercent)

    run_event_loop(print_add, print_remove, key_received)
