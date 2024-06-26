from enum import Enum


class DeviceType(Enum):
    UNKNOWN = (-1, "UNKNOWN", "Unknown")
    RTK = (0, "RTK", "RTK")
    LUBA = (1, "Luba", "Luba 1")
    LUBA_2 = (2, "Luba-VS", "Luba 2")
    LUBA_YUKA = (3, "Yuka-", "Yuka")

    def __init__(self, value: int, name: str, model: str):
        self._value = value
        self._name = name
        self._model = model

    def get_name(self):
        return self._name
    
    def get_model(self):
        return self._model

    def get_value(self):
        return self._value

    def get_value_str(self):
        return str(self._value)

    def set_value(self, value):
        self._value = value

    @staticmethod
    def valueof(value):
        if value == 0:
            return DeviceType.RTK
        elif value == 1:
            return DeviceType.LUBA
        elif value == 2:
            return DeviceType.LUBA_2
        elif value == 3:
            return DeviceType.LUBA_YUKA
        else:
            return DeviceType.UNKNOWN

    @staticmethod
    def value_of_str(device_name, product_key=""):
        if not device_name and not product_key:
            return DeviceType.UNKNOWN

        try:
            substring = device_name[:3]
            substring2 = device_name[:7]

            if DeviceType.RTK.name in substring or DeviceType.contain_rtk_product_key(product_key):
                return DeviceType.RTK
            elif DeviceType.LUBA_2.name in substring2 or DeviceType.contain_luba_2_product_key(product_key):
                return DeviceType.LUBA_2
            elif DeviceType.LUBA_YUKA.name in substring2:
                return DeviceType.LUBA_YUKA
            elif DeviceType.LUBA.name in substring2 or DeviceType.contain_luba_product_key(product_key):
                return DeviceType.LUBA
            else:
                return DeviceType.UNKNOWN
        except Exception:
            return DeviceType.UNKNOWN

    @staticmethod
    def has_4g(device_name, product_key=""):
        if not product_key:
            device_type = DeviceType.value_of_str(device_name)
        else:
            device_type = DeviceType.value_of_str(device_name, product_key)

        return device_type.get_value() >= DeviceType.LUBA_2.get_value()

    @staticmethod
    def is_luba1(device_name, product_key=""):
        if not product_key:
            device_type = DeviceType.value_of_str(device_name)
        else:
            device_type = DeviceType.value_of_str(device_name, product_key)

        return device_type.get_value() == DeviceType.LUBA.get_value()

    @staticmethod
    def is_luba_2(device_name, product_key=""):
        if not product_key:
            device_type = DeviceType.value_of_str(device_name)
        else:
            device_type = DeviceType.value_of_str(device_name, product_key)

        return device_type.get_value() >= DeviceType.LUBA_2.get_value()

    @staticmethod
    def is_yuka(device_name):
        return DeviceType.value_of_str(device_name).get_value() == DeviceType.LUBA_YUKA.get_value()

    @staticmethod
    def is_rtk(device_name, product_key=""):
        if not product_key:
            device_type = DeviceType.value_of_str(device_name)
        else:
            device_type = DeviceType.value_of_str(device_name, product_key)

        return DeviceType.RTK.get_value() <= device_type.get_value() < DeviceType.LUBA.get_value()

    @staticmethod
    def contain_rtk_product_key(product_key):
        if not product_key:
            return False
        return product_key in ["a1qXkZ5P39W", "a1Nc68bGZzX"]

    @staticmethod
    def contain_luba_product_key(product_key):
        if not product_key:
            return False
        return product_key in ["a1UBFdq6nNz", "a1x0zHD3Xop", "a1pvCnb3PPu", "a1kweSOPylG", "a1JFpmAV5Ur", "a1BmXWlsdbA", "a1jOhAYOIG8", "a1K4Ki2L5rK", "a1ae1QnXZGf", "a1nf9kRBWoH", "a1ZU6bdGjaM"]

    @staticmethod
    def contain_luba_2_product_key(product_key):
        if not product_key:
            return False
        return product_key in ["a1iMygIwxFC", "a1LLmy1zc0j", "a1LLmy1zc0j"]

    def is_support_video(self):
        return self == DeviceType.LUBA_YUKA
