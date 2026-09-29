"""Wire layout of the ``mctrl_driver.proto`` fields added from app 2.3.20.30.

Session-based manual drive (``MctlDriver`` fields 15-21) and the drive-link ``channel`` on
``DrvMotionCtrl``.  Frames are hand-encoded from explicit tags so a renumbered field fails here
rather than round-tripping through its own generated class.
"""

from __future__ import annotations

import betterproto2
import pytest

from pymammotion.proto import (
    DrvCtrlLink,
    DrvMotionCtrl,
    DrvMowCtrlByHand,
    DrvSessionCtrlReq,
    DrvSessionCtrlResult,
    DrvSessionExitAppNfty,
    DrvSessionExitReason,
    MctlDriver,
)

#: MctlDriver fields 18-21, message: (n << 3) | 2 = 146 / 154 / 162 / 170 -> 0x92 / 0x9A / 0xA2 / 0xAA, then 0x01.
_SESSION_CTRL_REQ_TAG = b"\x92\x01"
_SESSION_CTRL_ACK_TAG = b"\x9a\x01"
_SESSION_EXIT_APP_NFTY_TAG = b"\xa2\x01"
_SESSION_EXIT_NFTY_TAG = b"\xaa\x01"


def _parse(payload: bytes) -> tuple[str, object]:
    return betterproto2.which_one_of(MctlDriver().parse(payload), "SubDrvMsg")


@pytest.mark.parametrize(
    ("tag", "field"),
    [
        (b"\x7a", "todev_devmotion_ctrl_test"),  # (15 << 3) | 2 = 122
        (b"\x82\x01", "toapp_devmotion_ctrl_ack"),  # 130
        (b"\x8a\x01", "drv_buzz_enable"),  # 138
        (_SESSION_CTRL_REQ_TAG, "todev_session_ctrl_req"),
        (_SESSION_CTRL_ACK_TAG, "toapp_session_ctrl_ack"),
        (_SESSION_EXIT_APP_NFTY_TAG, "todev_session_exit_nfty"),
        (_SESSION_EXIT_NFTY_TAG, "toapp_session_exit_nfty"),
    ],
    ids=lambda value: value if isinstance(value, str) else value.hex(),
)
def test_mctl_driver_reads_the_new_oneof_fields_15_to_21(tag: bytes, field: str) -> None:
    name, _ = _parse(tag + b"\x00")

    assert name == field


@pytest.mark.parametrize(
    ("raw", "link"),
    [(1, DrvCtrlLink.DRV_CTRL_BLE), (2, DrvCtrlLink.DRV_CTRL_IOT), (3, DrvCtrlLink.DRV_CTRL_LAN)],
    ids=["ble", "iot", "lan"],
)
def test_motion_ctrl_carries_the_drive_link_on_field_3(raw: int, link: DrvCtrlLink) -> None:
    assert bytes(DrvMotionCtrl(set_linear_speed=1, channel=link)) == b"\x08\x01" + b"\x18" + bytes([raw])


def test_mow_ctrl_by_hand_reads_edge_ctrl_from_field_5() -> None:
    assert DrvMowCtrlByHand().parse(b"\x28\x01").edge_ctrl == 1  # (5 << 3) = 40 -> 0x28.


def test_session_ctrl_request_encodes_fields_1_to_7_in_order() -> None:
    request = DrvSessionCtrlReq(
        ctrl_seq=1,
        set_linear_speed=2,
        set_angular_speed=3,
        channel=DrvCtrlLink.DRV_CTRL_IOT,
        app_send_ts_ms=1000,
        vehicle_send_ts_ms=2000,
        token="t",
    )
    # uint64 1000 -> 0xE8 0x07, 2000 -> 0xD0 0x0F; token is field 7 string (0x3A).
    expected = b"\x08\x01\x10\x02\x18\x03\x20\x02" + b"\x28\xe8\x07" + b"\x30\xd0\x0f" + b"\x3a\x01t"

    assert (
        bytes(MctlDriver(todev_session_ctrl_req=request)) == _SESSION_CTRL_REQ_TAG + bytes([len(expected)]) + expected
    )


def test_session_ctrl_ack_reads_every_field() -> None:
    # fenceExceedDistance is a float on field 6 (tag 0x35): 1.5f = 00 00 C0 3F.
    ack = (
        b"\x08\x01\x10\xe8\x07\x18\xd0\x0f"
        + b"\x20\x08"  # result = OUT_OF_FENCE
        + b"\x28\x01"
        + b"\x35\x00\x00\xc0\x3f"
        + b"\x38\x2a\x40\x07"
    )
    _, value = _parse(_SESSION_CTRL_ACK_TAG + bytes([len(ack)]) + ack)

    assert (value.ctrl_seq, value.app_send_ts_ms, value.vehicle_send_ts_ms) == (1, 1000, 2000)
    assert value.result is DrvSessionCtrlResult.DRV_SESSION_CTRL_OUT_OF_FENCE
    assert (value.localization_valid, value.fence_exceed_distance) == (True, 1.5)
    assert (value.measured_delay_ms, value.preempt_account) == (42, 7)


def test_session_exit_from_the_app_encodes_token_and_channel() -> None:
    nfty = DrvSessionExitAppNfty(token="t", channel=DrvCtrlLink.DRV_CTRL_BLE)

    assert bytes(MctlDriver(todev_session_exit_nfty=nfty)) == _SESSION_EXIT_APP_NFTY_TAG + b"\x05\x0a\x01t\x10\x01"


def test_session_exit_from_the_device_reads_reason_and_preempting_account() -> None:
    _, value = _parse(_SESSION_EXIT_NFTY_TAG + b"\x04\x08\x01\x10\x05")

    assert (value.reason, value.preempt_account) == (DrvSessionExitReason.DRV_SESSION_EXIT_BLE_PREEMPT, 5)
