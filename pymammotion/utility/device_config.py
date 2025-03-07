from pymammotion.data.model.device_limits import DeviceLimits
from pymammotion.utility.device_type import DeviceType

default_luba_config = {
    "blade_height": {"min": 20, "max": 35},
    "working_speed": {"min": 0.2, "max": 1.2},
    "path_spacing": {"min": 8, "max": 14},
    "work_area_num_max": 60,
    "display_image_type": 0,
}

default_yuka_config = {
    "blade_height": {"min": 0, "max": 0},
    "working_speed": {"min": 0.2, "max": 0.6},
    "path_spacing": {"min": 8, "max": 30},
    "work_area_num_max": 60,
    "display_image_type": 0,
}


class DeviceConfig:
    def __init__(self) -> None:
        # Dictionary to store all device configurations

        # Device mode configurations
        self.default_list = {
            "a1ZU6bdGjaM": {
                "extMod": "LubaAWD1000723",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.4,
                "work_area_num_max": 3,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 1,
            },
            "a1nf9kRBWoH": {
                "extMod": "LubaAWD3000723",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 6,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 1,
            },
            "a1ae1QnXZGf": {
                "extMod": "LubaAWD1000743",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 3,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 1,
            },
            "a1K4Ki2L5rK": {
                "extMod": "LubaAWD5000723",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "a1jOhAYOIG8": {
                "extMod": "LubaAWD5000743LS",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "a1BmXWlsdbA": {
                "extMod": "LubaAWD5000743",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "a1JFpmAV5Ur": {
                "extMod": "Kumar-10",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "a1kweSOPylG": {
                "extMod": "LubaAWD3000723",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 6,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 1,
            },
            "a1pvCnb3PPu": {
                "extMod": "LubaAWD1000743",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 3,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 1,
            },
            "a1x0zHD3Xop": {
                "extMod": "LubaAWD5000743LS",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "a1UBFdq6nNz": {
                "extMod": "LubaAWD5000723",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "a1FbaU4Bqk5": {
                "extMod": "LubaAWD5000743",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
        }

        self.inner_list = {
            "HM010060LBAWD10": {
                "extMod": "LubaAWD1000",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 3,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 1,
            },
            "HM030080LBAWD30": {
                "extMod": "LubaAWD3000",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 6,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 1,
            },
            "HM050080LBAWD50": {
                "extMod": "LubaAWD5000",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM030060LBAWD50OMNI": {
                "extMod": "LubaAWD5000",
                "blade_height_min": 30,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 1,
            },
            "HM060100LBAWD50OMNIH": {
                "extMod": "LubaAWD5000H",
                "blade_height_min": 60,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM030070LBVAWD10OMNI": {
                "extMod": "Luba2AWD1000",
                "blade_height_min": 25,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM060100LBVAWD10OMNIH": {
                "extMod": "Luba2AWD1000H",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM030070LBVAWD30OMNI": {
                "extMod": "Luba2AWD3000",
                "blade_height_min": 25,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 20,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM060100LBVAWD30OMNIH": {
                "extMod": "Luba2AWD3000H",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 20,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM030070LBVAWD50OMNI": {
                "extMod": "Luba2AWD5000",
                "blade_height_min": 25,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 30,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM060100LBVAWD50OMNIH": {
                "extMod": "Luba2AWD5000H",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 30,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM030070LBVAWD100OMNI": {
                "extMod": "Luba2AWD10000",
                "blade_height_min": 25,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM060100LBVAWD100OMNIH": {
                "extMod": "Luba2AWD10000H",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM030070LB2PAWD30OMNI": {
                "extMod": "Luba2ProAWD3000",
                "blade_height_min": 25,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.8,
                "work_area_num_max": 60,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM060100LB2PAWD30OMNIH": {
                "extMod": "Luba2ProAWD3000NA",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.8,
                "work_area_num_max": 60,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM030070LB2PAWD50OMNI": {
                "extMod": "Luba2ProAWD5000",
                "blade_height_min": 25,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 1.0,
                "work_area_num_max": 60,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM060100LB2PAWD50OMNIH": {
                "extMod": "Luba2ProAWD5000NA",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 1.0,
                "work_area_num_max": 60,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM030070LB2PAWD100OMNI": {
                "extMod": "Luba2ProAWD10000",
                "blade_height_min": 25,
                "blade_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 1.0,
                "work_area_num_max": 60,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM060100LB2PAWD100OMNIH": {
                "extMod": "Luba2ProAWD10000NA",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 1.0,
                "work_area_num_max": 60,
                "path_spacing_min": 20,
                "path_spacing_max": 35,
                "display_image_type": 0,
            },
            "HM020065LB2MINIAWD08OMNI": {
                "extMod": "Luba2MiniAWD800",
                "blade_height_min": 20,
                "blade_height_max": 65,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 5,
                "path_spacing_max": 20,
                "display_image_type": 0,
            },
            "HM020065LB2MINIAWD15OMNI": {
                "extMod": "Luba2MiniAWD1500",
                "blade_height_min": 20,
                "blade_height_max": 65,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 5,
                "path_spacing_max": 20,
                "display_image_type": 0,
            },
            "HM020065LB2MINIAWD15OMNILD": {
                "extMod": "Luba2MiniAWD1500Lidar",
                "blade_height_min": 20,
                "blade_height_max": 65,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 5,
                "path_spacing_max": 20,
                "display_image_type": 0,
            },
            "HM055100LB2MINIAWD08OMNIH": {
                "extMod": "Luba2MiniAWD800NA",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 5,
                "path_spacing_max": 20,
                "display_image_type": 0,
            },
            "HM055100LB2MINIAWD15OMNIH": {
                "extMod": "Luba2MiniAWD1500NA",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 5,
                "path_spacing_max": 20,
                "display_image_type": 0,
            },
            "HM055100LB2MINIAWD15OMNIHLD": {
                "extMod": "Luba2MiniAWD1500NALidar",
                "blade_height_min": 55,
                "blade_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 5,
                "path_spacing_max": 20,
                "display_image_type": 0,
            },
            "HM030070YK06": {
                "extMod": "Yuka600",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM030100YK06H": {
                "extMod": "Yuka600NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM030070YK10": {
                "extMod": "Yuka1000",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM030100YK10H": {
                "extMod": "Yuka1000NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM030070YK15": {
                "extMod": "Yuka1500",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM030100YK15H": {
                "extMod": "Yuka1500NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM020090YK20": {
                "extMod": "Yuka2000",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM030100YK20H": {
                "extMod": "Yuka2000NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM020080YKMINI05": {
                "extMod": "YukaMini500",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 8,
                "path_spacing_max": 14,
                "display_image_type": 0,
            },
            "HM050090YKMINI05H": {
                "extMod": "YukaMini500NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 8,
                "path_spacing_max": 14,
                "display_image_type": 0,
            },
            "HM020080YKMINI08": {
                "extMod": "YukaMini800",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 8,
                "path_spacing_max": 14,
                "display_image_type": 0,
            },
            "HM050090YKMINI08H": {
                "extMod": "YukaMini800NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 8,
                "path_spacing_max": 14,
                "display_image_type": 0,
            },
            "HM020080YKMINI06": {
                "extMod": "YukaMini600",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 8,
                "path_spacing_max": 14,
                "display_image_type": 0,
            },
            "HM020080YKMINI07": {
                "extMod": "YukaMini700",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 8,
                "path_spacing_max": 14,
                "display_image_type": 0,
            },
            "HM050090YKMINI06H": {
                "extMod": "YukaMini600NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 8,
                "path_spacing_max": 14,
                "display_image_type": 0,
            },
            "HM050090YKMINI07H": {
                "extMod": "YukaMini700NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 8,
                "path_spacing_max": 14,
                "display_image_type": 0,
            },
            "HM020090YKPLUS15": {
                "extMod": "YukaPlus1500",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM020090YKPLUS20": {
                "extMod": "YukaPlus2000",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM030100YKPLUS15H": {
                "extMod": "YukaPlus1500NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM030100YKPLUS20H": {
                "extMod": "YukaPlus2000NA",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 15,
                "path_spacing_max": 30,
                "display_image_type": 0,
            },
            "HM020080MN23103": {
                "extMod": "MN231_1",
                "blade_height_min": 0,
                "blade_height_max": 0,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "path_spacing_min": 8,
                "path_spacing_max": 14,
                "display_image_type": 0,
            },
        }

    def get_device_config(self, int_mod_or_key: str) -> dict:
        """Look up device configuration by internal model code

        Args:
            int_mod (str): Internal model code

        Returns:
            dict: Device configuration or None if not found
            :param int_mod_or_key:

        """
        if found := self.inner_list.get(int_mod_or_key):
            return found
        else:
            return self.default_list.get(int_mod_or_key)

    def get_external_model(self, int_mod: str):
        """Get external model name for given internal model code

        Args:
            int_mod (str): Internal model code

        Returns:
            str: External model name or None if not found

        """
        config = self.get_device_config(int_mod)
        return config.get("extMod") if config else None

    def get_working_parameters(self, int_mod_or_key: str) -> DeviceLimits | None:
        """Get working parameters for given internal model code

        Args:
            int_mod (str): Internal model code

        Returns:
            dict: Working parameters or None if not found
            :param int_mod_or_key:

        """
        config = self.get_device_config(int_mod_or_key)
        if not config:
            return None

        return DeviceLimits.from_dict(
            {
                "blade_height": {"min": config["blade_height_min"], "max": config["blade_height_max"]},
                "working_speed": {"min": config["working_speed_min"], "max": config["working_speed_max"]},
                "path_spacing": {"min": config["path_spacing_min"], "max": config["path_spacing_max"]},
                "work_area_num_max": config["work_area_num_max"],
                "display_image_type": config["display_image_type"],
            }
        )

    @staticmethod
    def get_best_default(product_key: str) -> DeviceLimits:
        """Basic fallback if device is offline."""

        if DeviceType.contain_luba_product_key(product_key):
            return DeviceLimits.from_dict(default_luba_config)
        if DeviceType.contain_luba_2_product_key(product_key):
            return DeviceLimits.from_dict(default_luba_config)

        return DeviceLimits.from_dict(default_yuka_config)


# # Usage example:
# def main():
#     device_config = DeviceConfig()
#
#     # Look up a specific device
#     model_code = "HM010060LBAWD10"
#
#     # Get full configuration
#     config = device_config.get_device_config(model_code)
#     print(f"Full configuration for {model_code}:")
#     print(config)
#
#     # Get external model name
#     ext_model = device_config.get_external_model(model_code)
#     print(f"\nExternal model name: {ext_model}")
#
#     # Get working parameters
#     params = device_config.get_working_parameters(model_code)
#     print(f"\nWorking parameters:")
#     print(params)
