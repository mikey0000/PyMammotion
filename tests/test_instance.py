import asyncio
from threading import Thread
import threading
from luba_desktop.ble_connection import BleLubaConnection
from luba_desktop.control.joystick_control import JoystickControl
from luba_desktop.ble_message import BleMessage
from luba_desktop.blelibs.notifydata import BlufiNotifyData
from luba_desktop.event.event import BleNotificationEvent, MoveEvent

moveEvt = MoveEvent()
bleNotificationEvt = BleNotificationEvent()


async def ble_heartbeat(luba_client):
    while True:
        await luba_client.sendTodevBleSync()
        # eventually send an event and update data from sync
        await asyncio.sleep(1)
        await luba_client.send_ble_alive()
        await asyncio.sleep(10.5)

class AsyncLoopThread(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()


async def run():
    bleLubaConn = BleLubaConnection(bleNotificationEvt)
    did_connect = await bleLubaConn.scanForLubaAndConnect()
    if not did_connect:
        return
    await bleLubaConn.notifications()
    client = bleLubaConn.getClient()
    luba_client = BleMessage(client, moveEvt)

    def handle_notifications(data:bytearray):
        result = luba_client.parseNotification(data)
        print(result)
        if (result == 0):
            luba_client.parseBlufiNotifyData()
            luba_client.clearNotification()

    bleNotificationEvt.AddSubscribersForBleNotificationEvent(handle_notifications)
    # Run the ble heart beat in the background continuously which still doesn't quite work
    
    # loop_handler_bleheart = threading.Thread(target=), args=(), daemon=True)
    await luba_client.sendTodevBleSync()
    await luba_client.send_ble_alive()
    # await luba_client.getDeviceInfo()
    # gets info about luba and some other stuff
    # await luba_client.get_all_boundary_hash_list(3)
    await luba_client.get_all_boundary_hash_list(0)

    # get map data off Luba
    #8656065632562971511
    # await asyncio.sleep(1)
    await luba_client.synchronize_hash_data(8656065632562971511)
    
    # problem one
    # await asyncio.sleep(1)
    await luba_client.synchronize_hash_data(5326333396143256633)
    # await asyncio.sleep(1)
    # await luba_client.sendTodevBleSync()
    # await luba_client.send_ble_alive()
    await luba_client.synchronize_hash_data(6316048569363781876)    
    # probably gets paths
    # await luba_client.get_line_info(4)
    # await luba_client.get_hash_response(1, 1)
    print("joystick code")
    in_queue = asyncio.Queue()
    # joystick = JoystickControl(luba_client)
    # joystick.run_controller()

    
    asyncio.run(ble_heartbeat(luba_client))
    print("end run?")



if __name__ ==  '__main__':
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    asyncio.run(run())
    event_loop.run_forever()
    


