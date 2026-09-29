"""Builders for the ``RemoteDriveSession`` unit tests (``test_remote_drive*.py``).

Kept apart from ``_helpers.py`` so the reducer tests do not import the session module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pymammotion.device.handle import DeviceHandle
from pymammotion.device.remote_drive import RemoteDriveEvent, RemoteDriveEventKind, RemoteDriveSession
from pymammotion.http.model.fpv_control import FpvControl
from pymammotion.http.model.http import Response
from pymammotion.proto import DrvSessionCtrlAck, DrvSessionCtrlResult, LubaMsg, MctlDriver
from pymammotion.transport.base import TransportType
from tests._helpers import make_mock_handle, make_mock_transport
from tests.unit.device._fakes import FakeDriveClock, FrameSink, ScriptedTokens


def make_grant(**data: Any) -> Response[FpvControl]:
    """A granted control token (``deviceResult`` 0); keyword overrides use the wire's camelCase keys."""
    wire: dict[str, Any] = {"deviceResult": 0, "token": "ctl-1", "expireIn": 600, "timeoutExit": 10}
    wire.update(data)
    return Response(code=0, msg="success", data=FpvControl.from_dict(wire))


def make_session_ack(ctrl_seq: int, *, result: int = 0, **fields: Any) -> LubaMsg:
    """A ``toapp_session_ctrl_ack`` frame as the mower sends it."""
    ack = DrvSessionCtrlAck(ctrl_seq=ctrl_seq, result=DrvSessionCtrlResult(result), **fields)
    return LubaMsg(driver=MctlDriver(toapp_session_ctrl_ack=ack))


@dataclass
class DriveRig:
    """A session wired to a real handle, a fake clock, a recording send and scripted tokens."""

    session: RemoteDriveSession
    handle: DeviceHandle
    clock: FakeDriveClock
    sink: FrameSink
    tokens: ScriptedTokens
    events: list[RemoteDriveEvent] = field(default_factory=list)

    @property
    def kinds(self) -> list[RemoteDriveEventKind]:
        """The kind of every event the session has emitted, in order."""
        return [event.kind for event in self.events]

    async def ack(self, ctrl_seq: int, *, result: int = 0, **fields: Any) -> None:
        """Deliver an ack through the handle's broker, then run whatever it scheduled for now."""
        await self.handle.broker.on_message(make_session_ack(ctrl_seq, result=result, **fields))
        await self.clock.advance(0)


def make_drive_rig(
    *,
    grant: Response[FpvControl] | None = None,
    transports: tuple[TransportType, ...] = (TransportType.CLOUD_ALIYUN,),
    require_video: bool = False,
    invoke_timeout: float | None = None,
) -> DriveRig:
    """A remote-drive session over a real handle; *transports* chooses what the handle has registered.

    Without *invoke_timeout* the session keeps its own default.
    """
    kinds = {t: make_mock_transport(t) for t in transports}
    handle = make_mock_handle(
        device_name="Luba-VS6ABCDE",
        mqtt_transport=kinds.get(TransportType.CLOUD_ALIYUN),
        ble_transport=kinds.get(TransportType.BLE),
    )
    clock = FakeDriveClock()
    sink = FrameSink()
    tokens = ScriptedTokens(requests=[grant if grant is not None else make_grant()])
    timeout = {} if invoke_timeout is None else {"invoke_timeout": invoke_timeout}
    session = RemoteDriveSession(handle, tokens=tokens, send=sink, clock=clock, require_video=require_video, **timeout)
    rig = DriveRig(session=session, handle=handle, clock=clock, sink=sink, tokens=tokens)

    async def _record(event: RemoteDriveEvent) -> None:
        rig.events.append(event)

    session.subscribe(_record)
    return rig


async def make_active_rig(**kwargs: Any) -> DriveRig:
    """A rig whose session has its token, has been confirmed, and has sent nothing but its keep-alive."""
    rig = make_drive_rig(**kwargs)
    assert await rig.session.start()
    await rig.session.confirm()
    return rig
