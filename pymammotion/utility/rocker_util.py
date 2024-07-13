import copy
import math


class RockerControlUtil:
    """generated source for class RockerControlUtil"""

    instance_ = None
    list_ = []
    thresholdValue_1 = 30
    thresholdValue_2 = 7
    thresholdValue_3 = 15

    def __init__(self):
        """Generated source for method __init__"""

    @classmethod
    def getInstance(cls):
        """Generated source for method getInstance"""
        if cls.instance_ == None:
            cls.instance_ = RockerControlUtil()
        return cls.instance_

    def transfrom(self, f, f2):
        """Generated source for method transfrom"""
        radians = 0.0
        self.list_.clear()
        i = self.thresholdValue_2
        if f > 90 - i and f < i + 90:
            radians = math.radians(90.0)
        elif f > 270 - i and f < i + 270:
            radians = math.radians(270.0)
        elif f > 180 - i and f < i + 180:
            radians = math.radians(180.0)
        elif f < i and f > 360 - i:
            radians = math.radians(0.0)
        else:
            if f > i:
                i2 = self.thresholdValue_2
                if f < 90 - i2:
                    radians = math.radians(90 - i2)

            i3 = self.thresholdValue_1
            if f > i3 + 90 and f < 180 - i:
                radians = math.radians(i3 + 90)
            elif f > i + 180 and f < 270 - i3:
                radians = math.radians(270 - i3)
            elif f > i3 + 270 and f < 360 - i:
                radians = math.radians(i3 + 270)
            else:
                radians = math.radians(f)
        d = f2
        self.list_.append(int(math.sin(radians) * d))
        self.list_.append(int(d * math.cos(radians)))
        return copy.copy(self.list_)

    def transfrom2(self, f, f2):
        """Generated source for method transfrom2"""
        radians = 0.0
        self.list_.clear()
        i = self.thresholdValue_2
        if f > 90 - i and f < i + 90:
            radians = math.radians(90.0)
        elif f > 270 - i and f < i + 270:
            radians = math.radians(270.0)
        else:
            i2 = self.thresholdValue_3
            if f > 180 - i2 and f < i2 + 180:
                radians = math.radians(0.0)
            elif f < i2 or f > 360 - i2:
                radians = math.radians(180.0)
            else:
                if f > i2:
                    i3 = self.thresholdValue_1
                    if f < 90 - i3:
                        radians = math.radians(i3 + 90)
                i4 = self.thresholdValue_1
                if f > i4 + 90 and f < 180 - i2:
                    radians = math.radians(90 - i4)
                elif f > i2 + 180 and f < 270 - i4:
                    radians = math.radians(i4 + 270)
                elif f > i4 + 270 and f < 360 - i2:
                    radians = math.radians(270 - i4)
                elif f > 270 - i4 and f < 270 - i:
                    radians = math.radians((270.0 - f) + 270.0)
                elif f > i + 270 and f < i4 + 270:
                    radians = math.radians(270.0 - (f - 270.0))
                elif f > 90 - i4 and f < 90 - i:
                    radians = math.radians((90.0 - f) + 90.0)
                elif f > i + 90 and f < i4 + 90:
                    radians = math.radians(90.0 - (f - 90.0))
                else:
                    radians = math.radians(f)
        d = f2
        self.list_.append(int(math.sin(radians) * d))
        self.list_.append(int(d * math.cos(radians)))
        return copy.copy(self.list_)

    def transfrom3(self, f, f2):
        """Generated source for method transfrom3"""
        radians = 0.0
        self.list_.clear()
        i = self.thresholdValue_2
        if f > 90 - i and f < i + 90:
            radians = math.radians(90.0)
        elif f > 270 - i and f < i + 270:
            radians = math.radians(270.0)
        else:
            i2 = self.thresholdValue_3
            if f > 180 - i2 and f < i2 + 180:
                radians = math.radians(180.0)
            elif f < i2 or f > 360 - i2:
                radians = math.radians(0.0)
            else:
                if f > i2:
                    i3 = self.thresholdValue_1
                    if f < 90 - i3:
                        radians = math.radians(90 - i3)
                i4 = self.thresholdValue_1
                if f > i4 + 90 and f < 180 - i2:
                    radians = math.radians(i4 + 90)
                elif f > i2 + 180 and f < 270 - i4:
                    radians = math.radians(i4 + 270)
                elif f > i4 + 270 and f < 360 - i2:
                    radians = math.radians(270 - i4)
                elif f > 270 - i4 and f < 270 - i:
                    radians = math.radians((270.0 - f) + 270.0)
                elif f > i + 270 and f < i4 + 270:
                    radians = math.radians(270.0 - (f - 270.0))
                else:
                    radians = math.radians(f)
        d = f2
        self.list_.append(int(math.sin(radians) * d))
        self.list_.append(int(d * math.cos(radians)))
        return copy.copy(self.list_)
