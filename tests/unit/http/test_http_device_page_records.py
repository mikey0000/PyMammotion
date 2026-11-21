"""One device-page record the model cannot decode must not hide every other device.

``DeviceRecord`` requires ``bindTime`` and ``createTime``, which the app's own bean
does not (it defaults every field, and never reads ``createTime``).  A single record
missing one failed the whole ``Response[DeviceRecords]`` decode, so the page fetch
was treated as failed and no device on it was registered — a newly bound mower
never appeared, and on a first login the account came up with no devices at all.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest

from tests.unit._helpers import device_record_json, make_http_posting

KNOWN = "Luba-VSKNOWN1"
NEW = "Yuka-MNNEW001"


def _without(record: dict, key: str) -> dict:
    return {k: v for k, v in record.items() if k != key}


@pytest.mark.regression
@pytest.mark.parametrize(
    "new_record",
    [
        pytest.param(_without(device_record_json(NEW, "iot-new"), "createTime"), id="no-createTime"),
        pytest.param({**device_record_json(NEW, "iot-new"), "bindTime": None}, id="null-bindTime"),
    ],
)
async def test_a_record_missing_an_unused_field_still_lists_every_device(new_record: dict) -> None:
    """The decode failed for the whole page, so neither device was listed."""
    body = {
        "code": 0,
        "msg": "success",
        "data": {"records": [device_record_json(KNOWN, "iot-known"), new_record], "total": 2},
    }
    http, _ = make_http_posting(HTTPStatus.OK.value, body)

    await http.get_user_device_page()

    assert http.device_records is not None
    assert [r.device_name for r in http.device_records.records] == [KNOWN, NEW]
