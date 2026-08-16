import math


def parse_double(val: float, d: float):
    """Scale ``val`` down by ``10 ** d``, undoing the device's fixed-point encoding."""
    return val / math.pow(10.0, d)
