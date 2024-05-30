from typing import Callable, Optional

from pyluba.data.model.rapid_state import RapidState, RTKStatus
from pyluba.data.mqtt.status import StatusType


class BaseLuba:
    def __init__(self):
        self._rapid_state: Optional[RapidState] = None
        self.on_pos_change: Optional[Callable[[float, float, float], None]] = None
        self.on_rtk_change: Optional[Callable[[RTKStatus, float, int, int], None]] = None

        self.on_warning: Optional[Callable[[int], None]] = None

        self._status: Optional[StatusType] = None
        self.on_status_change: Optional[Callable[[StatusType], None]] = None

    def _set_rapid_state(self, state: RapidState):
        old_state = self._rapid_state
        self._rapid_state = state
        if old_state:
            if old_state.pos_x != state.pos_x or old_state.pos_y != state.pos_y or old_state.toward != state.toward:
                if self.on_pos_change:
                    self.on_pos_change(state.pos_x, state.pos_y, state.toward)
            if (
                    old_state.rtk_status != state.rtk_status or
                    old_state.rtk_age != state.rtk_age or
                    old_state.satellites_total != state.satellites_total or
                    old_state.satellites_l2 != state.satellites_l2):
                if self.on_rtk_change:
                    self.on_rtk_change(state.rtk_status, state.rtk_age, state.satellites_total, state.satellites_l2)

    def _set_status(self, status: StatusType):
        self._status = status
        if self.on_status_change:
            self.on_status_change(status)

    @property
    def pos_x(self) -> float:
        return self._rapid_state.pos_x if self._rapid_state is not None else None

    @property
    def pos_y(self) -> float:
        return self._rapid_state.pos_y if self._rapid_state is not None else None

    @property
    def rtk_status(self) -> RTKStatus:
        return self._rapid_state.rtk_status if self._rapid_state is not None else None

    @property
    def toward(self) -> float:
        return self._rapid_state.toward if self._rapid_state is not None else None

    @property
    def satellites_total(self) -> int:
        return self._rapid_state.satellites_total if self._rapid_state is not None else None

    @property
    def satellites_l2(self) -> int:
        return self._rapid_state.satellites_l2 if self._rapid_state is not None else None

    @property
    def rtk_age(self) -> float:
        return self._rapid_state.rtk_age if self._rapid_state is not None else None

    @property
    def lat_std(self) -> float:
        return self._rapid_state.lat_std if self._rapid_state is not None else None

    @property
    def lon_std(self) -> float:
        return self._rapid_state.lon_std if self._rapid_state is not None else None

    @property
    def pos_type(self) -> int:
        return self._rapid_state.pos_type if self._rapid_state is not None else None

    @property
    def pos_level(self) -> int:
        return self._rapid_state.pos_level if self._rapid_state is not None else None

    @property
    def zone_hash(self) -> int:
        return self._rapid_state.zone_hash if self._rapid_state is not None else None

    @property
    def status(self) -> Optional[StatusType]:
        return self._status
