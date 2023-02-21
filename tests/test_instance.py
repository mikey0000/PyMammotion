import asyncio
import sys
from luba_desktop import BleLubaConnection
from luba_desktop.bleakdemo import controller
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


async def run():
    bleLubaConn = BleLubaConnection()
    await bleLubaConn.scanForLubaAndConnect()
    await bleLubaConn.notifications()
    client = bleLubaConn.getClient()
    blufiClient = Blufi(client)
    await controller(blufiClient, moveEvt)
	#await main(address, UUID_NOTIFICATION_CHARACTERISTIC,moveEvt)



if __name__ ==  '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(run())
    # 
    # asyncio.run(run())
    asyncio.run(run())
    
    # asyncio.ensure_future(function_2())
    loop.run_forever()
    


