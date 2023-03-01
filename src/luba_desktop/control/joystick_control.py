
import asyncio
from luba_desktop.blufi_impl import Blufi
from pyjoystick.sdl2 import Key, Joystick, run_event_loop
from timeit import default_timer as timer

from luba_desktop.event.event import MoveEvent

import nest_asyncio

nest_asyncio.apply()

class JoystickControl:
    """Joystick class for controlling Luba with a joystick"""

    angular_percent = 0
    linear_percent = 0
    linear_speed = 0
    angular_speed = 0
    ignore_events = False

    def __init__(self, client: Blufi, moveEvt: MoveEvent):
        self._client = client
        self._moveEvt = moveEvt

        self._moveEvt.AddSubscribersForMoveFinishedEvent(self._movement_finished)

    def _movement_finished(self):
        self.ignore_events = False

    def run_controller(self):
        def print_add(joy):
            print("Added", joy)

        def print_remove(joy):
            print("Removed", joy)

        def key_received(key):
            self.handle_key_recieved(key)

        run_event_loop(print_add, print_remove, key_received)

    def handle_key_recieved(self, key):
        if key.keytype is Key.BUTTON and key.value == 1:
                print(key, "-", key.keytype, "-", key.number, "-", key.value)
                if key.number == 0:  # x
                    asyncio.run(self._client.returnToDock())
                if key.number == 1:
                    asyncio.run(self._client.leaveDock())
                if key.number == 3:
                    asyncio.run(self._client.setbladeControl(1))
                if key.number == 2:
                    asyncio.run(self._client.setBladeControl(0))
                if key.number == 9:
                    # lower knife height
                    pass
                if key.number == 10:
                    # raise knife height
                    pass

        if key.keytype is Key.AXIS:
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


                if(not self.ignore_events):
                    # changes on event from blufi
                    self.ignore_events = True
                    asyncio.run(
                        self._client.transformBothSpeeds(
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
