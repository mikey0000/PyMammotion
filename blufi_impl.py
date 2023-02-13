

from asyncio import sleep
from io import BytesIO
import itertools
import json
import queue
import time

from bleak import BleakClient

from framectrldata import FrameCtrlData
import proto.esp_driver_pb2
import proto.luba_msg_pb2


address = "90:38:0C:6E:EE:9E"
MODEL_NBR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

UART_SERVICE_UUID = "0000ffff-0000-1000-8000-00805f9b34fb"
UART_RX_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
UART_TX_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"


# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ServiceName:00001801-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ---CharacterName:00002a05-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ServiceName:00001800-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ---CharacterName:00002a00-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ---CharacterName:00002a01-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ---CharacterName:00002aa6-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.761 21981 22174 E EspBleUtil: ServiceName:0000ffff-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.762 21981 22174 E EspBleUtil: ---CharacterName:0000ff01-0000-1000-8000-00805f9b34fb
# 01-31 14:06:23.762 21981 22174 E EspBleUtil: ---CharacterName:0000ff02-0000-1000-8000-00805f9b34fb


UUID_SERVICE = "0000ffff-0000-1000-8000-00805f9b34fb"
UUID_WRITE_CHARACTERISTIC = "0000ff01-0000-1000-8000-00805f9b34fb"
UUID_NOTIFICATION_CHARACTERISTIC = "0000ff02-0000-1000-8000-00805f9b34fb"
UUID_NOTIFICATION_DESCRIPTOR = "00002902-0000-1000-8000-00805f9b34fb"

CLIENT_CHARACTERISTIC_CONFIG_DESCRIPTOR_UUID = "00002902-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE = "0000180F-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHARACTERISTIC = "00002A19-0000-1000-8000-00805f9b34fb"
GENERIC_ATTRIBUTE_SERVICE = "00001801-0000-1000-8000-00805f9b34fb"
SERVICE_CHANGED_CHARACTERISTIC = "00002A05-0000-1000-8000-00805f9b34fb"


class Blufi:
    AES_TRANSFORMATION = "AES/CFB/NoPadding"
    DEFAULT_PACKAGE_LENGTH = 20
    DH_G = "2"
    DH_P = "cf5cf5c38419a724957ff5dd323b9c45c3cdd261eb740f69aa94b8bb1a5c96409153bd76b24222d03274e4725a5406092e9e82e9135c643cae98132b0d95f7d65347c68afc1e677da90e51bbab5f5cf429c291b4ba39c6b2dc5e8c7231e46aa7728e87664532cdf547be20c9a3fa8342be6e34371a27c06f7dc0edddd2f86373"
    MIN_PACKAGE_LENGTH = 20
    NEG_SECURITY_SET_ALL_DATA = 1
    NEG_SECURITY_SET_TOTAL_LENGTH = 0
    PACKAGE_HEADER_LENGTH = 4
    # TAG = "BlufiClientImpl"
    # BluetoothDevice mDevice
    # BluetoothGatt mGatt
    # BluetoothGattCharacteristic mNotifyChar
    # BlufiNotifyData mNotifyData
    # BlufiCallback mUserBlufiCallback
    # BluetoothGattCallback mUserGattCallback
    # BluetoothGattCharacteristic mWriteChar
    mPrintDebug = False
    mWriteTimeout = -1
    mPackageLengthLimit = -1
    mBlufiMTU = -1
    mEncrypted = False
    mChecksum = False
    mRequireAck = False
    mConnectState = 0
    mSendSequence = itertools.count()
    mReadSequence = itertools.count()
    mAck = queue.Queue()

    def __init__(self, client: BleakClient):
        self.client = client
        pass


    def getDeviceVersionMain(self):
        commEsp = proto.esp_driver_pb2.CommEsp()
        
        
        infoReqId = commEsp.DrvDevInfoReqId()
        infoReqId.id = 1
        infoReqId.type = 6
        infoReq = commEsp.DrvDevInfoReq()
        reqIdReq = infoReq.req_ids.add()
        reqIdReq = [infoReqId]
        # commEsp.DrvDevInfoReq = infoReq
        # drvDevInfoReq.addReqIds(drvDevInfoReqId);
        # EspDriver.DrvDevInfoReq devInfoReq = drvDevInfoReq.build();
        lubaMsg = proto.luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = proto.luba_msg_pb2.MSG_CMD_TYPE_ESP
        lubaMsg.sender = proto.luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = proto.luba_msg_pb2.DEV_COMM_ESP
        lubaMsg.msgattr = proto.luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.esp.CopyFrom(commEsp)
        print(lubaMsg)
        print(commEsp)
        bytes = lubaMsg.SerializeToString()
        # bytes = lubaMsg.toByteArray();
        # await self.postCustomDataBytes(bytes)
    


    async def getDeviceInfo(self):
        await self.postCustomData(Blufi.getJsonString(63))
    

    async def requestDeviceStatus(self):
        request = False
        type = self.getTypeValue(0, 5)
        try:
            request = await self.post(Blufi.mEncrypted, Blufi.mChecksum, False, type, None)
            print(request)
        except Exception as err:
            # Log.w(TAG, "post requestDeviceStatus interrupted")
            request = False
            print(err)
        
        # if not request:
        #     onStatusResponse(BlufiCallback.CODE_WRITE_DATA_FAILED, null)


    async def requestDeviceVersion(self):
        request = False
        type = self.getTypeValue(0, 7)
        try:
            request = await self.post(Blufi.mEncrypted, Blufi.mChecksum, False, type, None)
            print(request)
        except Exception as err:
            # Log.w(TAG, "post requestDeviceStatus interrupted")
            request = False
            print(err)
        


    async def postCustomDataBytes(self, data: bytearray):
        if (data == None):
            return
        type = self.getTypeValue(1, 19)
        try:
            suc = await self.post(self.mEncrypted, self.mChecksum, self.mRequireAck, type, data)
            # int status = suc ? 0 : BlufiCallback.CODE_WRITE_DATA_FAILED
            # onPostCustomDataResult(status, data)
            print(suc)
            print(data)
        except Exception as err:
            print(err)

    async def postCustomData(self, dataStr: str):
        data = dataStr.encode()
        if (data == None):
            return
        type = self.getTypeValue(1, 19)
        try:
            suc = await self.post(self.mEncrypted, self.mChecksum, self.mRequireAck, type, data)
            # int status = suc ? 0 : BlufiCallback.CODE_WRITE_DATA_FAILED
            # onPostCustomDataResult(status, data)
            print(suc)
            print(data)
        except Exception as err:
            print(err)
        
        
    
    def getTypeValue(self, type: int, subtype: int):
        return (subtype << 2) | type
    

    async def post(self, encrypt: bool, checksum: bool, requireAck: bool, type: int, data: bytearray) -> bool:
        if data == None:
            return await self.postNonData(encrypt, checksum, requireAck, type)

        return await self.postContainsData(encrypt, checksum, requireAck, type, data)
        
    async def gattWrite(self, data: bytearray) -> bool:
        chunk_size = self.client.mtu_size - 3
        for chunk in (
            data[i : i + chunk_size] for i in range(0, len(data), chunk_size)
        ):
            await self.client.write_gatt_char(UUID_WRITE_CHARACTERISTIC, chunk, True)

    async def postNonData(self, encrypt: bool, checksum: bool, requireAck: bool, type: int) -> bool:
        sequence = self.generateSendSequence()
        postBytes = self.getPostBytes(type, encrypt, checksum, requireAck, False, sequence, None)
        posted = await self.gattWrite(postBytes)
        return posted and (not requireAck or self.receiveAck(sequence))


    async def postContainsData(self, encrypt: bool,  checksum: bool,  requireAck: bool,  type: int, data: bytearray) -> bool:
        dataIS = BytesIO(data)
        dataContent = BytesIO()
        i = 20
            
        return await self.gattWrite(data)
        # pkgLengthLimit = i
        # postDataLengthLimit2 = (pkgLengthLimit - 4) - 2
        # if (not checksum):
        #     postDataLengthLimit = postDataLengthLimit2
        # else:
        #     postDataLengthLimit = postDataLengthLimit2 - 2
        
        # dataBuf = bytearray([postDataLengthLimit])
        # while (True):
        #     read = dataIS.read(dataBuf, 0, dataBuf.length)
        #     if (read == -1):
        #         return True
            
        #     dataContent.write(dataBuf, 0, read)
        #     if (dataIS.available() > 0 and dataIS.available() <= 2):
        #         dataContent.write(dataBuf, 0, dataIS.read(dataBuf, 0, dataIS.available()))
            
        #     frag = dataIS.available() > 0
        #     sequence = self.generateSendSequence()
        #     if (frag):
        #         totalLen = dataContent.size() + dataIS.available()
        #         tempData = dataContent.toByteArray()
        #         dataContent.reset()
        #         dataContent.write(totalLen & 255)
        #         dataContent.write((totalLen >> 8) & 255)
        #         dataContent.write(tempData, 0, tempData.length)
            
        #     postBytes = self.getPostBytes(type, encrypt, checksum, requireAck, frag, sequence, dataContent.toByteArray())
        #     dataContent.reset()
        #     posted = await self.gattWrite(postBytes)
        #     if (not posted):
        #         return False
            
        #     if (not frag):
        #         return not requireAck or self.receiveAck(sequence)
                
        #     if (requireAck and not self.receiveAck(sequence)):
        #         return False
            
        await sleep(10)
        
    

    def getPostBytes(self, type: int,  encrypt: bool, checksum: bool,  requireAck: bool,  hasFrag: bool, sequence: int, data: bytearray) -> bytearray:
        data2 = data
        byteOS = BytesIO()
        dataLength = (0 if data2 == None  else data2.length)
        frameCtrl = FrameCtrlData.getFrameCTRLValue(encrypt, checksum, 0, requireAck, hasFrag)
        byteOS.write(str(type).encode())
        byteOS.write(str(frameCtrl).encode())
        byteOS.write(str(sequence).encode())
        byteOS.write(str(dataLength).encode())
        checksumBytes = None
        # if (checksum):
        #     byte[] willCheckBytes = {(byte) sequence, (byte) dataLength}
        #     crc = BlufiCRC.calcCRC(0, willCheckBytes)
        #     if (dataLength > 0) {
        #         crc = BlufiCRC.calcCRC(crc, data2)
        #     }
        #     checksumBytes = new byte[]{(byte) (crc & 255), (byte) ((crc >> 8) & 255)}
        
        # if (encrypt and data2 != null and data2.length > 0) {
        #     BlufiAES aes = new BlufiAES(this.mAESKey, AES_TRANSFORMATION, generateAESIV(sequence))
        #     data2 = aes.encrypt(data2)
        # }
        if (data2 != None):
            byteOS.write(data2, 0, data2.length)
        
        if (checksumBytes != None):
            byteOS.write(checksumBytes[0])
            byteOS.write(checksumBytes[1])
        print(byteOS.getvalue())
        return byteOS.getvalue()
    

    def receiveAck(self, expectAck: int) -> bool:
        try:
            ack = self.mAck.get()
            return ack == expectAck
        except Exception as err:
            print(err)
            return False
        

    def generateSendSequence(self):
        return next(self.mSendSequence) & 255


    def getJsonString(cmd: int) -> str:
        
        try:
            return json.dumps({
                "cmd": cmd,
                "id": round(time.time() * 1000)
            })
        except Exception as err:
            
            return ""
        
    
