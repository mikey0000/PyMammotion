# === sendOrderMsg_Net  ===
from abc import ABC
import time

from pymammotion import logger
from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import (
    BleSignatureReq,
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
    MnetApn,
    MnetApnCfg,
    MnetApnSetCfg,
    MnetCfg,
    MsgAttr,
    MsgCmdType,
    MsgDevice,
    NetType,
    SetDrvBleMtu,
    SetMnetCfgReq,
)


class MessageNetwork(AbstractMessage, ABC):
    """Mixin that builds and serialises network protobuf command messages (WiFi, 4G, BLE, logging)."""

    def send_order_msg_net(self, build: DevNet) -> bytes:
        """Serialize a network (DevNet) payload into a LubaMsg request frame targeting the ESP comm module."""
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.ESP,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=MsgDevice.DEV_COMM_ESP,
            msgattr=MsgAttr.REQ,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            net=build,
            timestamp=round(time.time() * 1000),
        )

        return luba_msg.SerializeToString()

    def send_todev_ble_sync(self, sync_type: int) -> bytes:
        """Send a BLE synchronisation control message with the specified sync type."""
        comm_esp = DevNet(todev_ble_sync=sync_type)
        return self.send_order_msg_net(comm_esp)

    def get_device_version_main(self) -> bytes:
        """Request the main firmware version from the ESP module."""
        net = DevNet(todev_devinfo_req=DrvDevInfoReq())
        net.todev_devinfo_req.req_ids.append(DrvDevInfoReqId(id=1, type=6))

        return self.send_order_msg_net(net)

    def get_device_base_info(self) -> bytes:
        """Request base hardware and firmware info for all device sub-components (IDs 1–7)."""
        net = DevNet(todev_devinfo_req=DrvDevInfoReq())

        for i in range(1, 8):
            if i == 1:
                net.todev_devinfo_req.req_ids.append(DrvDevInfoReqId(id=i, type=6))
            net.todev_devinfo_req.req_ids.append(DrvDevInfoReqId(id=i, type=3))

        return self.send_order_msg_net(net)

    def get_4g_module_info(self) -> bytes:
        """Request the 4G mobile network module configuration from the device."""
        build = DevNet(todev_get_mnet_cfg_req=DevNet().todev_get_mnet_cfg_req)
        logger.debug("Send command -- Get device 4G network module information")
        return self.send_order_msg_net(build)

    def get_4g_info(self) -> bytes:
        """Request current 4G network connection status and signal information from the device."""
        build = DevNet(todev_mnet_info_req=DevNet().todev_mnet_info_req)
        logger.debug("Send command -- Get device 4G network information")
        return self.send_order_msg_net(build)

    def set_zmq_enable(self) -> bytes:
        """Enable the DDS/ZMQ vision perception data bridge on the device."""
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
        """Send an IoT connectivity control command to bring the device online or offline."""
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
        """Instruct the device to upload log files to the specified server address and port."""
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
        """Request the current network interface information from the device."""
        build = DevNet(todev_networkinfo_req=GetNetworkInfoReq(req_ids=1))
        logger.debug("Send command - get device network information")
        return self.send_order_msg_net(build)

    def set_device_4g_enable_status(self, new_4g_status: bool) -> bytes:
        """Enable or disable the device 4G mobile network connection."""
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
        """Enable or disable the device WiFi connection."""
        build = DevNet(
            todev_ble_sync=1,
            todev_wifi_configuration=DrvWifiSet(config_param=4, wifi_enable=new_wifi_status),
        )
        logger.debug(f"szNetwork: Send command - set network (on/off status). newWifiStatus={new_wifi_status}")
        return self.send_order_msg_net(build)

    def wifi_connectinfo_update(self) -> bytes:
        """Request the current WiFi connection status and details from the device."""
        build = DevNet(
            todev_ble_sync=1,
            todev_wifi_msg_upload=DrvWifiUpload(wifi_msg_upload=1),
        )
        logger.debug("Send command - get Wifi connection information")
        return self.send_order_msg_net(build)

    def get_record_wifi_list(self) -> bytes:
        """Request the list of previously remembered WiFi networks stored on the device."""
        build = DevNet(todev_ble_sync=1, todev_wifi_list_upload=DrvWifiList())
        logger.debug("Send command - get memorized WiFi list upload command")
        return self.send_order_msg_net(build)

    def set_mtu_value(self, mtu: int) -> bytes:
        """Set Bluetooth MTU value."""
        build = DevNet(todev_set_ble_mtu=SetDrvBleMtu(mtu_count=mtu))
        logger.debug(f"Send command - Set MTU value mtu={mtu}")
        return self.send_order_msg_net(build)

    def send_sign_verification(self, signature_data: str, random_data: str) -> bytes:
        """Send BLE signature verification frame (RSA authentication)."""
        build = DevNet(
            todev_verify_signature_req=BleSignatureReq(signature_data=signature_data, random_data=random_data)
        )
        logger.debug("Send command - BLE signature verification")
        return self.send_order_msg_net(build)

    def set_4g_net_apn_info(self, apn_name: str) -> bytes:
        """Set 4G network APN name."""
        build = DevNet(
            todev_set_mnet_cfg_req=SetMnetCfgReq(
                cfg=MnetCfg(
                    apn=MnetApnSetCfg(cfg=MnetApnCfg(apn=[MnetApn(apn_name=apn_name)])),
                    inet_enable=True,
                    mnet_enable=True,
                )
            )
        )
        logger.debug(f"Send command - Set 4G APN name={apn_name}")
        return self.send_order_msg_net(build)

    def close_clear_connect_current_wifi(self, ssid: str, status: int) -> bytes:
        """Send a WiFi management command to disconnect, forget, directly connect, or reconnect to the given SSID."""
        build = DevNet(
            todev_ble_sync=1,
            todev_wifi_configuration=DrvWifiSet(config_param=status, confssid=ssid),
        )
        logger.debug(
            f"Send command - set network (disconnect, direct connect, forget, no operation reconnect) operation command (downlink ssid={ssid}, status={status})"
        )
        return self.send_order_msg_net(build)
