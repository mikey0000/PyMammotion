import asyncio
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from blufi_impl import Blufi
from blelibs.notifydata import BlufiNotifyData


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


async def main(address, char_uuid_notification):
    stop_event = asyncio.Event()
    # 0000ffff-0000-1000-8000-00805f9b34fb 0000ff02-0000-1000-8000-00805f9b34fb
    # TODO: add something that calls stop_event.set()

    # print(bytes.fromhex('08F801100728013001380142020801') )
    # print(b'\x08\xf8\x01\x10\x07(\x010\x018\x01B\x02\x08\x01'.decode('utf-8', 'slashescape'))

    def callback(device, advertising_data):
        # TODO: do something with incoming data
        print(device)
        print(advertising_data)
        if device.address == '90:38:0C:6E:EE:9E':
            stop_event.set()
        if "Luba-" in advertising_data.local_name:
            stop_event.set()

    async with BleakScanner(callback) as scanner:
        ...
        # Important! Wait for an event to trigger stop, otherwise scanner
        # will stop immediately.
        await stop_event.wait()

    # scanner stops when block exits
    async with BleakClient(address) as client:

        print(f"Connected: {client.is_connected}")

        await client.start_notify(char_uuid_notification, notification_handler)
        await client.start_notify(SERVICE_CHANGED_CHARACTERISTIC, notification2_handler)
        
        # model_number = await client.read_gatt_char(GENERIC_ATTRIBUTE_SERVICE)
        # print("Model Number: {0}".format("".join(map(chr, model_number))))
        print(f"Connected: {client.is_connected}")
        blufiClient = Blufi(client)
        # await blufiClient.requestDeviceStatus()
        # await blufiClient.getDeviceInfo()
        try:
            # await blufiClient.getDeviceVersionMain()
            # while(True):
            # await blufiClient.setKnifeHight(35)

# pretty sure this sends back all boundaries etc
            await blufiClient.sendTodevBleSync()
            #TOAPP_WIFI_IOT_STATUS

            # TOAPP_DEVINFO_RESP
            # await blufiClient.getDeviceVersionMain()


            await blufiClient.transformSpeed(0.0, 0.0)
            await blufiClient.transformSpeed(90.0, 100.0)
            await asyncio.sleep(1)
            # await blufiClient.transformSpeed(0.0, 100.0)
            await blufiClient.transformSpeed(0.0, 0.0)
            await blufiClient.setKnifeControl(1)

            # await blufiClient.setKnifeControl(0)

 
        except Exception as err:
            print(err)

        await asyncio.sleep(5.0)
        await client.stop_notify(char_uuid_notification)

asyncio.run(main(address, UUID_NOTIFICATION_CHARACTERISTIC))
