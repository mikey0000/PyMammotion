# === sendOrderMsg_Ota ===
from abc import ABC
import logging

from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import (
    DownlinkT,
    FotaInfoT,
    FotaSubInfoT,
    FwDownloadCtrl,
    GetInfoReq,
    InfoType,
    LubaMsg,
    MctlOta,
    MsgAttr,
    MsgCmdType,
    MsgDevice,
)

_LOGGER = logging.getLogger(__name__)


class MessageOta(AbstractMessage, ABC):
    """Message OTA class."""

    def send_order_msg_ota(self, ota):
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.EMBED_OTA,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.EMBED_OTA, MsgDevice.DEV_MAINCTL),
            msgattr=MsgAttr.REQ,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            ota=ota,
        )

        return luba_msg.SerializeToString()

    def get_device_ota_info(self, log_type: int):
        todev_get_info_req = MctlOta(todev_get_info_req=GetInfoReq(type=InfoType.IT_OTA))

        _LOGGER.debug("===Send command to get upgrade details===logType:" + str(log_type))
        return self.send_order_msg_ota(todev_get_info_req)

    def get_device_info_new(self) -> bytes:
        """New device call for OTA upgrade information."""
        todev_get_info_req = MctlOta(todev_get_info_req=GetInfoReq(type=InfoType.IT_BASE))
        _LOGGER.debug("Send to get OTA upgrade information", "Get device information")
        return self.send_order_msg_ota(todev_get_info_req)

    # === Swimming pool device OTA (Spino) ===

    def start_swimming_pool_device_ota(self, data: list[int]) -> bytes:
        """Initiate swimming pool device OTA by sending initial data packet (cmd=1)."""
        ota = MctlOta(fw_download_ctrl=FwDownloadCtrl(cmd=1, downlink=DownlinkT(data=data)))
        _LOGGER.debug("Send command - Start swimming pool device OTA")
        return self.send_order_msg_ota(ota)

    def send_swimming_pool_device_ota_first(self, img_size: int, need_ota_num: int, ota_version: str) -> bytes:
        """Send first OTA initiation message with image metadata (Spino)."""
        version = ota_version.replace(" ", "")
        if "(" in version:
            version = version[: version.index("(")]
        ota = MctlOta(
            fota_info=FotaInfoT(
                need_ota_num=need_ota_num,
                need_ota_img_size=img_size,
                ota_otype=1,
                ota_version=version,
                ota_oid="1",
            )
        )
        _LOGGER.debug(f"Send command - Swimming pool OTA first version={version}")
        return self.send_order_msg_ota(ota)

    def send_swimming_pool_device_ota_package(self, data: list[int], fw_id: int, pkg_seq: int) -> bytes:
        """Send an OTA firmware data chunk (cmd=3)."""
        ota = MctlOta(
            fw_download_ctrl=FwDownloadCtrl(
                cmd=3,
                downlink=DownlinkT(fw_id=fw_id, pkg_seq=pkg_seq, data=data),
            )
        )
        _LOGGER.debug(f"Send command - Swimming pool OTA package fw_id={fw_id}, pkg_seq={pkg_seq}")
        return self.send_order_msg_ota(ota)

    def send_swimming_pool_device_ota_second(
        self, sub_mod_id: int, sub_img_size: int, sub_img_url: str, sub_mod_version: str
    ) -> bytes:
        """Send secondary OTA initiation with sub-module metadata (Spino)."""
        version = sub_mod_version.replace(" ", "")
        if "(" in version:
            version = version[: version.index("(")]
        ota = MctlOta(
            fota_sub_info=FotaSubInfoT(
                sub_mod_ota_flag=1,
                sub_mod_id=sub_mod_id,
                sub_img_size=sub_img_size,
                sub_mod_version=version,
                sub_img_url=sub_img_url,
            )
        )
        _LOGGER.debug(f"Send command - Swimming pool OTA second sub_mod_id={sub_mod_id}")
        return self.send_order_msg_ota(ota)

    def notify_firmware_send_finish(self) -> bytes:
        """Notify device that firmware download is complete (cmd=5). Used for resume OTA."""
        ota = MctlOta(fw_download_ctrl=FwDownloadCtrl(cmd=5, downlink=DownlinkT()))
        _LOGGER.debug("Send command - Notify firmware send finish")
        return self.send_order_msg_ota(ota)
