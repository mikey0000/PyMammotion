import asyncio
import threading
from luba_desktop.blufi_impl import Blufi
import pyjoystick
from pyjoystick.sdl2 import Key, Joystick, run_event_loop
from pyjoystick.utils import PeriodicThread
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
    blade_height = 25

    def __init__(self, client: Blufi):
        self._client = client
        self._curr_time = timer()

    def _movement_finished(self):
        self.ignore_events = False
        
    def run_movement(self):
        if self.linear_speed != 0 or self.angular_speed != 0:
            asyncio.run(
                self._client.transformBothSpeeds(
                    self.linear_speed,
                    self.angular_speed,
                    self.linear_percent,
                    self.angular_percent,
                )
            )

    def run_controller(self):
        
        def print_add(joy):
            print("Added", joy)

        def print_remove(joy):
            print("Removed", joy)

        def key_received(key):
            self.handle_key_recieved(key)

        # run_event_loop(print_add, print_remove, key_received)
        repeater = pyjoystick.HatRepeater(
            first_repeat_timeout=0.2, repeat_timeout=0.03, check_timeout=0.01
        )

        mngr = pyjoystick.ThreadEventManager(
            event_loop=run_event_loop,
            handle_key_event=key_received,
            add_joystick=print_add,
            remove_joystick=print_remove,
            button_repeater=repeater,
        )
        mngr.start()

        self.worker = PeriodicThread(0.2, self.run_movement, name='luba-process_movements')
        self.worker.alive = mngr.alive  # stop when this event stops
        self.worker.daemon = True
        self.worker.start()

    def handle_key_recieved(self, key):
        if key.keytype is Key.BUTTON and key.value == 1:
            print(key, "-", key.keytype, "-", key.number, "-", key.value)
            if key.number == 0:  # x
                asyncio.run(self._client.returnToDock())
            if key.number == 1:
                asyncio.run(self._client.leaveDock())
            if key.number == 3:
                asyncio.run(self._client.setBladeControl(1))
            if key.number == 2:
                asyncio.run(self._client.setBladeControl(0))
            if key.number == 9:
                # lower knife height
                if self.blade_height > 25:
                    self.blade_height -= 5
                    asyncio.run(self._client.setbladeHeight(self.blade_height))
            if key.number == 10:
                # raise knife height
                if self.blade_height < 60:
                    self.blade_height += 5
                    asyncio.run(self._client.setbladeHeight(self.blade_height))

        if key.keytype is Key.AXIS:
            if key.value > 0.09 or key.value < -0.09:
                print(key, "-", key.keytype, "-", key.number, "-", key.value)
                # ignore events for 200ms
                elapsed_time = timer()
                if (elapsed_time - self._curr_time) < 0.2:
                    return
                else:
                    self._curr_time = timer()

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

                    case 3:  # right  (left right)
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

            else:

                if self.linear_speed != 0 or self.angular_speed != 0:
                    self.linear_speed = 0.0
                    self.linear_percent = 0
                    self.angular_speed = 0.0
                    self.angular_percent = 0

                    asyncio.run(
                        self._client.transformBothSpeeds(
                            self.linear_speed,
                            self.angular_speed,
                            self.linear_percent,
                            self.angular_percent,
                        )
                    )
