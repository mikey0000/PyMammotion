"""``MammotionClient.mammotion_device_list`` — the Mammotion-direct devices the host lists."""

from __future__ import annotations

import pytest

from pymammotion.account.registry import AccountSession
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import DeviceRecord, DeviceRecords
from tests._helpers import make_bare_client
from tests.unit._helpers import device_record_json

ACCOUNT = "user@test.com"


@pytest.mark.parametrize(
    ("records", "listed"),
    [
        pytest.param(None, [], id="unknown"),
        pytest.param(
            DeviceRecords(records=[DeviceRecord.from_dict(device_record_json("Yuka-LISTED", "iot-listed"))]),
            ["Yuka-LISTED"],
            id="known",
        ),
    ],
)
def test_the_mammotion_device_list_reflects_the_held_records(records: DeviceRecords | None, listed: list[str]) -> None:
    http = MammotionHTTP()
    http.device_records = records
    session = AccountSession(account_id=ACCOUNT, email=ACCOUNT, password="pw")
    session.mammotion_http = http
    client = make_bare_client(session)

    assert [d.device_name for d in client.mammotion_device_list] == listed
