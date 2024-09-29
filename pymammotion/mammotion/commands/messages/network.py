# === sendOrderMsg_Net  ===
from pymammotion import logger
from pymammotion.mammotion.commands.messages.navigation import MessageNavigation
from pymammotion.proto import dev_net_pb2, luba_msg_pb2


class MessageNetwork:
    messageNavigation: MessageNavigation = MessageNavigation()

    @staticmethod
    def send_order_msg_net(build) -> bytes:
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MSG_CMD_TYPE_ESP,
            sender=luba_msg_pb2.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.DEV_COMM_ESP,
            msgattr=luba_msg_pb2.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            net=build,
        )

        return luba_msg.SerializeToString()

    def send_todev_ble_sync(self, sync_type: int) -> bytes:
        comm_esp = dev_net_pb2.DevNet(todev_ble_sync=sync_type)
        return self.send_order_msg_net(comm_esp)

    def get_device_base_info(self) -> bytes:
        net = dev_net_pb2.DevNet(todev_devinfo_req=dev_net_pb2.DrvDevInfoReq())
        net.todev_devinfo_req.req_ids.add(id=1, type=6)

        return self.send_order_msg_net(net)

    def get_device_version_main(self) -> bytes:
        net = dev_net_pb2.DevNet(todev_devinfo_req=dev_net_pb2.DrvDevInfoReq())

        for i in range(1, 8):
            if i == 1:
                net.todev_devinfo_req.req_ids.add(id=i, type=6)
            net.todev_devinfo_req.req_ids.add(id=i, type=3)

        return self.send_order_msg_net(net)

    def get_4g_module_info(self) -> bytes:
        build = dev_net_pb2.DevNet(todev_get_mnet_cfg_req=dev_net_pb2.DevNet().todev_get_mnet_cfg_req)
        logger.debug("Send command -- Get device 4G network module information")
        return self.send_order_msg_net(build)

    def get_4g_info(self) -> bytes:
        build = dev_net_pb2.DevNet(todev_mnet_info_req=dev_net_pb2.DevNet().todev_mnet_info_req)
        logger.debug("Send command -- Get device 4G network information")
        return self.send_order_msg_net(build)

    def set_zmq_enable(self) -> bytes:
        build = dev_net_pb2.DevNet(
            todev_set_dds2zmq=dev_net_pb2.DrvDebugDdsZmq(
                is_enable=True,
                rx_topic_name="perception_post_result",
                tx_zmq_url="tcp://0.0.0.0:5555",
            )
        )
        logger.debug("Send command -- Set vision ZMQ to enable")
        return self.send_order_msg_net(build)

    def set_iot_setting(self, iot_control_type: dev_net_pb2.iot_conctrl_type) -> bytes:
        build = dev_net_pb2.DevNet(todev_set_iot_offline_req=iot_control_type)
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
        build = dev_net_pb2.DrvUploadFileToAppReq(
            bizId=request_id,
            operation=operation,
            serverIp=server_ip,
            serverPort=server_port,
            num=number,
            type=type,
        )
        logger.debug(
            f"Send log====Feedback====Command======requestID:{request_id} operation:{operation} serverIp:{server_ip} type:{type}"
        )
        return self.send_order_msg_net(dev_net_pb2.DevNet(todev_ble_sync=1, todev_uploadfile_req=build))

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
        build = dev_net_pb2.DrvUploadFileToAppReq(
            bizId=request_id,
            operation=operation,
            serverIp=server_ip,
            serverPort=server_port,
            num=number,
            type=type,
        )
        logger.debug(
            f"Send log====Feedback====Command======requestID:{request_id}  operation:{operation} serverIp:{server_ip}  type:{type}"
        )
        return self.send_order_msg_net(dev_net_pb2.DevNet(todev_ble_sync=1, todev_uploadfile_req=build))

    def get_device_log_info(self, biz_id: str, type: int, log_url: str) -> bytes:
        """Get device log info (bluetooth only)."""
        return self.send_order_msg_net(
            dev_net_pb2.DevNet(
                todev_ble_sync=1,
                todev_req_log_info=dev_net_pb2.DrvUploadFileReq(
                    bizId=biz_id,
                    type=type,
                    url=log_url,
                    num=0,
                    userId="",  # TODO supply user id
                ),
            )
        )

    def cancel_log_update(self, biz_id: str) -> bytes:
        """Cancel log update (bluetooth only)."""
        return self.send_order_msg_net(
            dev_net_pb2.DevNet(todev_log_data_cancel=dev_net_pb2.DrvUploadFileCancel(bizId=biz_id))
        )

    def get_device_network_info(self) -> bytes:
        build = dev_net_pb2.DevNet(todev_networkinfo_req=dev_net_pb2.GetNetworkInfoReq(req_ids=1))
        logger.debug("Send command - get device network information")
        return self.send_order_msg_net(build)

    def set_device_4g_enable_status(self, new_4g_status: bool) -> bytes:
        build = dev_net_pb2.DevNet(
            todev_ble_sync=1,
            todev_set_mnet_cfg_req=dev_net_pb2.SetMnetCfgReq(
                cfg=dev_net_pb2.MnetCfg(
                    type=dev_net_pb2.NET_TYPE_WIFI,
                    inet_enable=new_4g_status,
                    mnet_enable=new_4g_status,
                )
            ),
        )

        logger.debug(f"Send command - set 4G (on/off status). newWifiStatus={new_4g_status}")
        return self.send_order_msg_net(build)

    def set_device_wifi_enable_status(self, new_wifi_status: bool) -> bytes:
        build = dev_net_pb2.DevNet(
            todev_ble_sync=1,
            todev_Wifi_Configuration=dev_net_pb2.DrvWifiSet(configParam=4, wifi_enable=new_wifi_status),
        )
        logger.debug(f"szNetwork: Send command - set network (on/off status). newWifiStatus={new_wifi_status}")
        return self.send_order_msg_net(build)

    def wifi_connectinfo_update(self, device_name: str, is_binary: bool) -> bytes:
        logger.debug(
            f"Send command - get Wifi connection information.wifiConnectinfoUpdate().deviceName={device_name}.isBinary={is_binary}"
        )
        if is_binary:
            build = dev_net_pb2.DevNet(
                todev_ble_sync=1,
                todev_WifiMsgUpload=dev_net_pb2.DrvWifiUpload(wifi_msg_upload=1),
            )
            logger.debug("Send command - get Wifi connection information")
            return self.send_order_msg_net(build)
        self.wifi_connectinfo_update2()

    def wifi_connectinfo_update2(self) -> None:
        hash_map = {"getMsgCmd": 1}
        # self.post_custom_data(self.get_json_string(
        #     68, hash_map))  # ToDo: Fix this

    def get_record_wifi_list(self, is_binary: bool) -> bytes:
        logger.debug(f"getRecordWifiList().isBinary={is_binary}")
        if is_binary:
            build = dev_net_pb2.DevNet(todev_ble_sync=1, todev_WifiListUpload=dev_net_pb2.DrvWifiList())
            logger.debug("Send command - get memorized WiFi list upload command")
            return self.send_order_msg_net(build)
        self.get_record_wifi_list2()

    def get_record_wifi_list2(self) -> None:
        pass
        # self.messageNavigation.post_custom_data(
        #     self.get_json_string(69))  # ToDo: Fix this

    def close_clear_connect_current_wifi(self, ssid: str, status: int, is_binary: bool) -> bytes:
        if is_binary:
            build = dev_net_pb2.DevNet(
                todev_ble_sync=1,
                todev_Wifi_Configuration=dev_net_pb2.DrvWifiSet(configParam=status, Confssid=ssid),
            )
            logger.debug(
                f"Send command - set network (disconnect, direct connect, forget, no operation reconnect) operation command (downlink ssid={ssid}, status={status})"
            )
            return self.send_order_msg_net(build)
        self.close_clear_connect_current_wifi2(ssid, status)

    def close_clear_connect_current_wifi2(self, ssid: str, get_msg_cmd: int) -> None:
        data = {"ssid": ssid, "getMsgCmd": get_msg_cmd}
        # self.messageNavigation.post_custom_data(
        # ToDo: Fix this
        # self.get_json_string(bleOrderCmd.close_clear_connect_current_wifi, data).encode())
