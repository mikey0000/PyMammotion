import itertools
import json
import logging
import queue
import sys
import time
from asyncio import sleep
from io import BytesIO

from bleak import BleakClient
from jsonic.serializable import serialize

from pymammotion.aliyun.tmp_constant import tmp_constant
from pymammotion.bluetooth.const import UUID_WRITE_CHARACTERISTIC
from pymammotion.bluetooth.data.convert import parse_custom_data
from pymammotion.bluetooth.data.framectrldata import FrameCtrlData
from pymammotion.bluetooth.data.notifydata import BlufiNotifyData
from pymammotion.data.model.execute_boarder import ExecuteBorder
from pymammotion.proto import (
    dev_net_pb2,
    luba_msg_pb2,
)
from pymammotion.utility.constant.device_constant import bleOrderCmd

_LOGGER = logging.getLogger(__name__)


class BleMessage:
    """Class for sending and recieving messages from Luba"""

    AES_TRANSFORMATION = "AES/CFB/NoPadding"
    DEFAULT_PACKAGE_LENGTH = 20
    DH_G = "2"
    DH_P = "cf5cf5c38419a724957ff5dd323b9c45c3cdd261eb740f69aa94b8bb1a5c96409153bd76b24222d03274e4725a5406092e9e82e9135c643cae98132b0d95f7d65347c68afc1e677da90e51bbab5f5cf429c291b4ba39c6b2dc5e8c7231e46aa7728e87664532cdf547be20c9a3fa8342be6e34371a27c06f7dc0edddd2f86373"
    MIN_PACKAGE_LENGTH = 20
    NEG_SECURITY_SET_ALL_DATA = 1
    NEG_SECURITY_SET_TOTAL_LENGTH = 0
    PACKAGE_HEADER_LENGTH = 4
    mPrintDebug = False
    mWriteTimeout = -1
    mPackageLengthLimit = -1
    mBlufiMTU = -1
    mEncrypted = False
    mChecksum = False
    mRequireAck = False
    mConnectState = 0
    mSendSequence: iter
    mReadSequence: iter
    mAck: queue
    notification: BlufiNotifyData

    def __init__(self, client: BleakClient) -> None:
        self.client = client
        self.mSendSequence = itertools.count()
        self.mReadSequence = itertools.count()
        self.mAck = queue.Queue()
        self.notification = BlufiNotifyData()

    async def get_device_version_main(self) -> None:
        commEsp = dev_net_pb2.DevNet(todev_devinfo_req=dev_net_pb2.DrvDevInfoReq())

        for i in range(1, 8):
            if i == 1:
                commEsp.todev_devinfo_req.req_ids.add(id=i, type=6)
            commEsp.todev_devinfo_req.req_ids.add(id=i, type=3)

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_ESP
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.net.CopyFrom(commEsp)
        byte_arr = lubaMsg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def get_task(self) -> None:
        hash_map = {"pver": 1, "subCmd": 2, "result": 0}
        await self.post_custom_data(self.get_json_string(bleOrderCmd.task, hash_map))

    async def send_ble_alive(self) -> None:
        hash_map = {"ctrl": 1}
        await self.post_custom_data(self.get_json_string(bleOrderCmd.bleAlive, hash_map))

    def get_json_string(self, cmd: int, hash_map: dict[str, object]) -> str:
        jSONObject = {}
        try:
            jSONObject["cmd"] = cmd
            jSONObject[tmp_constant.REQUEST_ID] = int(time.time())
            jSONObject2 = {}
            for key, value in hash_map.items():
                jSONObject2[key] = value
            jSONObject["params"] = jSONObject2
            return json.dumps(jSONObject)
        except Exception as e:
            print(e)
            return ""

    def clearNotification(self) -> None:
        self.notification = None
        self.notification = BlufiNotifyData()

    # async def get_device_info(self):
    #     await self.postCustomData(self.getJsonString(bleOrderCmd.getDeviceInfo))

    async def send_device_info(self) -> None:
        """Currently not called"""
        luba_msg = luba_msg_pb2.LubaMsg(
            msgtype=luba_msg_pb2.MsgCmdType.MSG_CMD_TYPE_ESP,
            sender=luba_msg_pb2.MsgDevice.DEV_MOBILEAPP,
            rcver=luba_msg_pb2.MsgDevice.DEV_COMM_ESP,
            msgattr=luba_msg_pb2.MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            net=dev_net_pb2.DevNet(todev_ble_sync=1, todev_devinfo_req=dev_net_pb2.DrvDevInfoReq()),
        )
        byte_arr = luba_msg.SerializeToString()
        await self.post_custom_data_bytes(byte_arr)

    async def requestDeviceStatus(self) -> None:
        request = False
        type = self.getTypeValue(0, 5)
        try:
            request = await self.post(BleMessage.mEncrypted, BleMessage.mChecksum, False, type, None)
            # _LOGGER.debug(request)
        except Exception as err:
            # Log.w(TAG, "post requestDeviceStatus interrupted")
            request = False
            _LOGGER.error(err)

        # if not request:
        #     onStatusResponse(BlufiCallback.CODE_WRITE_DATA_FAILED, null)

    async def requestDeviceVersion(self) -> None:
        request = False
        type = self.getTypeValue(0, 7)
        try:
            request = await self.post(BleMessage.mEncrypted, BleMessage.mChecksum, False, type, None)
            # _LOGGER.debug(request)
        except Exception as err:
            # Log.w(TAG, "post requestDeviceStatus interrupted")
            request = False
            _LOGGER.error(err)

    async def sendBorderPackage(self, executeBorder: ExecuteBorder) -> None:
        await self.post_custom_data(serialize(executeBorder))

    async def gatt_write(self, data: bytes) -> None:
        await self.client.write_gatt_char(UUID_WRITE_CHARACTERISTIC, data, True)

    def parseNotification(self, response: bytearray):
        dataOffset = None
        if response is None:
            # Log.w(TAG, "parseNotification null data");
            return -1

        # if (this.mPrintDebug):
        #     Log.d(TAG, "parseNotification Notification= " + Arrays.toString(response));
        # }
        if len(response) >= 4:
            sequence = int(response[2])  # toInt
            if sequence != next(self.mReadSequence):
                _LOGGER.debug(
                    "parseNotification read sequence wrong",
                    sequence,
                    self.mReadSequence,
                )
                self.mReadSequence = itertools.count(start=sequence)
                # this is questionable
                # self.mReadSequence = sequence
                # self.mReadSequence_2.incrementAndGet()

            # LogUtil.m7773e(self.mGatt.getDevice().getName() + "打印丢包率", self.mReadSequence_2 + "/" + self.mReadSequence_1);
            pkt_type = int(response[0])  # toInt
            pkgType = self._getPackageType(pkt_type)
            subType = self._getSubType(pkt_type)
            self.notification.setType(pkt_type)
            self.notification.setPkgType(pkgType)
            self.notification.setSubType(subType)
            frameCtrl = int(response[1])  # toInt
            # _LOGGER.debug("frame ctrl")
            # _LOGGER.debug(frameCtrl)
            # _LOGGER.debug(response)
            # _LOGGER.debug(f"pktType {pkt_type} pkgType {pkgType} subType {subType}")
            self.notification.setFrameCtrl(frameCtrl)
            frameCtrlData = FrameCtrlData(frameCtrl)
            dataLen = int(response[3])  # toInt specifies length of data

            try:
                dataBytes = response[4 : 4 + dataLen]
                if frameCtrlData.isEncrypted():
                    _LOGGER.debug("is encrypted")
                #     BlufiAES aes = new BlufiAES(self.mAESKey, AES_TRANSFORMATION, generateAESIV(sequence));
                #     dataBytes = aes.decrypt(dataBytes);
                # }
                if frameCtrlData.isChecksum():
                    _LOGGER.debug("checksum")
                #     int respChecksum1 = toInt(response[response.length - 1]);
                #     int respChecksum2 = toInt(response[response.length - 2]);
                #     int crc = BlufiCRC.calcCRC(BlufiCRC.calcCRC(0, new byte[]{(byte) sequence, (byte) dataLen}), dataBytes);
                #     int calcChecksum1 = (crc >> 8) & 255;
                #     int calcChecksum2 = crc & 255;
                #     if (respChecksum1 != calcChecksum1 || respChecksum2 != calcChecksum2) {
                #         Log.w(TAG, "parseNotification: read invalid checksum");
                #         if (self.mPrintDebug) {
                #             Log.d(TAG, "expect   checksum: " + respChecksum1 + ", " + respChecksum2);
                #             Log.d(TAG, "received checksum: " + calcChecksum1 + ", " + calcChecksum2);
                #             return -4;
                #         }
                #         return -4;
                #     }
                # }
                if frameCtrlData.hasFrag():
                    dataOffset = 2
                else:
                    dataOffset = 0

                self.notification.addData(dataBytes, dataOffset)
                return 1 if frameCtrlData.hasFrag() else 0
            except Exception as e:
                _LOGGER.debug(e)
                return -100

        # Log.w(TAG, "parseNotification data length less than 4");
        return -2

    async def parseBlufiNotifyData(self, return_bytes: bool = False):
        pkgType = self.notification.getPkgType()
        subType = self.notification.getSubType()
        dataBytes = self.notification.getDataArray()
        if pkgType == 0:
            # never seem to get these..
            self._parseCtrlData(subType, dataBytes)
        if pkgType == 1:
            if return_bytes:
                return dataBytes
            return await self._parseDataData(subType, dataBytes)

    def _parseCtrlData(self, subType: int, data: bytes) -> None:
        pass
        # self._parseAck(data)

    async def _parseDataData(self, subType: int, data: bytes):
        #     if (subType == 0) {
        #         this.mSecurityCallback.onReceiveDevicePublicKey(data);
        #         return;
        #     }
        _LOGGER.debug(subType)
        match subType:
            #         case 15:
            #             parseWifiState(data);
            #             return;
            #         case 16:
            #             parseVersion(data);
            #             return;
            #         case 17:
            #             parseWifiScanList(data);
            #             return;
            #         case 18:
            #             int errCode = data.length > 0 ? 255 & data[0] : 255;
            #             onError(errCode);
            #             return;
            case 19:
                #             # com/agilexrobotics/utils/EspBleUtil$BlufiCallbackMain.smali
                luba_msg = parse_custom_data(data)  # parse to protobuf message
                # really need some sort of callback
                if luba_msg.HasField("net"):
                    if luba_msg.net.HasField("toapp_wifi_iot_status"):
                        # await sleep(1.5)
                        _LOGGER.debug("sending ble sync")
                        # await self.send_todev_ble_sync(2)
                return luba_msg

    # private void parseCtrlData(int i, byte[] bArr) {
    #     if (i == 0) {
    #         parseAck(bArr);
    #     }
    # }

    # private void parseAck(byte[] bArr) {
    #     this.mAck.add(Integer.valueOf(bArr.length > 0 ? bArr[0] & 255 : 256));
    # }

    def getJsonString(self, cmd: int) -> str:
        jSONObject = {}
        try:
            jSONObject["cmd"] = cmd
            jSONObject[tmp_constant.REQUEST_ID] = int(time.time())
            return json.dumps(jSONObject)
        except Exception:
            return ""

    def current_milli_time(self):
        return round(time.time() * 1000)

    def _getPackageType(self, typeValue: int):
        return typeValue & 3

    def _getSubType(self, typeValue: int):
        return (typeValue & 252) >> 2

    def getTypeValue(self, type: int, subtype: int):
        return (subtype << 2) | type

    def receiveAck(self, expectAck: int) -> bool:
        try:
            ack = next(self.mAck)
            return ack == expectAck
        except Exception as err:
            _LOGGER.debug(err)
            return False

    def generateSendSequence(self):
        return next(self.mSendSequence) & 255

    async def post_custom_data_bytes(self, data: bytes) -> None:
        if data == None:
            return
        type_val = self.getTypeValue(1, 19)
        try:
            suc = await self.post(self.mEncrypted, self.mChecksum, self.mRequireAck, type_val, data)
            # int status = suc ? 0 : BlufiCallback.CODE_WRITE_DATA_FAILED
            # onPostCustomDataResult(status, data)
            # _LOGGER.debug(suc)
        except Exception as err:
            _LOGGER.debug(err)

    async def post_custom_data(self, data_str: str) -> None:
        data = data_str.encode()
        if data == None:
            return
        type_val = self.getTypeValue(1, 19)
        try:
            suc = await self.post(self.mEncrypted, self.mChecksum, self.mRequireAck, type_val, data)
            # int status = suc ? 0 : BlufiCallback.CODE_WRITE_DATA_FAILED
            # onPostCustomDataResult(status, data)
        except Exception as err:
            _LOGGER.debug(err)
            # we might be constantly connected and in a bad state
            self.mSendSequence = itertools.count()
            self.mReadSequence = itertools.count()
            await self.client.disconnect()

    async def post(
        self,
        encrypt: bool,
        checksum: bool,
        require_ack: bool,
        type_of: int,
        data: bytes,
    ) -> bool:
        if data is None:
            return await self.post_non_data(encrypt, checksum, require_ack, type_of)

        return await self.post_contains_data(encrypt, checksum, require_ack, type_of, data)

    async def post_non_data(self, encrypt: bool, checksum: bool, require_ack: bool, type_of: int) -> bool:
        sequence = self.generateSendSequence()
        postBytes = self.getPostBytes(type_of, encrypt, checksum, require_ack, False, sequence, None)
        posted = await self.gatt_write(postBytes)
        return posted and (not require_ack or self.receiveAck(sequence))

    async def post_contains_data(
        self,
        encrypt: bool,
        checksum: bool,
        require_ack: bool,
        type_of: int,
        data: bytes,
    ) -> bool:
        chunk_size = 517  # self.client.mtu_size - 3

        chunks = list()
        for i in range(0, len(data), chunk_size):
            if i + chunk_size > len(data):
                chunks.append(data[i : len(data)])
            else:
                chunks.append(data[i : i + chunk_size])
        for index, chunk in enumerate(chunks):
            frag = index != len(chunks) - 1
            sequence = self.generateSendSequence()
            postBytes = self.getPostBytes(type_of, encrypt, checksum, require_ack, frag, sequence, chunk)
            # _LOGGER.debug("sequence")
            # _LOGGER.debug(sequence)
            posted = await self.gatt_write(postBytes)
            if posted != None:
                return False

            if not frag:
                return not require_ack or self.receiveAck(sequence)

            if require_ack and not self.receiveAck(sequence):
                return False
            else:
                _LOGGER.debug("sleeping 0.01")
                await sleep(0.01)

    def getPostBytes(
        self,
        type: int,
        encrypt: bool,
        checksum: bool,
        require_ack: bool,
        hasFrag: bool,
        sequence: int,
        data: bytes | None,
    ) -> bytes:
        byteOS = BytesIO()
        dataLength = 0 if data == None else len(data)
        frameCtrl = FrameCtrlData.getFrameCTRLValue(encrypt, checksum, 0, require_ack, hasFrag)
        byteOS.write(type.to_bytes(1, sys.byteorder))
        byteOS.write(frameCtrl.to_bytes(1, sys.byteorder))
        byteOS.write(sequence.to_bytes(1, sys.byteorder))
        byteOS.write(dataLength.to_bytes(1, sys.byteorder))

        if data != None:
            byteOS.write(data)

        _LOGGER.debug(byteOS.getvalue())
        return byteOS.getvalue()
