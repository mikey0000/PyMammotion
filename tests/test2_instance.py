import asyncio
import logging
from threading import Thread

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from pymammotion.event.event import BleNotificationEvent
from pymammotion.mammotion.devices.mammotion import MammotionBaseBLEDevice, has_field
from pymammotion.proto.mctrl_sys import MctlSys, RptAct, RptInfoType

bleNotificationEvt = BleNotificationEvent()

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


async def ble_heartbeat(luba_client):
    while True:
        # await luba_client.send_todev_ble_sync(1)
        # eventually send an event and update data from sync
        # await asyncio.sleep(1)
        await asyncio.sleep(0.01)


class AsyncLoopThread(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()


async def scan_for_luba() -> BLEDevice:
    scanner = BleakScanner()

    def scan_callback(device, advertising_data):
        # TODO: do something with incoming data
        print(device)
        print(advertising_data)
        if device.address == "90:38:0C:6E:EE:9E":
            return True
        if advertising_data.local_name and "Luba-" in advertising_data.local_name:
            return True
        return False

    device = await scanner.find_device_by_filter(scan_callback)
    if device is not None:
        return device


async def run(loop):
    luba_device = await scan_for_luba()
    if luba_device is None:
        print("failed to find a Luba")
        return

    luba_ble = MammotionBaseBLEDevice(
        device=luba_device
    )

    await asyncio.sleep(2)
    await luba_ble.start_sync(0)
    # await luba_ble.start_map_sync()
    #await asyncio.sleep(2)
    # print(luba_ble.luba_msg.sys.toapp_report_data.dev)
    # if has_field(luba_ble.luba_msg.sys.toapp_report_data.dev):
    #     dev = luba_ble.luba_msg.sys.toapp_report_data.dev
    #     if dev.sys_status == 11:
    #         await luba_ble.command("start_job")
    # await luba_ble.command("get_report_cfg")

    print(luba_ble.luba_msg.sys.toapp_report_data.dev.charge_state)
    await asyncio.sleep(5)
    await luba_ble.command("get_report_cfg")
    await asyncio.sleep(2)
    print(luba_ble.luba_msg.sys.toapp_report_data)
    print(luba_ble.luba_msg.sys.toapp_report_data.dev.charge_state)
    # await luba_ble.command("send_todev_ble_sync", **{'sync_type': 2})
    #print(luba_ble.raw_data) # unreliable
    # print(has_field(luba_ble.luba_msg.sys.toapp_report_data.dev))
    # print(luba_ble.luba_msg.sys.toapp_report_data.dev.battery_val)
    await asyncio.sleep(5)
    print(luba_ble.luba_msg.sys.toapp_report_data.dev.charge_state)
    # await luba_ble.command("return_to_dock")
    # await luba_ble.command("get_hash_response", total_frame=1, current_frame=1)
    counter = 30
    # while (counter > 0):
    #     luba_device = await scan_for_luba()
    #     if luba_device is not None:
    #         luba_ble.update_device(luba_device)
    #         await luba_ble.start_sync(0)
    #     await asyncio.sleep(10)
    #     # await luba_ble._execute_disconnect_with_lock()
    #     await asyncio.sleep(60)
    #
    #     counter -= 1

    # app_request_cover_paths_t use hashlist from ??

    # asyncio.run(await ble_heartbeat(luba_ble))
    # await luba_ble.command("synchronize_hash_data", hash_num=25410289481558284)
    await asyncio.sleep(20)
    print("end run?")
    print(luba_ble.luba_msg.map)



if __name__ == '__main__':
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    asyncio.run(run(event_loop))
    event_loop.run_forever()
