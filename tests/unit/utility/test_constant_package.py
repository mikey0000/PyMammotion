"""The ``utility/constant`` package boundary and its compatibility surface.

``device_constant`` used to hold five unrelated concerns; they now live in
siblings and it survives as a re-export surface, because the Home Assistant
integration imports several of these names from that exact path.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from pymammotion.utility.constant import device_constant

# Names the Home Assistant integration imports from
# ``pymammotion.utility.constant.device_constant`` (custom_components/mammotion/
# sensor.py and lawn_mower.py).  Removing one is a downstream break.
HA_DEVICE_CONSTANT_IMPORTS = [
    "AppConnectType",
    "PosType",
    "RTKPositionMode",
    "WorkMode",
    "camera_brightness",
    "device_connection",
    "device_mode",
]

# Names it imports from the ``pymammotion.utility.constant`` barrel.
HA_BARREL_IMPORTS = ["MOWING_ACTIVE_MODES", "VioState", "WorkMode"]


@pytest.mark.parametrize("name", HA_DEVICE_CONSTANT_IMPORTS)
def test_device_constant_still_exports_what_ha_imports(name: str) -> None:
    assert hasattr(device_constant, name)


@pytest.mark.parametrize("name", HA_BARREL_IMPORTS)
def test_barrel_still_exports_what_ha_imports(name: str) -> None:
    from pymammotion.utility import constant

    assert hasattr(constant, name)


def test_shim_and_barrel_hand_back_the_same_objects() -> None:
    """Two import paths for one name must not become two objects."""
    from pymammotion.utility import constant

    for name in HA_BARREL_IMPORTS:
        assert getattr(constant, name) is getattr(device_constant, name)


def test_constant_package_depends_on_nothing_above_it() -> None:
    """``utility/`` is the bottom layer, so this package must not import upward.

    A type-only import of ``data.model.report_info.ConnectData`` for
    ``device_connection``'s signature was the sole reason it did; the helper now
    takes a structural Protocol instead.
    """
    package = pathlib.Path(device_constant.__file__).parent
    offenders: list[str] = []
    for module in sorted(package.glob("*.py")):
        tree = ast.parse(module.read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            for name in names:
                if name.startswith("pymammotion.") and not name.startswith("pymammotion.utility"):
                    offenders.append(f"{module.name}: {name}")
    assert not offenders, f"utility/constant must not import upward: {offenders}"


def test_connect_data_satisfies_the_connection_protocol() -> None:
    """The Protocol replaced a concrete import, so the real dataclass must still fit."""
    from pymammotion.data.model.report_info import ConnectData
    from pymammotion.utility.constant.display import device_connection

    connect = ConnectData()
    connect.wifi_rssi = -50
    connect.ble_rssi = -60
    assert device_connection(connect) == "WIFI/BLE"
