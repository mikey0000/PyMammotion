from pymammotion.data.model.device_limits import DeviceLimits


class DeviceConfig:
    def __init__(self) -> None:
        # Dictionary to store all device configurations

        # Device mode configurations
        self.default_list = {
            "a1ZU6bdGjaM": {
                "extMod": "LubaAWD1000723",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.4,
                "work_area_num_max": 3,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 1,
            },
            "a1nf9kRBWoH": {
                "extMod": "LubaAWD3000723",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.4,
                "work_area_num_max": 6,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 1,
            },
            "a1ae1QnXZGf": {
                "extMod": "LubaAWD1000743",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.4,
                "work_area_num_max": 3,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 1,
            },
            "a1K4Ki2L5rK": {
                "extMod": "LubaAWD5000723",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "a1jOhAYOIG8": {
                "extMod": "LubaAWD5000743LS",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "a1BmXWlsdbA": {
                "extMod": "LubaAWD5000743",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "a1JFpmAV5Ur": {
                "extMod": "Kumar-10",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "a1kweSOPylG": {
                "extMod": "LubaAWD3000723",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 6,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 1,
            },
            "a1pvCnb3PPu": {
                "extMod": "LubaAWD1000743",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 3,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 1,
            },
            "a1x0zHD3Xop": {
                "extMod": "LubaAWD5000743LS",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "a1UBFdq6nNz": {
                "extMod": "LubaAWD5000723",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "a1FbaU4Bqk5": {
                "extMod": "LubaAWD5000743",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
        }

        self.inner_list = {
            "HM010060LBAWD10": {
                "extMod": "LubaAWD1000",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 3,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 1,
            },
            "HM030080LBAWD30": {
                "extMod": "LubaAWD3000",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 6,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 1,
            },
            "HM050080LBAWD50": {
                "extMod": "LubaAWD5000",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "HM030060LBAWD50OMNI": {
                "extMod": "LubaAWD5000",
                "cutter_height_min": 30,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 1,
            },
            "HM060100LBAWD50OMNIH": {
                "extMod": "LubaAWD5000H",
                "cutter_height_min": 60,
                "cutter_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "HM030070LBVAWD10OMNI": {
                "extMod": "Luba2AWD1000",
                "cutter_height_min": 25,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "HM060100LBVAWD10OMNIH": {
                "extMod": "Luba2AWD1000H",
                "cutter_height_min": 55,
                "cutter_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 10,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "HM030070LBVAWD30OMNI": {
                "extMod": "Luba2AWD3000",
                "cutter_height_min": 25,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 20,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "HM060100LBVAWD30OMNIH": {
                "extMod": "Luba2AWD3000H",
                "cutter_height_min": 55,
                "cutter_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 20,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "HM030070LBVAWD50OMNI": {
                "extMod": "Luba2AWD5000",
                "cutter_height_min": 25,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 30,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "HM060100LBVAWD50OMNIH": {
                "extMod": "Luba2AWD5000H",
                "cutter_height_min": 55,
                "cutter_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 30,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "HM030070LBVAWD100OMNI": {
                "extMod": "Luba2AWD10000",
                "cutter_height_min": 25,
                "cutter_height_max": 70,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
            },
            "HM060100LBVAWD100OMNIH": {
                "extMod": "Luba2AWD10000H",
                "cutter_height_min": 55,
                "cutter_height_max": 100,
                "working_speed_min": 0.2,
                "working_speed_max": 0.6,
                "work_area_num_max": 60,
                "working_path_min": 20,
                "working_path_max": 35,
                "display_imge_type": 0,
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

    def get_working_parameters(self, int_mod_or_key: str) -> DeviceLimits:
        """Get working parameters for given internal model code

        Args:
            int_mod (str): Internal model code

        Returns:
            dict: Working parameters or None if not found

        """
        config = self.get_device_config(int_mod_or_key)
        if not config:
            return None

        return DeviceLimits.from_dict(
            {
                "cutter_height": {"min": config["cutter_height_min"], "max": config["cutter_height_max"]},
                "working_speed": {"min": config["working_speed_min"], "max": config["working_speed_max"]},
                "working_path": {"min": config["working_path_min"], "max": config["working_path_max"]},
                "work_area_num_max": config["work_area_num_max"],
                "display_image_type": config["display_image_type"],
            }
        )


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
