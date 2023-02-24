

from asyncio import sleep
from io import BytesIO
import itertools
import json
import queue
import sys
import time

from bleak import BleakClient
from jsonic import serialize

from luba_desktop.blelibs.framectrldata import FrameCtrlData
from luba_desktop.proto import mctrl_driver_pb2, luba_msg_pb2, esp_driver_pb2, mctrl_nav_pb2

from luba_desktop.blelibs.model.ExecuteBoarder import ExecuteBorder, ExecuteBorderParams
from luba_desktop.utility.rocker_util import RockerControlUtil

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


    async def getDeviceVersionMain(self):
        commEsp = esp_driver_pb2.CommEsp()
        
        reqIdReq = commEsp.todev_devinfo_req.req_ids.add()
        reqIdReq.id = 1
        reqIdReq.type = 6
        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_ESP
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.DEV_COMM_ESP
        lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.esp.CopyFrom(commEsp)
        print(lubaMsg)
        bytes = lubaMsg.SerializeToString()
        await self.postCustomDataBytes(bytes)
    
    async def sendTodevBleSync(self):
        commEsp = esp_driver_pb2.CommEsp()
        
        commEsp.todev_ble_sync = 1
        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_ESP
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.DEV_COMM_ESP
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.esp.CopyFrom(commEsp)
        print(lubaMsg)
        bytes = lubaMsg.SerializeToString()
        await self.postCustomDataBytes(bytes)
      

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
    
    async def returnToDock(self):
        mctrlNav = mctrl_nav_pb2.MctlNav()
        navTaskCtrl = mctrl_nav_pb2.NavTaskCtrl()
        navTaskCtrl.type = 1
        navTaskCtrl.action = 5
        navTaskCtrl.result = 0
        mctrlNav.todev_taskctrl.CopyFrom(navTaskCtrl)
        
        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_NAV
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.DEV_MAINCTL
        lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.nav.CopyFrom(mctrlNav)
        print(lubaMsg)
        bytes = lubaMsg.SerializeToString()
        await self.postCustomDataBytes(bytes)
            
    async def leaveDock(self):
        mctrlNav = mctrl_nav_pb2.MctlNav()
        mctrlNav.todev_one_touch_leave_pile = 1

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_NAV
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.DEV_MAINCTL
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.nav.CopyFrom(mctrlNav)
        print(lubaMsg)
        bytes = lubaMsg.SerializeToString()
        await self.postCustomDataBytes(bytes)


    async def setKnifeHight(self, height: int):
        mctrlDriver = mctrl_driver_pb2.MctrlDriver()
        drvKnifeHeight = mctrl_driver_pb2.DrvKnifeHeight()
        drvKnifeHeight.knifeHeight = height
        mctrlDriver.todev_knife_hight_set.CopyFrom(drvKnifeHeight)

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_EMBED_DRIVER
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.DEV_MAINCTL
        lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.driver.CopyFrom(mctrlDriver)
        print(lubaMsg)
        bytes = lubaMsg.SerializeToString()
        await self.postCustomDataBytes(bytes)

    async def setKnifeControl(self, onOff: int):
        mctlsys = mctrl_sys_pb2.MctlSys()
        sysKnifeControl = mctrl_sys_pb2.SysKnifeControl()
        sysKnifeControl.knifeStatus = onOff
        mctlsys.todev_knife_ctrl.CopyFrom(sysKnifeControl)

        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_EMBED_SYS
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.DEV_MAINCTL
        lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_REQ
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        lubaMsg.sys.CopyFrom(mctlsys)
        print(lubaMsg)
        bytes = lubaMsg.SerializeToString()
        await self.postCustomDataBytes(bytes)

    async def transformSpeed(self, linear: float, percent: float):
            
        transfrom3 = RockerControlUtil.getInstance().transfrom3(linear, percent)
        if (transfrom3 != None and len(transfrom3) > 0):
            linearSpeed = transfrom3[0] * 10
            angularSpeed = (int) (transfrom3[1] * 4.5)
            
            await self.sendMovement(linearSpeed, angularSpeed)

    async def transformBothSpeeds(self, linear: float, angular: float, linearPercent: float, angularPercent: float):
        transfrom3 = RockerControlUtil.getInstance().transfrom3(linear, linearPercent)
        transform4 = RockerControlUtil.getInstance().transfrom3(angular, angularPercent)
        
        if (transfrom3 != None and len(transfrom3) > 0):
            linearSpeed = transfrom3[0] * 10
            angularSpeed = (int) (transform4[1] * 4.5)
            print(linearSpeed, angularSpeed)
            await self.sendMovement(linearSpeed, angularSpeed)
    

    
    # asnyc def transfromDoubleRockerSpeed(float f, float f2, boolean z):
    #         transfrom3 = RockerControlUtil.getInstance().transfrom3(f, f2)
    #         if (transfrom3 != null && transfrom3.size() > 0):
    #             if (z):
    #                 this.linearSpeed = transfrom3.get(0).intValue() * 10
    #             else
    #                 this.angularSpeed = (int) (transfrom3.get(1).intValue() * 4.5d)
                
            
    #         if (this.countDownTask == null):
    #             testSendControl()
    



    async def sendMovement(self, linearSpeed: int, angularSpeed: int):
        mctrlDriver = mctrl_driver_pb2.MctrlDriver()
        
        drvMotionCtrl = mctrl_driver_pb2.DrvMotionCtrl()
        drvMotionCtrl.setLinearSpeed = linearSpeed
        drvMotionCtrl.setAngularSpeed = angularSpeed
        mctrlDriver.todev_devmotion_ctrl.CopyFrom(drvMotionCtrl)
        lubaMsg = luba_msg_pb2.LubaMsg()
        lubaMsg.msgtype = luba_msg_pb2.MSG_CMD_TYPE_EMBED_DRIVER
        lubaMsg.sender = luba_msg_pb2.DEV_MOBILEAPP
        lubaMsg.rcver = luba_msg_pb2.DEV_MAINCTL
        lubaMsg.msgattr = luba_msg_pb2.MSG_ATTR_NONE
        lubaMsg.timestamp = self.current_milli_time()
        lubaMsg.seqs = 1
        lubaMsg.version = 1
        lubaMsg.subtype = 1
        
        lubaMsg.driver.CopyFrom(mctrlDriver)
        print(lubaMsg)
        bytes = lubaMsg.SerializeToString()
        await self.postCustomDataBytes(bytes)
  
        

    async def sendBorderPackage(self, executeBorder: ExecuteBorder):
        await self.postCustomData(serialize(executeBorder))
    
        


    async def postCustomDataBytes(self, data: bytearray):
        if (data == None):
            return
        type = self.getTypeValue(1, 19)
        try:
            suc = await self.post(self.mEncrypted, self.mChecksum, self.mRequireAck, type, data)
            # int status = suc ? 0 : BlufiCallback.CODE_WRITE_DATA_FAILED
            # onPostCustomDataResult(status, data)
            print(suc)
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
        await self.client.write_gatt_char(UUID_WRITE_CHARACTERISTIC, data, True)

    async def postNonData(self, encrypt: bool, checksum: bool, requireAck: bool, type: int) -> bool:
        sequence = self.generateSendSequence()
        postBytes = self.getPostBytes(type, encrypt, checksum, requireAck, False, sequence, None)
        posted = await self.gattWrite(postBytes)
        return posted and (not requireAck or self.receiveAck(sequence))


    async def postContainsData(self, encrypt: bool,  checksum: bool,  requireAck: bool,  type: int, data: bytearray) -> bool:
        chunk_size = 200 -3  #self.client.mtu_size - 3

        chunks = list()
        for i in range(0, len(data), chunk_size):
            if(i + chunk_size > len(data)):
                chunks.append(data[i: len(data)])
            else:
                chunks.append(data[i : i + chunk_size])
    
        for index, chunk in enumerate(chunks):
            print("entered for loop")
            # frag = i < len(data)
            frag = index != len(chunks)-1
            sequence = self.generateSendSequence()
            postBytes = self.getPostBytes(type, encrypt, checksum, requireAck, frag, sequence, chunk)
            
            posted = await self.gattWrite(postBytes)
            if (posted != None):
                return False
            
            if (not frag):
                print("not frag")
                return not requireAck or self.receiveAck(sequence)
                
            # if (requireAck and not self.receiveAck(sequence)): TODO: 
            #     return False
            # else:
            await sleep(0.01)

        
    

    def getPostBytes(self, type: int,  encrypt: bool, checksum: bool,  requireAck: bool,  hasFrag: bool, sequence: int, data: bytearray) -> bytearray:
        
        byteOS = BytesIO()
        dataLength = (0 if data == None else len(data))
        frameCtrl = FrameCtrlData.getFrameCTRLValue(encrypt, checksum, 0, requireAck, hasFrag)
        byteOS.write(type.to_bytes(1,sys.byteorder))
        byteOS.write(frameCtrl.to_bytes(1, sys.byteorder))
        byteOS.write(sequence.to_bytes(1, sys.byteorder))
        byteOS.write(dataLength.to_bytes(1, sys.byteorder))
        
        if (data != None):
            byteOS.write(data)

        
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


    def current_milli_time(self):
        return round(time.time() * 1000)
        
    
