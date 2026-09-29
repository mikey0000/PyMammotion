"""The "continue last job" builder: ``MctlNav.todev_work_report_start_working_msg`` (field 65).

Mirrors ``MACommandApiHelper.continueLastWork(accountId, workId)`` in app 2.3.20.30: account id,
the cloud work report's work id, the send time in milliseconds as ``stamp`` and ``result=1``;
``type`` is never set.  The payload is pinned byte for byte because the device only sees bytes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import time_machine

from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg

#: MctlNav field 65, length-delimited: (65 << 3) | 2 = 522 -> varint 0x8A 0x04.
_FIELD_65_TAG = b"\x8a\x04"


@time_machine.travel(datetime(1970, 1, 1, 0, 0, 1, tzinfo=UTC), tick=False)
def test_continue_last_job_sends_account_work_id_stamp_and_result_1_on_nav_field_65() -> None:
    payload = MammotionCommand("Luba-VS6ABCDE", user_account=42).continue_last_job(work_id=7)
    # accountID=42 (0x08 0x2A), work_id=7 (0x10 0x07), stamp=1000 ms (0x18, 1000 -> varint 0xE8 0x07),
    # result=1 (0x20 0x01); no field 5.
    inner = b"\x08\x2a" + b"\x10\x07" + b"\x18\xe8\x07" + b"\x20\x01"

    assert bytes(LubaMsg().parse(payload).nav) == _FIELD_65_TAG + bytes([len(inner)]) + inner
