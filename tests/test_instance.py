import asyncio
from threading import Thread
from luba_desktop import BleLubaConnection
from luba_desktop.bleakdemo import JoystickControl
from luba_desktop.blufi_impl import Blufi
from luba_desktop.utility.event import Event

address = "90:38:0C:6E:EE:9E"
UUID_SERVICE = "0000ffff-0000-1000-8000-00805f9b34fb"
UUID_WRITE_CHARACTERISTIC = "0000ff01-0000-1000-8000-00805f9b34fb"
UUID_NOTIFICATION_CHARACTERISTIC = "0000ff02-0000-1000-8000-00805f9b34fb"
UUID_NOTIFICATION_DESCRIPTOR = "00002902-0000-1000-8000-00805f9b34fb"

CLIENT_CHARACTERISTIC_CONFIG_DESCRIPTOR_UUID = "00002902-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE = "0000180F-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHARACTERISTIC = "00002A19-0000-1000-8000-00805f9b34fb"
GENERIC_ATTRIBUTE_SERVICE = "00001801-0000-1000-8000-00805f9b34fb"
SERVICE_CHANGED_CHARACTERISTIC = "00002A05-0000-1000-8000-00805f9b34fb"
moveEvt = Event()


async def ble_heartbeat(blufi_client):
    while True:
        await blufi_client.sendTodevBleSync()
        # eventually send an event and update data from sync
        await asyncio.sleep(5)

class AsyncLoopThread(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

async def run():
    bleLubaConn = BleLubaConnection()
    await bleLubaConn.scanForLubaAndConnect()
    await bleLubaConn.notifications()
    client = bleLubaConn.getClient()
    blufi_client = Blufi(client)
    # Run the ble heart beat in the background continuously
    loop_handler_bleheart = AsyncLoopThread()
    loop_handler_bleheart.start()
    asyncio.run_coroutine_threadsafe(ble_heartbeat(blufi_client), loop_handler_bleheart.loop)
    
    print("joystick code")
    await JoystickControl().controller(blufi_client, moveEvt)
    print("end run?")
	#await main(address, UUID_NOTIFICATION_CHARACTERISTIC,moveEvt)



if __name__ ==  '__main__':
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(run())
    # 
    # asyncio.run(run())
    event_loop.run_until_complete(run())
    
    # asyncio.ensure_future(function_2())
    loop.run_forever()
    


