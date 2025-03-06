from asyncio import sleep
from io import BytesIO
import itertools
import json
import logging
import queue
import sys
import time

from bleak import BleakClient
from jsonic.serializable import serialize

from pymammotion.aliyun.tmp_constant import tmp_constant
from pymammotion.bluetooth.const import UUID_WRITE_CHARACTERISTIC
from pymammotion.bluetooth.data.framectrldata import FrameCtrlData
from pymammotion.bluetooth.data.notifydata import BlufiNotifyData
from pymammotion.bluetooth.model.atomic_integer import AtomicInteger
from pymammotion.data.model.execute_boarder import ExecuteBorder
from pymammotion.proto import DevNet, DrvDevInfoReq, LubaMsg, MsgAttr, MsgCmdType, MsgDevice
from pymammotion.utility.constant.device_constant import bleOrderCmd

_LOGGER = logging.getLogger(__name__)

CRC_TB = [
    0x0000,
    0x1021,
    0x2042,
    0x3063,
    0x4084,
    0x50A5,
    0x60C6,
    0x70E7,
    0x8108,
    0x9129,
    0xA14A,
    0xB16B,
    0xC18C,
    0xD1AD,
    0xE1CE,
    0xF1EF,
    0x1231,
    0x0210,
    0x3273,
    0x2252,
    0x52B5,
    0x4294,
    0x72F7,
    0x62D6,
    0x9339,
    0x8318,
    0xB37B,
    0xA35A,
    0xD3BD,
    0xC39C,
    0xF3FF,
    0xE3DE,
    0x2462,
    0x3443,
    0x0420,
    0x1401,
    0x64E6,
    0x74C7,
    0x44A4,
    0x5485,
    0xA56A,
    0xB54B,
    0x8528,
    0x9509,
    0xE5EE,
    0xF5CF,
    0xC5AC,
    0xD58D,
    0x3653,
    0x2672,
    0x1611,
    0x0630,
    0x76D7,
    0x66F6,
    0x5695,
    0x46B4,
    0xB75B,
    0xA77A,
    0x9719,
    0x8738,
    0xF7DF,
    0xE7FE,
    0xD79D,
    0xC7BC,
    0x48C4,
    0x58E5,
    0x6886,
    0x78A7,
    0x0840,
    0x1861,
    0x2802,
    0x3823,
    0xC9CC,
    0xD9ED,
    0xE98E,
    0xF9AF,
    0x8948,
    0x9969,
    0xA90A,
    0xB92B,
    0x5AF5,
    0x4AD4,
    0x7AB7,
    0x6A96,
    0x1A71,
    0x0A50,
    0x3A33,
    0x2A12,
    0xDBFD,
    0xCBDC,
    0xFBBF,
    0xEB9E,
    0x9B79,
    0x8B58,
    0xBB3B,
    0xAB1A,
    0x6CA6,
    0x7C87,
    0x4CE4,
    0x5CC5,
    0x2C22,
    0x3C03,
    0x0C60,
    0x1C41,
    0xEDAE,
    0xFD8F,
    0xCDEC,
    0xDDCD,
    0xAD2A,
    0xBD0B,
    0x8D68,
    0x9D49,
    0x7E97,
    0x6EB6,
    0x5ED5,
    0x4EF4,
    0x3E13,
    0x2E32,
    0x1E51,
    0x0E70,
    0xFF9F,
    0xEFBE,
    0xDFDD,
    0xCFFC,
    0xBF1B,
    0xAF3A,
    0x9F59,
    0x8F78,
    0x9188,
    0x81A9,
    0xB1CA,
    0xA1EB,
    0xD10C,
    0xC12D,
    0xF14E,
    0xE16F,
    0x1080,
    0x00A1,
    0x30C2,
    0x20E3,
    0x5004,
    0x4025,
    0x7046,
    0x6067,
    0x83B9,
    0x9398,
    0xA3FB,
    0xB3DA,
    0xC33D,
    0xD31C,
    0xE37F,
    0xF35E,
    0x02B1,
    0x1290,
    0x22F3,
    0x32D2,
    0x4235,
    0x5214,
    0x6277,
    0x7256,
    0xB5EA,
    0xA5CB,
    0x95A8,
    0x8589,
    0xF56E,
    0xE54F,
    0xD52C,
    0xC50D,
    0x34E2,
    0x24C3,
    0x14A0,
    0x0481,
    0x7466,
    0x6447,
    0x5424,
    0x4405,
    0xA7DB,
    0xB7FA,
    0x8799,
    0x97B8,
    0xE75F,
    0xF77E,
    0xC71D,
    0xD73C,
    0x26D3,
    0x36F2,
    0x0691,
    0x16B0,
    0x6657,
    0x7676,
    0x4615,
    0x5634,
    0xD94C,
    0xC96D,
    0xF90E,
    0xE92F,
    0x99C8,
    0x89E9,
    0xB98A,
    0xA9AB,
    0x5844,
    0x4865,
    0x7806,
    0x6827,
    0x18C0,
    0x08E1,
    0x3882,
    0x28A3,
    0xCB7D,
    0xDB5C,
    0xEB3F,
    0xFB1E,
    0x8BF9,
    0x9BD8,
    0xABBB,
    0xBB9A,
    0x4A75,
    0x5A54,
    0x6A37,
    0x7A16,
    0x0AF1,
    0x1AD0,
    0x2AB3,
    0x3A92,
    0xFD2E,
    0xED0F,
    0xDD6C,
    0xCD4D,
    0xBDAA,
    0xAD8B,
    0x9DE8,
    0x8DC9,
    0x7C26,
    0x6C07,
    0x5C64,
    0x4C45,
    0x3CA2,
    0x2C83,
    0x1CE0,
    0x0CC1,
    0xEF1F,
    0xFF3E,
    0xCF5D,
    0xDF7C,
    0xAF9B,
    0xBFBA,
    0x8FD9,
    0x9FF8,
    0x6E17,
    0x7E36,
    0x4E55,
    0x5E74,
    0x2E93,
    0x3EB2,
    0x0ED1,
    0x1EF0,
]


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

    def __init__(self, client: BleakClient) -> None:
        self.client = client
        self.mSendSequence = AtomicInteger(-1)
        self.mReadSequence = AtomicInteger(-1)
        self.mAck = queue.Queue()
        self.notification = BlufiNotifyData()

    async def get_task(self) -> None:
        hash_map = {"pver": 1, "subCmd": 2, "result": 0}
        await self.post_custom_data(self.get_json_string(bleOrderCmd.task, hash_map))

    async def send_ble_alive(self) -> None:
        hash_map = {"ctrl": 1}
        await self.post_custom_data(self.get_json_string(bleOrderCmd.bleAlive, hash_map))

    def get_json_string(self, cmd: int, hash_map: dict[str, int]) -> str:
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

    def clear_notification(self) -> None:
        self.notification = None
        self.notification = BlufiNotifyData()

    # async def get_device_info(self):
    #     await self.postCustomData(self.getJsonString(bleOrderCmd.getDeviceInfo))

    async def send_device_info(self) -> None:
        """Currently not called"""
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.ESP,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=MsgDevice.DEV_COMM_ESP,
            msgattr=MsgAttr.REQ,
            seqs=1,
            version=1,
            subtype=1,
            net=DevNet(todev_ble_sync=1, todev_devinfo_req=DrvDevInfoReq()),
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
        """Parse notification data from BLE device."""
        if response is None:
            # Log.w(TAG, "parseNotification null data");
            return -1

        # if (this.mPrintDebug):
        #     Log.d(TAG, "parseNotification Notification= " + Arrays.toString(response));
        # }
        if len(response) < 4:
            _LOGGER.debug("parseNotification data length less than 4")
            return -2

        sequence = int(response[2])  # toInt
        current_sequence = self.mReadSequence.get() & 255
        if sequence == current_sequence:
            _LOGGER.debug(f"Received bluetooth data 1: {response.hex()}, object: {self}")
            return 2

        # Compare with the second counter, mod 255
        if sequence != (self.mReadSequence.increment_and_get() & 255):
            _LOGGER.debug(
                "parseNotification read sequence wrong %s %s",
                sequence,
                self.mReadSequence.get(),
            )
            # Set the value for mReadSequence manually
            self.mReadSequence.set(sequence)

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
                respChecksum1 = int(response[-1])
                respChecksum2 = int(response[-2])
                crc = self.calc_crc(self.calc_crc(0, bytes([sequence, dataLen])), dataBytes)
                calcChecksum1 = (crc >> 8) & 255
                calcChecksum2 = crc & 255

                if respChecksum1 != calcChecksum1 or respChecksum2 != calcChecksum2:
                    _LOGGER.debug(
                        f"expect checksum: {respChecksum1}, {respChecksum2}\n"
                        f"received checksum: {calcChecksum1}, {calcChecksum2}"
                    )
                    return -4

            data_offset = 2 if frameCtrlData.hasFrag() else 0

            self.notification.addData(dataBytes, data_offset)
            return 1 if frameCtrlData.hasFrag() else 0
        except Exception as e:
            _LOGGER.debug(e)
            return -100

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
                # luba_msg = parse_custom_data(data)  # parse to protobuf message
                return data

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
            ack = self.mAck.get()
            return ack == expectAck
        except Exception as err:
            _LOGGER.debug(err)
            return False

    def generate_send_sequence(self) -> int:
        return self.mSendSequence.increment_and_get() & 255

    async def post_custom_data_bytes(self, data: bytes) -> None:
        if data is None:
            return
        type_val = self.getTypeValue(1, 19)
        try:
            suc = await self.post(self.mEncrypted, self.mChecksum, self.mRequireAck, type_val, data)
            # int status = suc ? 0 : BlufiCallback.CODE_WRITE_DATA_FAILED
            # onPostCustomDataResult(status, data)
            # _LOGGER.debug(suc)
        except Exception as err:
            await self.client.disconnect()
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
        sequence = self.generate_send_sequence()
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
            sequence = self.generate_send_sequence()
            postBytes = self.getPostBytes(type_of, encrypt, checksum, require_ack, frag, sequence, chunk)
            # _LOGGER.debug("sequence")
            # _LOGGER.debug(sequence)
            posted = await self.gatt_write(postBytes)
            if posted is not None:
                return False

            if not frag:
                return not require_ack or self.receiveAck(sequence)

            if require_ack and not self.receiveAck(sequence):
                return False

            _LOGGER.debug("sleeping 0.01")
            await sleep(0.01)
            if require_ack and not self.receiveAck(sequence):
                return False
            else:
                return True

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

        if data is not None:
            byteOS.write(data)

        _LOGGER.debug(byteOS.getvalue())
        return byteOS.getvalue()

    @staticmethod
    def calc_crc(initial: int, data: bytes | bytearray) -> int:
        """Calculate CRC value for given initial value and byte array.

        Args:
            initial: Initial CRC value
            data: Bytes to calculate CRC for

        Returns:
            Calculated CRC value (16-bit)

        Raises:
            TypeError: If data is not bytes or bytearray
            ValueError: If initial value is out of valid range

        """
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Data must be bytes or bytearray")

        if not 0 <= initial <= 0xFFFF:
            raise ValueError("Initial value must be between 0 and 65535")

        try:
            crc = (~initial) & 0xFFFF

            for byte in data:
                crc = ((crc << 8) ^ CRC_TB[byte ^ (crc >> 8)]) & 0xFFFF

            return (~crc) & 0xFFFF

        except Exception as e:
            _LOGGER.error("Error calculating CRC: %s", str(e))
            raise
