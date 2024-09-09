class FrameCtrlData:
    FRAME_CTRL_POSITION_CHECKSUM = 1
    FRAME_CTRL_POSITION_DATA_DIRECTION = 2
    FRAME_CTRL_POSITION_ENCRYPTED = 0
    FRAME_CTRL_POSITION_FRAG = 4
    FRAME_CTRL_POSITION_REQUIRE_ACK = 3
    mValue = 0

    def __init__(self, frameCtrlValue) -> None:
        self.mValue = frameCtrlValue

    def check(self, position):
        return ((self.mValue >> position) & 1) == 1

    def isEncrypted(self):
        return self.check(0)

    def isChecksum(self):
        return self.check(1)

    def isAckRequirement(self):
        return self.check(3)

    def hasFrag(self):
        return self.check(4)

    @staticmethod
    def getFrameCTRLValue(encrypted, checksum, direction, requireAck, frag):
        frame = 0
        if encrypted:
            frame = 0 | 1
        if checksum:
            frame |= 2
        if direction == 1:
            frame |= 4
        if requireAck:
            frame |= 8
        if frag:
            return frame | 16
        return frame
