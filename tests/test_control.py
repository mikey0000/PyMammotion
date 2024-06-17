import asyncio
from threading import Thread

from pyluba import LubaBLE
from pyluba.bluetooth import BleMessage
from pyluba.event import BleNotificationEvent
from pyluba.event.event import MoveEvent
from pyluba.mammotion.control.joystick import JoystickControl

moveEvt = MoveEvent()
bleNotificationEvt = BleNotificationEvent()

class AsyncLoopThread(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()


async def ble_heartbeat(luba_client):
    while True:
        # await luba_client.send_todev_ble_sync(1)
        # eventually send an event and update data from sync
        # await asyncio.sleep(1)
        await asyncio.sleep(0.01)


async def run():
    # bleLubaConn = LubaBLE(bleNotificationEvt)
    # did_connect = await bleLubaConn.scanForLubaAndConnect()
    # if not did_connect:
    #     return
    # await bleLubaConn.notifications()
    # client = bleLubaConn.getClient()
    # luba_client = BleMessage(client)
    #
    # async def handle_notifications(data: bytearray):
    #     print("got ble message", data)
    #     result = luba_client.parseNotification(data)
    #     print(result)
    #     if result == 0:
    #         await luba_client.parseBlufiNotifyData()
    #         luba_client.clearNotification()
    #
    # bleNotificationEvt.AddSubscribersForBleNotificationEvent(handle_notifications)
    # Run the ble heart beat in the background continuously which still doesn't quite work
    # await luba_client.send_todev_ble_sync(2)
    # await luba_client.send_ble_alive()
    print("joystick code")
    joystick = JoystickControl(None)
    joystick.run_controller()
    print("heartbeat code")
    # asyncio.run(ble_heartbeat(luba_client))
    print("end run?")


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.run(run())
    loop.run_forever()
