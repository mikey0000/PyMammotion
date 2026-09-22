"""Models for the cloud map backup endpoints under ``/device-server/v1/map/backup``.

Mirrors the app's ``BackupMap*`` beans (``map/entity`` and ``me/api`` in the 2.3.8
APK).  The mower uploads and downloads the map itself; these endpoints only start,
track and cancel that transfer, so every job is keyed by the backup's ``bizId``.

Backups belong to the account that made them, not to the mower: an account sees
only its own, even for a mower shared with another account that has backups of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Annotated

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


class BackupProgressType(IntEnum):
    """The ``type`` the app sends to ``/backup/progress`` (``BackupsMapActivity.ProgressType``)."""

    BACKUP = 1
    RESTORE = 2
    UPDATE = 3


#: ``state`` on a progress reply once the transfer has finished.
BACKUP_STATE_DONE = 1

#: ``state`` values on a backup record while the mower is still transferring it;
#: the app reattaches to the running job instead of starting another.
BACKUP_STATES_IN_PROGRESS = frozenset({4, 5})


@dataclass
class BackupMapResult(DataClassORJSONMixin):
    """The job id every backup reply carries (``BackupMapBaseResponse``).

    The bean's ``result``/``errorCode``/``errorMessage`` are filled in by the app,
    not the server: a refusal arrives as ``data: null`` with the reason in the
    envelope's ``code`` and ``msg`` (e.g. 60215 robot busy, 60216 firmware too old).
    """

    biz_id: Annotated[str, Alias("bizId")] = ""

    class Config(BaseConfig):
        allow_deserialization_not_by_alias = True


@dataclass
class BackupMapCheck(BackupMapResult):
    """A ``/backup/check`` reply."""

    has_back: Annotated[bool, Alias("hasBack")] = False


@dataclass
class BackupMapProgress(BackupMapResult):
    """A ``/backup/progress`` reply; ``state == BACKUP_STATE_DONE`` means finished."""

    progress: int | None = None
    state: int | None = None
    confirmed: bool | None = None


@dataclass
class BackupMapItem(BackupMapResult):
    """One stored backup, or one device offered as a backup source or restore target.

    ``device_id`` is what the other backup endpoints take as ``deviceId``, so callers
    should look it up here by ``device_name`` rather than assume it is the iot id.
    """

    name: str = ""
    device_id: Annotated[str, Alias("deviceId")] = ""
    device_name: Annotated[str, Alias("deviceName")] = ""
    nick_name: Annotated[str | None, Alias("nickName")] = None
    product_key: Annotated[str | None, Alias("productKey")] = None
    user_id: Annotated[str | None, Alias("userId")] = None
    area: int | None = None
    state: int | None = None
    progress: int | None = None
    operation_stage: Annotated[int | None, Alias("operationStage")] = None
    task: int | None = None
    user_backup_quota: Annotated[int | None, Alias("userBackupQuota")] = None
    backup_time: Annotated[int | None, Alias("backupTime")] = None
    hash_code: Annotated[str | None, Alias("hashCode")] = None
    correction_value: Annotated[str | None, Alias("correctionValue")] = None
    origin_data: Annotated[str | None, Alias("originData")] = None
    control_file_link: Annotated[str | None, Alias("controlFileLink")] = None
