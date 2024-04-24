import asyncio
from threading import Thread

from pyluba.data.model import GenerateRouteInformation
from pyluba.bluetooth.ble import LubaBLE
from pyluba.bluetooth.ble_message import BleMessage
from pyluba.event.event import BleNotificationEvent

bleNotificationEvt = BleNotificationEvent()


async def ble_heartbeat(luba_client):
    while True:
        # await luba_client.send_todev_ble_sync(1)
        # eventually send an event and update data from sync
        await asyncio.sleep(2)
        await luba_client.send_todev_ble_sync(1)
        # await luba_client.send_ble_alive()
        await asyncio.sleep(10.5)

class AsyncLoopThread(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()


async def run():
    bleLubaConn = LubaBLE(bleNotificationEvt)
    did_connect = await bleLubaConn.scanForLubaAndConnect()
    if not did_connect:
        return
    await bleLubaConn.notifications()
    client = bleLubaConn.getClient()
    luba_client = BleMessage(client)

    def handle_notifications(data:bytearray):
        result = luba_client.parseNotification(data)
        # print(result)
        if (result == 0):
            luba_client.parseBlufiNotifyData()
            luba_client.clearNotification()

    bleNotificationEvt.AddSubscribersForBleNotificationEvent(handle_notifications)
    # Run the ble heart beat in the background continuously which still doesn't quite work

    # loop_handler_bleheart = threading.Thread(target=), args=(), daemon=True)
    # await luba_client.send_ble_alive()

    # gets info about luba and some other stuff
    # await luba_client.get_all_boundary_hash_list(3)
    # await luba_client.get_all_boundary_hash_list(0)


    # get map data off Luba
    #8656065632562971511
    await asyncio.sleep(1)
    await luba_client.send_todev_ble_sync(1)
    await luba_client.send_ble_alive()

    # await luba_client.synchronize_hash_data(8656065632562971511)

    # problem one
    # await asyncio.sleep(1)
    # await luba_client.synchronize_hash_data(5326333396143256633)
    # await asyncio.sleep(1)
    # await luba_client.sendTodevBleSync()
    # await luba_client.send_ble_alive()
    # await luba_client.synchronize_hash_data(6316048569363781876)
    # probably gets paths
    # await luba_client.get_line_info(4)
    # await luba_client.get_hash_response(1, 1)
    """
        private final int knifeHeight = 70;
    private int pKnifeHeight = 0;
    private int taskMode = 3;
    private int line_mode = 1;
    private int path_space = 25;
    private float speed_task = 0.3f;
    private int ultraWave = 1;
    private int rainTactics = 1;
    private int knifeHeight_task = 70;
    private int path_angler = 0;
    oneHashs=[8656065632562971511], jobId=null, jobVer=0, rainTactics=1, jobMode=3, knifeHeight=70, speed=0.3, UltraWave=2, channelWidth=25, channelMode=1, toward=0, edgeMode=1
    """

    generate_route_information = GenerateRouteInformation(
        one_hashs=[8656065632562971511],
        rain_tactics=1,
        speed=.3,
        ultra_wave=2,
        toward=0, # is just angle
        knife_height=70,
        channel_mode=0, # line mode is grid single double or single2
        channel_width=25,
        job_mode=3, # taskMode
        edge_mode=1, # border laps
        path_order=0,
        obstacle_laps=0

    )
    """arrayList.add(new TaskModeBean(getContext().getString(C1006R.string.boxchoice_monday), 2, true, true));
        this.list.add(new TaskModeBean(getContext().getString(C1006R.string.boxchoice_tuesday), 3, false, true));
        this.list.add(new TaskModeBean(getContext().getString(C1006R.string.boxchoice_wednesday), 4, false, true));
        this.list.add(new TaskModeBean(getContext().getString(C1006R.string.boxchoice_thursday), 5, false, true));
        this.list.add(new TaskModeBean(getContext().getString(C1006R.string.boxchoice_friday), 6, false, true));
        this.list.add(new TaskModeBean(getContext().getString(C1006R.string.boxchoice_saturday), 7, false, true));
        this.list.add(new TaskModeBean(getContext().getString(C1006R.string.boxchoice_sunday), 1, false, false));
        this.se"""

    # await luba_client.generate_route_information(generate_route_information)
    # probably need to wait for this to finish before hitting start
    # await luba_client.start_job(30)
    # await luba_client.setbladeHeight(70)
    # await luba_client.send_todev_ble_sync()

    # await luba_client.get_device_info()
    # await luba_client.all_powerful_RW(0, 1, 1)
    await asyncio.sleep(5)
    # await luba_client.get_device_info()
    await luba_client.send_device_info()

    asyncio.run(await ble_heartbeat(luba_client))
    print("end run?")



if __name__ ==  '__main__':
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    asyncio.run(run())
    event_loop.run_forever()



