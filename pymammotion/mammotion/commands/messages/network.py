# === sendOrderMsg_Net  ===
from abc import ABC
import time

from pymammotion import logger
from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.mammotion.commands.messages.navigation import MessageNavigation
from pymammotion.proto import (
    DevNet,
    DrvDebugDdsZmq,
    DrvDevInfoReq,
    DrvDevInfoReqId,
    DrvUploadFileCancel,
    DrvUploadFileReq,
    DrvUploadFileToAppReq,
    DrvWifiList,
    DrvWifiSet,
    DrvWifiUpload,
    GetNetworkInfoReq,
    IotConctrlType,
    LubaMsg,
    MnetCfg,
    MsgAttr,
    MsgCmdType,
    MsgDevice,
    NetType,
    SetMnetCfgReq,
)


class MessageNetwork(AbstractMessage, ABC):
    messageNavigation: MessageNavigation = MessageNavigation()

    @staticmethod
    def send_order_msg_net(build: DevNet) -> bytes:
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.ESP,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=MsgDevice.DEV_COMM_ESP,
            msgattr=MsgAttr.REQ,
            seqs=1,
            version=1,
            subtype=1,
            net=build,
            timestamp=round(time.time() * 1000),
        )

        return luba_msg.SerializeToString()

    def send_todev_ble_sync(self, sync_type: int) -> bytes:
        comm_esp = DevNet(todev_ble_sync=sync_type)
        return self.send_order_msg_net(comm_esp)

    def get_device_version_main(self) -> bytes:
        net = DevNet(todev_devinfo_req=DrvDevInfoReq())
        net.todev_devinfo_req.req_ids.append(DrvDevInfoReqId(id=1, type=6))

        return self.send_order_msg_net(net)

    def get_device_base_info(self) -> bytes:
        net = DevNet(todev_devinfo_req=DrvDevInfoReq())

        for i in range(1, 8):
            if i == 1:
                net.todev_devinfo_req.req_ids.append(DrvDevInfoReqId(id=i, type=6))
            net.todev_devinfo_req.req_ids.append(DrvDevInfoReqId(id=i, type=3))

        return self.send_order_msg_net(net)

    def get_4g_module_info(self) -> bytes:
        build = DevNet(todev_get_mnet_cfg_req=DevNet().todev_get_mnet_cfg_req)
        logger.debug("Send command -- Get device 4G network module information")
        return self.send_order_msg_net(build)

    def get_4g_info(self) -> bytes:
        build = DevNet(todev_mnet_info_req=DevNet().todev_mnet_info_req)
        logger.debug("Send command -- Get device 4G network information")
        return self.send_order_msg_net(build)

    def set_zmq_enable(self) -> bytes:
        build = DevNet(
            todev_set_dds2_zmq=DrvDebugDdsZmq(
                is_enable=True,
                rx_topic_name="perception_post_result",
                tx_zmq_url="tcp://0.0.0.0:5555",
            )
        )
        logger.debug("Send command -- Set vision ZMQ to enable")
        return self.send_order_msg_net(build)

    def set_iot_setting(self, iot_control_type: IotConctrlType) -> bytes:
        build = DevNet(todev_set_iot_offline_req=iot_control_type)
        logger.debug("Send command -- Device re-online")
        return self.send_order_msg_net(build)

    def set_device_log_upload(
        self,
        request_id: str,
        operation: int,
        server_ip: int,
        server_port: int,
        number: int,
        type: int,
    ) -> bytes:
        build = DrvUploadFileToAppReq(
            biz_id=request_id,
            operation=operation,
            server_ip=server_ip,
            server_port=server_port,
            num=number,
            type=type,
        )
        logger.debug(
            f"Send log====Feedback====Command======requestID:{request_id} operation:{operation} serverIp:{server_ip} type:{type}"
        )
        return self.send_order_msg_net(DevNet(todev_ble_sync=1, todev_uploadfile_req=build))

    def set_device_socket_request(
        self,
        request_id: str,
        operation: int,
        server_ip: int,
        server_port: int,
        number: int,
        type: int,
    ) -> bytes:
        """Set device socket request (bluetooth only)."""
        build = DrvUploadFileToAppReq(
            biz_id=request_id,
            operation=operation,
            server_ip=server_ip,
            server_port=server_port,
            num=number,
            type=type,
        )
        logger.debug(
            f"Send log====Feedback====Command======requestID:{request_id}  operation:{operation} serverIp:{server_ip}  type:{type}"
        )
        return self.send_order_msg_net(DevNet(todev_ble_sync=1, todev_uploadfile_req=build))

    def get_device_log_info(self, biz_id: str, type: int, log_url: str) -> bytes:
        """Get device log info (bluetooth only)."""
        return self.send_order_msg_net(
            DevNet(
                todev_ble_sync=1,
                todev_req_log_info=DrvUploadFileReq(
                    biz_id=biz_id,
                    type=type,
                    url=log_url,
                    num=0,
                    user_id="",  # TODO supply user id
                ),
            )
        )

    def cancel_log_update(self, biz_id: str) -> bytes:
        """Cancel log update (bluetooth only)."""
        return self.send_order_msg_net(DevNet(todev_log_data_cancel=DrvUploadFileCancel(biz_id=biz_id)))

    def get_device_network_info(self) -> bytes:
        build = DevNet(todev_networkinfo_req=GetNetworkInfoReq(req_ids=1))
        logger.debug("Send command - get device network information")
        return self.send_order_msg_net(build)

    def set_device_4g_enable_status(self, new_4g_status: bool) -> bytes:
        build = DevNet(
            todev_ble_sync=1,
            todev_set_mnet_cfg_req=SetMnetCfgReq(
                cfg=MnetCfg(
                    type=NetType.WIFI,
                    inet_enable=new_4g_status,
                    mnet_enable=new_4g_status,
                )
            ),
        )

        logger.debug(f"Send command - set 4G (on/off status). newWifiStatus={new_4g_status}")
        return self.send_order_msg_net(build)

    def set_device_wifi_enable_status(self, new_wifi_status: bool) -> bytes:
        build = DevNet(
            todev_ble_sync=1,
            todev_wifi_configuration=DrvWifiSet(config_param=4, wifi_enable=new_wifi_status),
        )
        logger.debug(f"szNetwork: Send command - set network (on/off status). newWifiStatus={new_wifi_status}")
        return self.send_order_msg_net(build)

    def wifi_connectinfo_update(self) -> bytes:
        build = DevNet(
            todev_ble_sync=1,
            todev_wifi_msg_upload=DrvWifiUpload(wifi_msg_upload=1),
        )
        logger.debug("Send command - get Wifi connection information")
        return self.send_order_msg_net(build)

    def wifi_connectinfo_update2(self) -> None:
        hash_map = {"getMsgCmd": 1}
        # self.post_custom_data(self.get_json_string(
        #     68, hash_map))  # TODO: Fix this

    def get_record_wifi_list(self) -> bytes:
        build = DevNet(todev_ble_sync=1, todev_wifi_list_upload=DrvWifiList())
        logger.debug("Send command - get memorized WiFi list upload command")
        return self.send_order_msg_net(build)

    def close_clear_connect_current_wifi(self, ssid: str, status: int) -> bytes:
        build = DevNet(
            todev_ble_sync=1,
            todev_wifi_configuration=DrvWifiSet(config_param=status, confssid=ssid),
        )
        logger.debug(
            f"Send command - set network (disconnect, direct connect, forget, no operation reconnect) operation command (downlink ssid={ssid}, status={status})"
        )
        return self.send_order_msg_net(build)
