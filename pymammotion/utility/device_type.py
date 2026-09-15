"""Device type definitions and product key mappings for Mammotion robot mowers."""

from collections.abc import Callable
from enum import Enum

LubaProductKey = [
    "a1UBFdq6nNz",
    "a1x0zHD3Xop",
    "a1pvCnb3PPu",
    "a1kweSOPylG",
    "a1JFpmAV5Ur",
    "a1BmXWlsdbA",
    "a1jOhAYOIG8",
    "a1K4Ki2L5rK",
    "a1ae1QnXZGf",
    "a1nf9kRBWoH",
    "a1ZU6bdGjaM",
    # LubaAWD5000743.  Absent from the APK's ``DeviceProductKey.LubaProductKey`` but
    # present in its Aliyun device-configuration form, and already carried by
    # ``device_capabilities._DEFAULT_LIST`` — without it here the key falls through to
    # the Mammotion-IoT default and an Aliyun Luba 1 is pointed at the wrong broker.
    "a1FbaU4Bqk5",
    # The newer-generation key for the whole Luba 1 line: the cloud publishes it with
    # LubaAWD1000/3000/5000/5000H under one key rather than one key per model.
    "b9tzVWaMxDZ",
]

LubaVProductKey = ["a1iMygIwxFC", "a1LLmy1zc0j", "6kWUnPW8UrW"]

LubaVProProductKey = ["a1mb8v6tnAa", "a1pHsTqyoPR", "ATyVu9QkAdX"]

Luba2MiniProductKey = ["a1L5ZfJIxGl", "a1dCWYFLROK", "ftDnXns2cdT"]

YukaProductKey = ["a1kT0TlYEza", "a1IQV0BrnXb", "KJHXKHMEvj3"]

YukaPlusProductKey = ["a1lNESu9VST", "a1zAEzmvWDa", "UfsEwwHp8uz"]

YukaMiniProductKey = ["a1BqmEWMRbX", "a1biqVGvxrE", "8xMGQS6DESC"]

#: ``a1vIxwrmpMn``/``HwHcWDDVkT9`` are the SolarRtkV2 pair — published by the cloud but
#: absent from the APK's own tables, so they are classed here by their model name.
RTKProductKey = [
    "a1qXkZ5P39W",
    "a1Nc68bGZzX",
    "mUzerUySdcC",
    "a1wIIUUdAMX",
    "sePx2YW6xDT",
    "a1mGLcddn4u",
    "a1vIxwrmpMn",
    "HwHcWDDVkT9",
]

YukaMVProductKey = ["a1jFe8HzcDb", "a16cz0iXgUJ", "USpE46bNTC7", "pdA6uJrBfjz"]

LubaLDProductKey = ["a1jDMfG2Fgj", "a1vtZq9LUFS", "FpstPz2SpwH"]

LubaVAProductKey = ["a1Ce85210Be", "a1BBOJnnjb9", "uY54W5rM8YH"]

YukaMLProductKey = ["a1OWGO8WXbh", "a1s6znKxGvI", "5BMtap5Q3Yq"]

LubaMDProductKey = ["a1T6VTFTc0C", "a14iRDqMepW"]

LubaMBProductKey = ["a1pb9toor70", "3drMFnqGVNe"]

LubaMEProductKey = ["HK8snDC8Kxh"]

RTKNBProductKey = ["a1NfZqdSREf", "a1ZuQVL7UiN", "6DPytKe4pKz"]

LubaLAProductKey = ["CDYuKXTYrSP"]

YukaMN100ProductKey = ["NnbeYtaEUGE"]

Cm900ProductKey = ["zkRuTK9KsXG", "6DbgVh2Qs5m"]

# Observed on a Spino-E1 (PC100).  The app carries no product key for it — its
# ``DeviceProductKey`` table stops at the PC210 pair below and the E1 is resolved
# by name alone — so this one comes from a live device, not the APK.
SwimmingPoolE1ProductKey = ["a15Cq8FbCh1"]

# APK ``SwimmingPoolOtaCorrelation.SWIMMING_POOL_PRODUCT_KEY``, the only other pool
# product key the app names.  It carries no model, so it lands on the generic Spino
# rather than a variant — enough to classify the device as a pool cleaner, which is
# what every gate actually asks.  Re-point it if a device turns up naming its variant.
SwimmingPoolProductKey = ["a1UvLZ3mWcW"]

# APK ``DeviceProductKey.PC210ProductKey`` — the PC210 pool cleaner (Spino-SP).
SwimmingPoolSPProductKey = ["FCtXbVnmd2C", "YBRDhT2YTvY"]

# APK ``DeviceProductKey.PC210PileProductKey`` — the PC210's charging pile, which
# ``DeviceType.valueOfStrByProductKey`` resolves to SD_PX, part of the pool family.
SdPxProductKey = ["GJzsmaVk5za", "fEaKVY28tNz"]

# Exhaustive list of all known Aliyun-platform product keys.
# Any product key NOT in this list is assumed to be a Mammotion-IoT device.
# This "closed Aliyun / open Mammotion-IoT" policy means new device types are
# handled correctly without a library update.
AliyunProductKey = [
    *LubaProductKey,
    *LubaVProductKey,
    *LubaVProProductKey,
    *Luba2MiniProductKey,
    *YukaProductKey,
    *YukaPlusProductKey,
    *YukaMiniProductKey,
    *RTKProductKey,
    "a1jFe8HzcDb",  # YukaMV (Aliyun variant — USpE46bNTC7 / pdA6uJrBfjz are Mammotion IoT)
    "a16cz0iXgUJ",  # YukaMV (Aliyun variant)
    *LubaLDProductKey,
    *LubaVAProductKey,
    *YukaMLProductKey,
    *LubaMDProductKey,
    *LubaMBProductKey,
    *RTKNBProductKey,
]


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse a dotted firmware version (e.g. ``1.12.0.466``) into an int tuple.

    Stops at the first non-numeric segment, so trailing content like a git hash
    in ``5.1.2.1540 (dc75bb0b)`` is ignored.
    """
    parts: list[int] = []
    for segment in version.strip().split("."):
        digits = ""
        for char in segment:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _version_less_than(version: str, target: str) -> bool:
    """Return True if dotted ``version`` is strictly older than dotted ``target``."""
    current = _version_tuple(version)
    threshold = _version_tuple(target)
    length = max(len(current), len(threshold))
    current += (0,) * (length - len(current))
    threshold += (0,) * (length - len(threshold))
    return current < threshold


def _version_greater_than(version: str, target: str) -> bool:
    """Return True if dotted ``version`` is strictly newer than dotted ``target``."""
    return _version_less_than(version=target, target=version)


#: Firmware above which the app shows the Smart Sleep screen (EcoSleep /
#: LiveSleep).  See ``DeviceType.supports_smart_sleep``.
_SMART_SLEEP_FIRMWARE = "2.3.26.0"

#: Firmware from which the app opens the Battery management page (charge limit,
#: off-peak charging).  See ``DeviceType.supports_charge_limit``.
_CHARGE_LIMIT_FIRMWARE = "2.1.1.5"

#: Firmware (major.minor) from which the app offers Wildlife Safety (animal
#: protection).  See ``DeviceType.supports_wildlife_safety``.
_WILDLIFE_SAFETY_FIRMWARE = "1.13"

#: Firmware above which the app replaces the on/off rain switch with the three-mode
#: Rain Protection screen.  Unconfirmed — borrowed from ``_SMART_SLEEP_FIRMWARE``.
#: Kept separate from it, with its own device tuple below, so confirming or
#: correcting one capability cannot silently move the other.
_RAIN_PROTECTION_MODES_FIRMWARE = "2.3.26.0"

#: Firmware from which the app shows "Auto-reverse Mowing Direction".  Verbatim from
#: the 2.3.18.21 RN bundle: ``compareVersion(device.firmwareVersion, "2.3.28.1") >= 0``.
#: See ``DeviceType.supports_auto_change_direction``.
_AUTO_CHANGE_DIRECTION_FIRMWARE = "2.3.28.1"


class DeviceType(Enum):
    """Enum of all supported Mammotion device types with their numeric ID, name prefix, and model string."""

    UNKNOWN = (-1, "UNKNOWN", "Unknown")
    RTK = (0, "RTK", "RTK")
    LUBA = (1, "Luba", "Luba 1")
    LUBA_2 = (2, "Luba-VS", "Luba 2")
    LUBA_YUKA = (3, "Yuka-", "Yuka")
    YUKA_MINI = (4, "Yuka-MN", "Yuka Mini")
    YUKA_MINI2 = (5, "Yuka-YM", "Yuka Mini 2")
    LUBA_VP = (6, "Luba-VP", "Luba VP")
    LUBA_MN = (7, "Luba-MN", "HM430")
    YUKA_VP = (8, "Yuka-VP", "MN241")
    SPINO = (9, "Spino", "Spino")
    RTK3A1 = (10, "RBSA1", "RBS03A1")
    LUBA_LD = (11, "Luba-LD", "HM431")
    RTK3A0 = (12, "RBSA0", "RBS03A0")
    RTK3A2 = (13, "RBSA2", "RBS03A2")
    YUKA_MINIV = (14, "Yuka-MV", "MN231")
    LUBA_VA = (15, "Luba-VA", "HM442")
    YUKA_ML = (16, "Yuka-ML", "MN232")
    LUBA_MD = (17, "Luba-MD", "HM433")
    LUBA_LA = (18, "Luba-LA", "HM432")
    SWIMMINGPOOL_S1 = (19, "Spino-S1", "Spino-S1")
    SWIMMINGPOOL_E1 = (20, "Spino-E1", "Spino-E1")
    YUKA_MN100 = (21, "Ezy-VT", "MN100")
    RTKNB = (22, "NB", "NB")
    LUBA_MB = (23, "Luba-MB", "HM434")
    CM900 = (24, "Kumar-MK", "KM01")
    YUKA_MN101 = (25, "Ezy-LD", "MN101")
    SWIMMINGPOOL_SP = (26, "Spino-SP,Spino-S1", "Spino-SP")
    SD_PX = (27, "SDPX", "SDPX")
    LUBA_HM = (28, "Luba-HM", "HM610")
    LUBA_ME = (29, "Luba-ME", "HM620")

    def __init__(self, value: int, name: str, model: str) -> None:
        """Initialize device type with its integer id, short name, and model string."""
        self._value = value
        self._name = name
        self._model = model

    def get_name(self) -> str:
        """Return the short device-name prefix string (e.g. 'Luba-VS') for this device type."""
        return self._name

    def get_model(self) -> str:
        """Return the human-readable model name (e.g. 'Luba 2') for this device type."""
        return self._model

    def get_value(self) -> int:
        """Return the integer identifier for this device type."""
        return self._value

    def get_value_str(self) -> str:
        """Return the integer identifier for this device type as a string."""
        return str(self._value)

    def set_value(self, value: int) -> None:
        """Override the integer identifier for this device type."""
        self._value = value

    # ------------------------------------------------------------------
    # Instance query methods (mirror the Java instance methods)
    # ------------------------------------------------------------------

    def is_luba2(self) -> bool:
        """Return True if this is a Luba 2 (Luba-VS)."""
        return self == DeviceType.LUBA_2

    def is_luba2_pro(self) -> bool:
        """Return True if this is a Luba 2 Pro (Luba-VP / HM441)."""
        return self == DeviceType.LUBA_VP

    def is_luba_hm(self) -> bool:
        """Return True if this is a Luba HM (HM610)."""
        return self == DeviceType.LUBA_HM

    def is_luba_me(self) -> bool:
        """Return True if this is a Luba ME (HM620)."""
        return self == DeviceType.LUBA_ME

    def is_luba_la(self) -> bool:
        """Return True if this is a Luba LA (HM432)."""
        return self == DeviceType.LUBA_LA

    def is_luba_ld(self) -> bool:
        """Return True if this is a Luba LD (HM431)."""
        return self == DeviceType.LUBA_LD

    def is_luba_mb(self) -> bool:
        """Return True if this is a Luba MB (HM434)."""
        return self == DeviceType.LUBA_MB

    def is_luba_md(self) -> bool:
        """Return True if this is a Luba MD (HM433)."""
        return self == DeviceType.LUBA_MD

    def is_luba_mn(self) -> bool:
        """Return True if this is a Luba MN (HM430)."""
        return self == DeviceType.LUBA_MN

    def is_luba_va(self) -> bool:
        """Return True if this is a Luba VA (HM442)."""
        return self == DeviceType.LUBA_VA

    def is_luba(self) -> bool:
        """Return True if this is a mini/pro Luba variant (VP, MN, or LD)."""
        return self in (DeviceType.LUBA_VP, DeviceType.LUBA_MN, DeviceType.LUBA_LD)

    def is_luba_type(self) -> bool:
        """Return True if this is any Luba family device (all generations, including CM900)."""
        return self in (
            DeviceType.LUBA,
            DeviceType.LUBA_2,
            DeviceType.LUBA_VP,
            DeviceType.LUBA_MN,
            DeviceType.LUBA_LD,
            DeviceType.LUBA_VA,
            DeviceType.LUBA_HM,
            DeviceType.LUBA_ME,
            DeviceType.LUBA_MB,
            DeviceType.LUBA_LA,
            DeviceType.CM900,
        )

    def is_cm900(self) -> bool:
        """Return True if this is a CM900 (Kumar-MK / KM01)."""
        return self == DeviceType.CM900

    def is_support_dynamics_line(self, firmware_version: str | None = None) -> bool:
        """Return True if this device supports the dynamics-line (live mow-progress) stream.

        Mirrors ``DeviceType.isSupportDynamicsLine(ICarDevice)`` in APK 2.3.8.201
        (`DeviceType.java:606-607`).  Supporting devices stream the actual cut
        path as a separate ``NavGetCommData(action=8, type=18)`` response that
        the APK polls every 10 s while the device is mowing.

        LUBA_VA qualifies only when the main-controller firmware is at least
        ``1.15.3.4422`` — pass ``firmware_version`` to enable that case
        (typically ``mower_device.device_firmwares.main_controller``).  When
        ``firmware_version`` is omitted, LUBA_VA is treated as unsupported
        (conservative — matches the APK's behaviour for missing/older firmware).

        Args:
            firmware_version: Optional main-controller firmware version string
                (e.g. ``"1.15.4.0"``).  Only consulted for LUBA_VA.

        """
        if self in (
            DeviceType.YUKA_MINIV,
            DeviceType.YUKA_MN100,
            DeviceType.YUKA_ML,
            DeviceType.LUBA_HM,
            DeviceType.LUBA_ME,
            DeviceType.LUBA_LA,
            DeviceType.LUBA_MB,
            DeviceType.CM900,
        ):
            return True
        if self is DeviceType.LUBA_VA and firmware_version:
            return not _version_less_than(firmware_version, "1.15.3.4422")
        return False

    def is_rtk_type(self) -> bool:
        """Return True if this is any RTK device (instance version of is_rtk)."""
        return self in (
            DeviceType.RTK,
            DeviceType.RTK3A0,
            DeviceType.RTK3A1,
            DeviceType.RTK3A2,
            DeviceType.RTKNB,
        )

    def is_rtk2(self) -> bool:
        """Return True if this is an RTK3A2."""
        return self == DeviceType.RTK3A2

    def is_rtk3(self) -> bool:
        """Return True if this is a generation-3 RTK (RTK3A0, RTK3A1, RTK3A2, or RTKNB)."""
        return self in (DeviceType.RTK3A0, DeviceType.RTK3A1, DeviceType.RTK3A2, DeviceType.RTKNB)

    def is_rtk3a1(self) -> bool:
        """Return True if this is an RTK3A1."""
        return self == DeviceType.RTK3A1

    def is_rtk_nb(self) -> bool:
        """Return True if this is an RTK NB."""
        return self == DeviceType.RTKNB

    def is_yu_ka(self) -> bool:
        """Return True if this is the original Yuka (LUBA_YUKA)."""
        return self == DeviceType.LUBA_YUKA

    def is_yu_ka_mini(self) -> bool:
        """Return True if this is a Yuka Mini or Yuka Mini 2."""
        return self in (DeviceType.YUKA_MINI, DeviceType.YUKA_MINI2)

    def is_yu_ka_pro(self) -> bool:
        """Return True if this is a Yuka VP (MN241)."""
        return self == DeviceType.YUKA_VP

    def is_yuka_mv(self) -> bool:
        """Return True if this is a Yuka MV (YUKA_MINIV / MN231)."""
        return self == DeviceType.YUKA_MINIV

    def is_yuka_ml_type(self) -> bool:
        """Return True if this is a Yuka ML (MN232)."""
        return self == DeviceType.YUKA_ML

    def is_yuka_mn100(self) -> bool:
        """Return True if this is a Yuka MN100."""
        return self == DeviceType.YUKA_MN100

    def is_yuka_mn101(self) -> bool:
        """Return True if this is a Yuka MN101."""
        return self == DeviceType.YUKA_MN101

    def is_yu_ka_type(self) -> bool:
        """Return True if this is any Yuka-family device."""
        return self in (
            DeviceType.LUBA_YUKA,
            DeviceType.YUKA_MINI,
            DeviceType.YUKA_MINI2,
            DeviceType.YUKA_VP,
            DeviceType.YUKA_MINIV,
            DeviceType.YUKA_MN100,
            DeviceType.YUKA_MN101,
            DeviceType.YUKA_ML,
        )

    def is_yu_ka_type1(self) -> bool:
        """Return True if this is a Yuka type 1 variant (original + mini variants + ML + MN101)."""
        return self in (
            DeviceType.LUBA_YUKA,
            DeviceType.YUKA_MINI,
            DeviceType.YUKA_MINI2,
            DeviceType.YUKA_VP,
            DeviceType.YUKA_ML,
            DeviceType.YUKA_MN101,
        )

    @staticmethod
    def from_value(value: int) -> "DeviceType":
        """Return the DeviceType corresponding to the given value."""
        return _VALUE_TO_DEVICE_TYPE.get(value, DeviceType.UNKNOWN)

    @staticmethod
    def value_of_str(device_name: str, product_key: str = "") -> "DeviceType":
        """Determine the type of device based on the provided device name and product key.

        Args:
            device_name (str): The name of the device.
            product_key (str?): The product key associated with the device. Defaults to "".

        Returns:
            DeviceType: The type of device based on the provided information.

        """
        if not device_name and not product_key:
            return DeviceType.UNKNOWN

        try:
            for device_type, name_slice, product_key_match in _VALUE_OF_STR_RULES:
                # A rule may claim several name prefixes, comma-separated, exactly as the
                # APK's enum does for SWIMMINGPOOL_SP ("Spino-SP,Spino-S1").
                prefixes = device_type.get_name().split(",")
                if any(prefix in device_name[:name_slice] for prefix in prefixes) or (
                    product_key_match is not None and product_key_match(product_key)
                ):
                    return device_type
        except (AttributeError, TypeError, IndexError):
            return DeviceType.UNKNOWN
        else:
            return DeviceType.UNKNOWN

    @staticmethod
    def has_4g(device_name: str, product_key: str = "") -> bool:
        """Check if the device has 4G capability based on the device name and optional product key."""
        device_type = DeviceType.value_of_str(device_name, product_key)
        return device_type.get_value() >= DeviceType.LUBA_2.get_value()

    @staticmethod
    def is_luba1(device_name: str, product_key: str = "") -> bool:
        """Check if the given device is of type LUBA (original Luba 1)."""
        device_type = DeviceType.value_of_str(device_name, product_key)
        return device_type.get_value() == DeviceType.LUBA.get_value()

    @staticmethod
    def uses_new_obstacle_detection(device_name: str, firmware_version: str = "", product_key: str = "") -> bool:
        """Whether the device presents the new-style obstacle-detection options.

        Mirrors the app's ``isLuba2YukaNewFirmwareVersion``: Luba 2 and the
        original Yuka switched obstacle-detection options at firmware ``1.12.0``.
        Below that they use the old four-option touch UI; at/above it — or when
        the version is unknown (matching the app's ``versionCode == 0`` branch) —
        they use the new Off/Standard/Sensitive options. All other devices always
        use the new options.
        """
        device_type = DeviceType.value_of_str(device_name, product_key)
        if device_type in (DeviceType.LUBA_2, DeviceType.LUBA_YUKA):
            if not firmware_version:
                return True
            return not _version_less_than(firmware_version, "1.12.0")
        return True

    @staticmethod
    def supports_smart_sleep(device_name: str, firmware_version: str = "", product_key: str = "") -> bool:
        """Whether the device exposes the Smart Sleep switches (EcoSleep / LiveSleep).

        Mirrors the gate on the app's battery page, which only offers the Smart
        Sleep entry for the HM432/HM434/HM442 product keys above firmware
        ``2.3.26.0`` (RN bundle ``assets/index.android.bundle`` in APK
        2.3.18.21: ``[y.HM432, y.HM434, y.HM442].includes(productKey) &&
        compareVersion(firmwareVersion, "2.3.26.0") > 0``).

        The threshold is exclusive, matching the app's ``> 0`` comparison.  An
        empty ``firmware_version`` returns False — the switches write to device
        storage, so guessing capability from a missing version is the wrong risk
        to take.
        """
        if DeviceType.value_of_str(device_name, product_key) not in _SMART_SLEEP_DEVICES:
            return False
        return _version_greater_than(firmware_version, _SMART_SLEEP_FIRMWARE)

    @staticmethod
    def supports_charge_limit(device_name: str, firmware_version: str = "", product_key: str = "") -> bool:
        """Whether the device exposes the battery charge limit (``bms_ctrl_info_msg``).

        Mirrors the app's Battery management entry (``DeviceFragment.onListener``
        and ``HomeFragmentNew``, APK 2.3.8.201): the page is hidden for the pool
        robots and whenever ``DeviceVersionUtils.isLessThanInputVersion(dev,
        "2.1.1.5")`` holds.  That check also returns True for a firmware string
        without a dot, so an unknown version hides the setting here as well.
        """
        if DeviceType.is_swimming_pool(device_name, product_key):
            return False
        if "." not in firmware_version:
            return False
        return not _version_less_than(firmware_version, _CHARGE_LIMIT_FIRMWARE)

    @staticmethod
    def supports_wildlife_safety(device_name: str, firmware_version: str = "", product_key: str = "") -> bool:
        """Whether the device exposes the Wildlife Safety (animal protection) setting.

        Mirrors ``CarSettingDrawerFragment.setAnimalProtectVisible`` (APK 2.3.8.201):
        the row is hidden for Luba 1, the pool robots and the 231-family parameter
        set (``is231SimilarParameterSettings``: Yuka MV, Ezy VT, Luba MB), and for
        firmware whose major.minor is below 1.13 (``DeviceVersionUtils.isOldAnimalVersion``).
        A version without a dot — unknown — counts as supported, as in the app, so a
        mower whose firmware has not been read yet keeps the setting.
        """
        device_type = DeviceType.value_of_str(device_name, product_key)
        if (
            device_type == DeviceType.LUBA
            or DeviceType.is_swimming_pool(device_name, product_key)
            or device_type in _WILDLIFE_SAFETY_EXCLUDED_DEVICES
        ):
            return False
        if "." not in firmware_version:
            return True
        return not _version_less_than(firmware_version, _WILDLIFE_SAFETY_FIRMWARE)

    @staticmethod
    def supports_rain_protection_modes(device_name: str, firmware_version: str = "", product_key: str = "") -> bool:
        """Whether the device exposes three-mode Rain Protection instead of an on/off switch.

        Off / Smart / Sensor plus a resume delay, new in app 2.3.18.  **The
        threshold and device set here are unconfirmed**: the app's entry point for
        this screen lives in native code that is packed in the 2.3.18.21 APK, so
        the only thing recoverable was the screen itself (RN bundle
        ``ScreenName.RainProtection``).  Its threshold and device tuple are borrowed
        from ``supports_smart_sleep`` — the one gate of the same vintage that *is*
        readable — but held separately so correcting either leaves the other alone.

        Devices that return False use the plain rain switch
        (``allpowerfull_rw`` id 3), which every supported mower has.
        """
        if DeviceType.value_of_str(device_name, product_key) not in _RAIN_PROTECTION_MODE_DEVICES:
            return False
        return _version_greater_than(firmware_version, _RAIN_PROTECTION_MODES_FIRMWARE)

    @staticmethod
    def supports_auto_change_direction(device_name: str, firmware_version: str = "", product_key: str = "") -> bool:
        """Whether the device offers "Auto-reverse Mowing Direction" (anti-matting).

        The app gates the row on a server-supplied capability list
        (``isShowCurrentModule(MAWorkSettingDetailCodeAUTOChangeDirection, detailVos)``)
        *and* on ``compareVersion(firmwareVersion, "2.3.28.1") >= 0`` — 2.3.18.21 RN
        bundle, work-settings screen.  pymammotion has no equivalent of ``detailVos``,
        so the device half is taken from Mammotion's release notes instead
        (``_AUTO_CHANGE_DIRECTION_DEVICES``).

        A firmware string without a dot — unknown — returns False: the toggle writes a
        setting to the device, so an unread version is the wrong thing to guess on.
        """
        if DeviceType.value_of_str(device_name, product_key) not in _AUTO_CHANGE_DIRECTION_DEVICES:
            return False
        if "." not in firmware_version:
            return False
        return not _version_less_than(firmware_version, _AUTO_CHANGE_DIRECTION_FIRMWARE)

    @staticmethod
    def is_luba_pro(device_name: str, product_key: str = "") -> bool:
        """Check if the device type is LUBA 2 or higher (non-RTK, non-swimming-pool)."""
        device_type = DeviceType.value_of_str(device_name, product_key)
        return (
            device_type.get_value() >= DeviceType.LUBA_2.get_value()
            and not DeviceType.is_swimming_pool(device_name, product_key)
            and not DeviceType.is_rtk(device_name, product_key)
        )

    @staticmethod
    def is_yuka(device_name: str) -> bool:
        """Check if the given device name corresponds to any Yuka-family device type."""
        dt = DeviceType.value_of_str(device_name)
        return dt in (
            DeviceType.LUBA_YUKA,
            DeviceType.YUKA_VP,
            DeviceType.YUKA_MINI,
            DeviceType.YUKA_MINI2,
            DeviceType.YUKA_MINIV,
            DeviceType.YUKA_ML,
            DeviceType.YUKA_MN100,
            DeviceType.YUKA_MN101,
        )

    @staticmethod
    def is_yuka_mini(device_name: str) -> bool:
        """Return True if the device name identifies a Yuka Mini, Yuka Mini 2, or Yuka ML device."""
        dt = DeviceType.value_of_str(device_name)
        return dt in (DeviceType.YUKA_MINI, DeviceType.YUKA_MINI2, DeviceType.YUKA_ML)

    @staticmethod
    def is_support_fill_light(device_name: str) -> bool:
        """Return True if the device has a fill light (manual/night light settings).

        The APK's own gate for that settings row: ``isSupportFillLight()``, and the
        night-light row additionally hides for Yuka MV
        (``CarSettingDrawerFragment``: ``if (!isSupportFillLight() || isYukaMV()) hide``).
        Prefer this over :meth:`is_mini_or_x_series` for light features — it is a
        capability, and it covers eight device types that grouping misses.
        """
        dt = DeviceType.value_of_str(device_name)
        return dt in (
            DeviceType.YUKA_MINI,
            DeviceType.YUKA_MINI2,
            DeviceType.YUKA_ML,
            DeviceType.YUKA_MINIV,
            DeviceType.YUKA_MN100,
            DeviceType.YUKA_MN101,
            DeviceType.LUBA_MN,
            DeviceType.LUBA_VP,
            DeviceType.CM900,
            DeviceType.LUBA_VA,
            DeviceType.LUBA_HM,
            DeviceType.LUBA_ME,
            DeviceType.LUBA_LA,
            DeviceType.LUBA_MD,
            DeviceType.LUBA_MB,
            DeviceType.LUBA_LD,
        )

    @staticmethod
    def is_support_blade_speed(device_name: str) -> bool:
        """Return True if the device exposes a blade-speed / cutter mode.

        Mirrors the APK's ``isSupportBladeSpeed()``.  Prefer this over
        :meth:`is_mini_or_x_series` for the cutter-mode setting.
        """
        dt = DeviceType.value_of_str(device_name)
        return dt in (
            DeviceType.YUKA_MINI,
            DeviceType.YUKA_MINI2,
            DeviceType.YUKA_MINIV,
            DeviceType.YUKA_MN100,
            DeviceType.YUKA_MN101,
            DeviceType.YUKA_ML,
            DeviceType.YUKA_VP,
            DeviceType.LUBA_MN,
            DeviceType.LUBA_LD,
            DeviceType.LUBA_LA,
            DeviceType.LUBA_MD,
            DeviceType.LUBA_MB,
            DeviceType.LUBA_VA,
            DeviceType.LUBA_HM,
            DeviceType.LUBA_ME,
            DeviceType.CM900,
            DeviceType.LUBA_VP,
        )

    @staticmethod
    def is_mini_or_x_series(device_name: str) -> bool:
        """Return True if the device is part of the mini or X series."""
        dt = DeviceType.value_of_str(device_name)
        return dt in (
            DeviceType.YUKA_MINI,
            DeviceType.YUKA_MINI2,
            DeviceType.YUKA_MINIV,
            DeviceType.YUKA_ML,
            DeviceType.YUKA_VP,
            DeviceType.LUBA_MN,
            DeviceType.LUBA_VP,
            DeviceType.LUBA_LD,
            DeviceType.LUBA_LA,
            DeviceType.LUBA_MB,
            DeviceType.LUBA_MD,
        )

    @staticmethod
    def is_rtk(device_name: str, product_key: str = "") -> bool:
        """Check if the device type is within the range of RTK devices."""
        device_type = DeviceType.value_of_str(device_name, product_key)
        return device_type in (
            DeviceType.RTK,
            DeviceType.RTK3A0,
            DeviceType.RTK3A1,
            DeviceType.RTK3A2,
            DeviceType.RTKNB,
        )

    @staticmethod
    def is_swimming_pool(device_name: str, product_key: str = "") -> bool:
        """Return True if the device is a swimming-pool robot (Spino variants + SD_PX).

        *product_key* identifies the device when the name cannot — the pool models
        are sold under names the prefix table does not cover.
        """
        device_type = DeviceType.value_of_str(device_name, product_key)
        return device_type in (
            DeviceType.SPINO,
            DeviceType.SWIMMINGPOOL_S1,
            DeviceType.SWIMMINGPOOL_E1,
            DeviceType.SWIMMINGPOOL_SP,
            DeviceType.SD_PX,
        )

    @staticmethod
    def is_yuka_ml(device_name: str) -> bool:
        """Return True if the device name identifies a Yuka ML device."""
        return DeviceType.value_of_str(device_name) == DeviceType.YUKA_ML

    # ------------------------------------------------------------------
    # Product-key contain helpers
    # ------------------------------------------------------------------

    @staticmethod
    def contain_rtk_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to an RTK device."""
        return bool(product_key) and product_key in RTKProductKey

    @staticmethod
    def contain_luba_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to an original Luba 1 device."""
        return bool(product_key) and product_key in LubaProductKey

    @staticmethod
    def contain_luba_2_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Luba 2 (Luba-VS) device."""
        return bool(product_key) and product_key in LubaVProductKey

    @staticmethod
    def contain_luba_ld_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Luba LD device."""
        return bool(product_key) and product_key in LubaLDProductKey

    @staticmethod
    def contain_luba_va_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Luba VA device."""
        return bool(product_key) and product_key in LubaVAProductKey

    @staticmethod
    def contain_luba_la_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Luba LA device."""
        return bool(product_key) and product_key in LubaLAProductKey

    @staticmethod
    def contain_luba_md_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Luba MD device."""
        return bool(product_key) and product_key in LubaMDProductKey

    @staticmethod
    def contain_luba_mb_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Luba MB device."""
        return bool(product_key) and product_key in LubaMBProductKey

    @staticmethod
    def contain_luba_me_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Luba ME device (HM620)."""
        return bool(product_key) and product_key in LubaMEProductKey

    @staticmethod
    def contain_luba_v_pro_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Luba VP (Luba 2 Pro) device."""
        return bool(product_key) and product_key in LubaVProProductKey

    @staticmethod
    def contain_luba_2_mini_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Luba MN (Luba 2 Mini) device."""
        return bool(product_key) and product_key in Luba2MiniProductKey

    @staticmethod
    def contain_yuka_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to an original Yuka device."""
        return bool(product_key) and product_key in YukaProductKey

    @staticmethod
    def contain_yuka_plus_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Yuka Plus device."""
        return bool(product_key) and product_key in YukaPlusProductKey

    @staticmethod
    def contain_yuka_mini_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Yuka Mini device."""
        return bool(product_key) and product_key in YukaMiniProductKey

    @staticmethod
    def contain_yuka_vp_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Yuka VP device."""
        return bool(product_key) and product_key in YukaPlusProductKey

    @staticmethod
    def contain_yuka_mv_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Yuka MV (MINIV) device."""
        return bool(product_key) and product_key in YukaMVProductKey

    @staticmethod
    def contain_yuka_ml_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Yuka ML device."""
        return bool(product_key) and product_key in YukaMLProductKey

    @staticmethod
    def contain_yuka_mn100_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Yuka MN100 device."""
        return bool(product_key) and product_key in YukaMN100ProductKey

    @staticmethod
    def contain_rtk_nb_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to an RTK NB device."""
        return bool(product_key) and product_key in RTKNBProductKey

    @staticmethod
    def contain_cm900_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a CM900 device."""
        return bool(product_key) and product_key in Cm900ProductKey

    @staticmethod
    def contain_swimming_pool_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Spino pool cleaner of unnamed variant."""
        return bool(product_key) and product_key in SwimmingPoolProductKey

    @staticmethod
    def contain_swimming_pool_e1_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Spino-E1 (PC100) pool cleaner."""
        return bool(product_key) and product_key in SwimmingPoolE1ProductKey

    @staticmethod
    def contain_swimming_pool_sp_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Spino-SP (PC210) pool cleaner."""
        return bool(product_key) and product_key in SwimmingPoolSPProductKey

    @staticmethod
    def contain_sd_px_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a PC210 charging pile (SD_PX)."""
        return bool(product_key) and product_key in SdPxProductKey

    @staticmethod
    def is_aliyun_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a known Aliyun-platform device.

        Any product key NOT in the explicit Aliyun list is treated as a
        Mammotion-IoT device so that new device types work without a library update.
        """
        return bool(product_key) and product_key in AliyunProductKey

    @staticmethod
    def is_mammotion_iot_product_key(product_key: str) -> bool:
        """Return True if the product key belongs to a Mammotion-IoT (post-2025) device.

        Defaults to True for any unrecognised key — new devices are assumed to
        use the Mammotion MQTT broker until proven otherwise.
        """
        return not product_key or product_key not in AliyunProductKey

    def is_support_video(self) -> bool:
        """Return True if this device type supports video streaming (all models except the original Luba 1)."""
        return self != DeviceType.LUBA

    def supports_battery_cycle_count(self) -> bool:
        """Return True if the device has a built-in (non-removable) battery and reports cycle count.

        Mirrors APK ``DeviceType.isSupportBatteryLoopCount()``.  The 9 models
        below use removable/detachable battery packs and do not report a
        meaningful ``bat_cycles`` value.
        """
        return self not in (
            DeviceType.YUKA_MINI,
            DeviceType.YUKA_ML,
            DeviceType.LUBA_MN,
            DeviceType.YUKA_MINIV,
            DeviceType.YUKA_MN100,
            DeviceType.YUKA_MN101,
            DeviceType.LUBA_LD,
            DeviceType.LUBA_LA,
            DeviceType.LUBA_MB,
        )


# Devices the app offers the Smart Sleep screen on. The RN bundle names them by
# product key (HM432/HM434/HM442); expressed as device types here so a mower whose
# product key we don't know still matches on its name prefix.
_SMART_SLEEP_DEVICES = (
    DeviceType.LUBA_LA,
    DeviceType.LUBA_MB,
    DeviceType.LUBA_VA,
)

# The app's is231SimilarParameterSettings() set: these share the 231 parameter
# UI and never show Wildlife Safety regardless of firmware.
_WILDLIFE_SAFETY_EXCLUDED_DEVICES = (
    DeviceType.YUKA_MINIV,
    DeviceType.YUKA_MN100,
    DeviceType.LUBA_MB,
)

# Devices believed to offer three-mode Rain Protection. Unconfirmed, and separate
# from _SMART_SLEEP_DEVICES on purpose — see _RAIN_PROTECTION_MODES_FIRMWARE.
_RAIN_PROTECTION_MODE_DEVICES = (
    DeviceType.LUBA_LA,
    DeviceType.LUBA_MB,
    DeviceType.LUBA_VA,
)

# Devices Mammotion lists for "Auto-reverse Mowing Direction" (release notes of
# 2026-08-12): LUBA 3 AWD, LUBA mini 2 AWD 1000/1500 and YUKA mini 2 Vision/LiDAR.
# LUBA_LA (HM432) and LUBA_MB (HM434) are the two the app describes as interior-routes
# only — the app's own is434Or432Device() — but they still offer the toggle.
_AUTO_CHANGE_DIRECTION_DEVICES = (
    DeviceType.LUBA_VA,
    DeviceType.LUBA_LA,
    DeviceType.LUBA_MB,
    DeviceType.YUKA_MINIV,
    DeviceType.YUKA_ML,
)

# Numeric id -> DeviceType, used by DeviceType.from_value. Built straight from the
# enum members' ids (the first tuple element), so it stays 1:1 with the definitions
# above; any id not present (including UNKNOWN's -1) falls back to DeviceType.UNKNOWN.
_VALUE_TO_DEVICE_TYPE: dict[int, "DeviceType"] = {
    dt.get_value(): dt for dt in DeviceType if dt is not DeviceType.UNKNOWN
}

# Ordered (device_type, name-prefix slice length, optional product-key predicate)
# rules for DeviceType.value_of_str. Order is significant: it reproduces the original
# if-chain exactly, so specific "Luba-XX"/"Yuka-XX" prefixes are matched before the
# generic "Luba", and the product-key checks fire at the same positions they did in the
# chain. Most names are matched against device_name[:7]; RTK uses [:3] and the
# swimming-pool models use [:8].
_VALUE_OF_STR_RULES: tuple[tuple["DeviceType", int, Callable[[str], bool] | None], ...] = (
    (DeviceType.RTK, 3, DeviceType.contain_rtk_product_key),
    (DeviceType.LUBA_2, 7, DeviceType.contain_luba_2_product_key),
    (DeviceType.LUBA_LD, 7, None),
    (DeviceType.LUBA_VP, 7, None),
    (DeviceType.LUBA_MN, 7, None),
    (DeviceType.YUKA_VP, 7, None),
    (DeviceType.YUKA_MINI, 7, None),
    (DeviceType.YUKA_MINI2, 7, None),
    (DeviceType.RTK3A1, 7, None),
    (DeviceType.RTK3A0, 7, None),
    (DeviceType.RTK3A2, 7, None),
    (DeviceType.YUKA_MINIV, 7, None),
    (DeviceType.LUBA_VA, 7, None),
    (DeviceType.YUKA_ML, 7, None),
    (DeviceType.LUBA_MD, 7, None),
    (DeviceType.LUBA_LA, 7, None),
    (DeviceType.LUBA_YUKA, 7, None),
    # A ``Spino-S1`` *name* is a PC210, i.e. SWIMMINGPOOL_SP — the APK says so outright
    # (``DeviceType.java``: ``if (str.contains(SWIMMINGPOOL_S1.product_name)) return
    # SWIMMINGPOOL_SP;``) and its SP entry claims both prefixes, ``"Spino-SP,Spino-S1"``.
    # So SP is matched first and SWIMMINGPOOL_S1 (PC200) is now reachable only by its
    # own product key, which is the same position the APK leaves it in.
    (DeviceType.SWIMMINGPOOL_SP, 8, DeviceType.contain_swimming_pool_sp_product_key),
    (DeviceType.SWIMMINGPOOL_S1, 8, None),
    (DeviceType.SWIMMINGPOOL_E1, 8, DeviceType.contain_swimming_pool_e1_product_key),
    (DeviceType.SPINO, 7, DeviceType.contain_swimming_pool_product_key),
    (DeviceType.YUKA_MN100, 7, None),
    (DeviceType.YUKA_MN101, 7, None),
    (DeviceType.RTKNB, 7, None),
    (DeviceType.LUBA_MB, 7, None),
    (DeviceType.CM900, 7, None),
    (DeviceType.SD_PX, 7, DeviceType.contain_sd_px_product_key),
    (DeviceType.LUBA_HM, 7, None),
    (DeviceType.LUBA_ME, 7, DeviceType.contain_luba_me_product_key),
    (DeviceType.LUBA, 7, DeviceType.contain_luba_product_key),
)
