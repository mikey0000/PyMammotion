import copy
import math


class RockerControlUtil:
    """generated source for class RockerControlUtil"""

    instance_ = None
    list_ = []
    thresholdValue_1 = 30
    thresholdValue_2 = 7
    thresholdValue_3 = 15

    def __init__(self) -> None:
        """Generated source for method __init__"""

    @classmethod
    def getInstance(cls):
        """Return the instance of RockerControlUtil if it exists, otherwise create
        a new instance.

        This method checks if an instance of RockerControlUtil exists. If not,
        it creates a new instance and returns it.

        Args:
            cls (class): The class for which the instance is being retrieved.

        Returns:
            RockerControlUtil: An instance of RockerControlUtil.

        """
        if cls.instance_ == None:
            cls.instance_ = RockerControlUtil()
        return cls.instance_

    def transfrom(self, f, f2):
        """Perform a transformation based on the input angles and distance.

        This method calculates the transformation based on the input angle 'f'
        and distance 'f2'. It determines the appropriate radians based on the
        angle and performs the transformation.

        Args:
            f (float): The angle in degrees for transformation.
            f2 (float): The distance for transformation.

        Returns:
            list: A list containing the transformed coordinates.

        """
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
        """Calculate the transformation of input angles to radians and perform
        trigonometric calculations.

        This method takes two input parameters, an angle 'f' and a value 'f2',
        and calculates the corresponding radians based on the angle. It then
        performs trigonometric calculations using the radians and 'f2' value to
        generate a list of transformed values.

        Args:
            self: The instance of the class.
            f (float): The input angle in degrees.
            f2 (float): The input value for trigonometric calculations.

        Returns:
            list: A list containing the transformed values based on trigonometric
                calculations.

        """
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
        """Calculate the transformation of input angles to radians and perform
        trigonometric calculations.

        This method calculates the transformation of input angles to radians
        based on certain threshold values. It then performs trigonometric
        calculations using sine and cosine functions to determine the output
        values.

        Args:
            self: The object instance.
            f (float): The input angle in degrees.
            f2 (float): The input value for trigonometric calculations.

        Returns:
            list: A list containing the calculated values based on trigonometric
                functions.

        """
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
