"""The ``/device-server/v1/map/backup`` endpoints: cloud map backup and restore.

Request bodies and verbs mirror ``MapApiService`` in the 2.3.8 APK; the reply
shapes mirror its ``BackupMap*`` beans.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest

from pymammotion.http.model.http import UnauthorizedExceptionError
from pymammotion.http.model.map_backup import BACKUP_STATE_DONE, BackupProgressType
from tests.unit._helpers import make_http_posting

BIZ_ID = "1987654321"


def _ok(data: object) -> dict:
    return {"code": 0, "msg": "success", "data": data}


def _backup(**overrides: object) -> dict:
    record = {
        "bizId": BIZ_ID,
        "name": "Map1",
        "deviceId": "dev-1",
        "deviceName": "Luba-VSLKJX",
        "nickName": None,
        "productKey": "a1pvCnb3PPu",
        "area": 812,
        "state": 1,
        "progress": 100,
        "backupTime": 1_758_000_000_000,
        "userBackupQuota": 5,
    }
    record.update(overrides)
    return record


async def test_the_backup_list_parses_and_tolerates_nulls() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _ok([_backup(), _backup(bizId="2", controlFileLink=None)]))

    response = await http.get_map_backups()

    assert response.data is not None
    first = response.data[0]
    assert (first.biz_id, first.device_name, first.area, first.backup_time) == (
        BIZ_ID,
        "Luba-VSLKJX",
        812,
        1_758_000_000_000,
    )
    assert first.nick_name is None, "a null string field must parse rather than reject the list"
    assert session.get.await_args.args[0].endswith("/device-server/v1/map/backup/list")


async def test_the_backup_device_list_is_a_post() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _ok([_backup()]))

    await http.get_map_backup_devices()

    assert session.post.await_args.args[0].endswith("/device-server/v1/map/backup/backup/list")


async def test_starting_a_backup_sends_the_app_body_and_returns_the_job_id() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _ok(_backup(state=2, progress=0)))

    response = await http.start_map_backup("dev-1", "Map1", '{"OffsetX":0.0,"OffsetY":0.0}')

    assert response.data is not None and response.data.biz_id == BIZ_ID
    assert session.post.await_args.args[0].endswith("/device-server/v1/map/backup")
    assert session.post.await_args.kwargs["json"] == {
        "deviceId": "dev-1",
        "name": "Map1",
        "correctionValue": '{"OffsetX":0.0,"OffsetY":0.0}',
    }


async def test_a_backup_reply_without_result_parses() -> None:
    """A live start reply carries the record but no ``result`` — the app adds that."""
    http, _ = make_http_posting(HTTPStatus.OK.value, _ok({"bizId": BIZ_ID, "name": "Map1", "state": 2}))

    response = await http.start_map_backup("dev-1", "Map1")

    assert response.data is not None and response.data.biz_id == BIZ_ID


async def test_a_refused_backup_carries_the_reason_in_the_envelope() -> None:
    """A refusal is ``data: null`` with the reason in ``code``/``msg``."""
    http, _ = make_http_posting(HTTPStatus.OK.value, {"code": 60215, "msg": "robot busy", "data": None})

    response = await http.start_map_backup("dev-1", "Map1")

    assert response.data is None
    assert (response.code, response.msg) == (60215, "robot busy")


async def test_overwriting_a_backup_is_a_put() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _ok(_backup()))

    await http.update_map_backup(BIZ_ID, "dev-1", "Map1")

    session.post.assert_not_awaited()
    assert session.put.await_args.args[0].endswith("/device-server/v1/map/backup")
    assert session.put.await_args.kwargs["json"]["bizId"] == BIZ_ID


async def test_deleting_a_backup_is_a_delete_on_its_id() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _ok(True))

    response = await http.delete_map_backup(BIZ_ID)

    assert response.data is True
    assert session.delete.await_args.args[0].endswith(f"/device-server/v1/map/backup/{BIZ_ID}")
    assert "json" not in session.delete.await_args.kwargs


async def test_restoring_sends_the_target_device_and_backup() -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _ok({"bizId": BIZ_ID}))

    response = await http.restore_map_backup("dev-2", BIZ_ID)

    assert response.data is not None and response.data.biz_id == BIZ_ID
    assert session.post.await_args.args[0].endswith("/device-server/v1/map/backup/recovery")
    assert session.post.await_args.kwargs["json"] == {"deviceId": "dev-2", "bizId": BIZ_ID}


async def test_progress_sends_the_app_type_code() -> None:
    http, session = make_http_posting(
        HTTPStatus.OK.value, _ok({"progress": 100, "state": BACKUP_STATE_DONE, "confirmed": True})
    )

    response = await http.get_map_backup_progress(BIZ_ID, BackupProgressType.RESTORE)

    assert response.data is not None and response.data.state == BACKUP_STATE_DONE
    assert session.post.await_args.kwargs["json"] == {"bizId": BIZ_ID, "type": 2}


async def test_the_check_reply_parses_has_back() -> None:
    http, _ = make_http_posting(HTTPStatus.OK.value, _ok({"hasBack": True}))

    response = await http.has_map_backup("dev-1")

    assert response.data is not None and response.data.has_back


@pytest.mark.parametrize(
    ("call", "path"),
    [
        ("cancel_map_backup", "/cancel/backup"),
        ("cancel_map_restore", "/cancel/recovery"),
    ],
)
async def test_cancel_endpoints(call: str, path: str) -> None:
    http, session = make_http_posting(HTTPStatus.OK.value, _ok(True))

    response = await getattr(http, call)("dev-1", BIZ_ID)

    assert response.data is True
    assert session.post.await_args.args[0].endswith(f"/device-server/v1/map/backup{path}")


async def test_a_401_on_a_put_is_raised() -> None:
    """The verb override must keep the shared auth guard."""
    http, _ = make_http_posting(HTTPStatus.UNAUTHORIZED.value, {"code": 401, "msg": "unauthorized"})

    with pytest.raises(UnauthorizedExceptionError):
        await http.update_map_backup(BIZ_ID, "dev-1", "Map1")
