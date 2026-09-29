"""Remote-drive session builders on the driver mixin: ``session_ctrl`` and ``session_exit_notify``.

Mirror ``MACommandApiHelper.sendSessionControl`` / ``sendSessionExitNotify`` in app 2.3.20.30:
``MctlDriver`` field 18 (``DrvSessionCtrlReq``) with ``channel = DRV_CTRL_IOT`` on every frame, and
field 20 (``DrvSessionExitAppNfty``) carrying the token and the link the session ran on.  Both ride
an ``EMBED_DRIVER`` request to the main controller.  Payloads are pinned byte for byte because the
device only sees bytes.
"""

from __future__ import annotations

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import DrvCtrlLink, LubaMsg, MsgAttr, MsgCmdType, MsgDevice

#: MctlDriver field 18, length-delimited: (18 << 3) | 2 = 146 -> varint 0x92 0x01.
_FIELD_18_TAG = b"\x92\x01"
#: MctlDriver field 20: (20 << 3) | 2 = 162 -> varint 0xA2 0x01.
_FIELD_20_TAG = b"\xa2\x01"


def _command() -> MammotionCommand:
    return MammotionCommand("Luba-VS6ABCDE", user_account=42)


def test_a_session_frame_carries_every_field_on_driver_field_18() -> None:
    payload = _command().session_ctrl(
        ctrl_seq=1, linear_speed=300, angular_speed=-45, app_send_ts_ms=1000, vehicle_send_ts_ms=7, token="t"
    )
    inner = (
        b"\x08\x01"  # ctrlSeq=1
        + b"\x10\xac\x02"  # setLinearSpeed=300
        + b"\x18\xd3\xff\xff\xff\xff\xff\xff\xff\xff\x01"  # setAngularSpeed=-45 (int32, sign-extended)
        + b"\x20\x02"  # channel=DRV_CTRL_IOT
        + b"\x28\xe8\x07"  # appSendTsMs=1000
        + b"\x30\x07"  # vehicleSendTsMs=7
        + b"\x3a\x01t"  # token="t"
    )

    assert bytes(LubaMsg().parse(payload).driver) == _FIELD_18_TAG + bytes([len(inner)]) + inner


def test_a_keep_alive_frame_carries_only_the_channel_the_timestamp_and_the_token() -> None:
    """Sequence 0, zero speed and no echoed vehicle time are proto3 defaults and vanish from the wire."""
    payload = _command().session_ctrl(
        ctrl_seq=0, linear_speed=0, angular_speed=0, app_send_ts_ms=1000, vehicle_send_ts_ms=0, token="t"
    )
    inner = b"\x20\x02" + b"\x28\xe8\x07" + b"\x3a\x01t"

    assert bytes(LubaMsg().parse(payload).driver) == _FIELD_18_TAG + bytes([len(inner)]) + inner


def test_a_session_frame_is_a_driver_request_to_the_main_controller() -> None:
    msg = LubaMsg().parse(
        _command().session_ctrl(
            ctrl_seq=3, linear_speed=0, angular_speed=0, app_send_ts_ms=1, vehicle_send_ts_ms=0, token="t"
        )
    )

    assert (msg.msgtype, msg.rcver, msg.msgattr) == (MsgCmdType.EMBED_DRIVER, MsgDevice.DEV_MAINCTL, MsgAttr.REQ)


def test_an_exit_notify_carries_the_token_and_the_iot_channel_on_driver_field_20() -> None:
    inner = b"\x0a\x03abc" + b"\x10\x02"

    payload = _command().session_exit_notify(token="abc")

    assert bytes(LubaMsg().parse(payload).driver) == _FIELD_20_TAG + bytes([len(inner)]) + inner


def test_an_exit_notify_names_the_link_it_is_given() -> None:
    msg = LubaMsg().parse(_command().session_exit_notify(token="abc", channel=DrvCtrlLink.DRV_CTRL_BLE))

    assert msg.driver.todev_session_exit_nfty.channel is DrvCtrlLink.DRV_CTRL_BLE
