from dataclasses import dataclass, field

from mashumaro.mixins.orjson import DataClassORJSONMixin

from pymammotion.data.model.enums import TaskAreaStatus


@dataclass
class WorkTaskEvent(DataClassORJSONMixin):
    """Work task progress event mapping zone hashes to their current mowing status."""

    hash_area_map: dict[int, TaskAreaStatus] = field(default_factory=dict)
    ids: list[int] = field(default_factory=list)


@dataclass
class BladeHeightEvent(DataClassORJSONMixin):
    """In-progress blade height change event (proto DrvKnifeChangeReport).

    is_start: 1 when a height change begins, 0 when complete
    start_height / end_height: requested height range
    cur_height: current position during the change
    """

    is_start: int = 0
    start_height: int = 0
    end_height: int = 0
    cur_height: int = 0


#: ``DrvUpgradeReport.result`` sentinel for "upgrade finished successfully".
#:
#: The device streams these reports throughout an OTA.  Per the APK
#: (``FirmwareUpdateKTView.setProgress`` / ``MACarDataManager`` case 10), the code is
#: **not** a progress flag: ``0`` marks *completion* — it is the branch where the app
#: pins progress to 100 and writes ``version`` into its installed-firmware cache — while
#: an in-flight tick carries ``2``.  ``1`` and any negative value route to
#: ``setDeviceErrorMsg`` → ``setUpdateFailure``, i.e. the upgrade failed.
OTA_RESULT_SUCCESS: int = 0

#: ``DrvUpgradeReport.result`` sentinel for a failed upgrade.  Negative codes are
#: device-specific error numbers and are treated as failures too — see :meth:`OTAProgress.is_failed`.
OTA_RESULT_FAILED: int = 1


@dataclass
class OTAProgress(DataClassORJSONMixin):
    """Firmware OTA upgrade progress (proto DrvUpgradeReport).

    progress: 0–100 percentage
    result: outcome code — see :data:`OTA_RESULT_SUCCESS` for the (counter-intuitive)
        encoding.  Use :attr:`is_complete` / :attr:`is_failed` / :attr:`is_in_progress`
        rather than comparing the raw value at call sites.
    devname: which sub-component is being upgraded
    version: target firmware version string
    message: free-text stage description, e.g. ``"dl fw:SocMidware, 54651495/14861"``
    """

    devname: str = ""
    otaid: str = ""
    version: str = ""
    progress: int = 0
    result: int = 0
    message: str = ""
    recv_cnt: int = 0

    @property
    def is_complete(self) -> bool:
        """True when the device reported the upgrade finished successfully."""
        return self.result == OTA_RESULT_SUCCESS

    @property
    def is_failed(self) -> bool:
        """True when the device reported the upgrade failed (``1``, or a negative error code)."""
        return self.result == OTA_RESULT_FAILED or self.result < 0

    @property
    def is_in_progress(self) -> bool:
        """True while the upgrade is still running (any code above the failure sentinel)."""
        return self.result > OTA_RESULT_FAILED


@dataclass
class Events(DataClassORJSONMixin):
    """Container for all device event types tracked during a mowing session."""

    work_tasks_event: WorkTaskEvent = field(default_factory=WorkTaskEvent)
    blade_height_event: BladeHeightEvent = field(default_factory=BladeHeightEvent)
    ota_progress: OTAProgress = field(default_factory=OTAProgress)
