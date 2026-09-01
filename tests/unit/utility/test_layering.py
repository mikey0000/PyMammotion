"""Import-direction rules for ``utility/`` and the ``data/model`` geojson pair.

``utility/`` is the bottom layer.  Three modules that operate on ``data.model``
types moved out of it; the old paths survive as shims because the Home Assistant
integration imports from them, so those three files are the only upward imports
left and this test holds that line.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

PYMAMMOTION = pathlib.Path(__file__).parents[3] / "pymammotion"

# The only files under utility/ allowed to import a layer above it.  Each exists
# solely to keep a public import path working; deleting one needs a coordinated
# change to the integration's imports.
SHIMS = {"map.py", "svg.py", "device_config.py", "map_renderer.py"}

UPWARD = ("data", "device", "transport", "aliyun", "http", "messaging", "state", "bluetooth")


def _pymammotion_imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return {m for m in modules if m.startswith("pymammotion.")}


def test_only_the_shims_import_upward_from_utility() -> None:
    offenders: list[str] = []
    for module in sorted((PYMAMMOTION / "utility").rglob("*.py")):
        if module.name in SHIMS:
            continue
        for imported in _pymammotion_imports(module):
            tail = imported.removeprefix("pymammotion.").split(".")[0]
            if tail in UPWARD:
                offenders.append(f"{module.relative_to(PYMAMMOTION)} -> {imported}")
    assert not offenders, f"utility/ must not import upward: {offenders}"


@pytest.mark.parametrize("shim", sorted(SHIMS))
def test_shims_still_re_export_their_public_names(shim: str) -> None:
    """The integration imports from these paths; the names must resolve."""
    import importlib

    module = importlib.import_module(f"pymammotion.utility.{shim.removesuffix('.py')}")
    assert module.__all__, "a shim with nothing in __all__ has stopped doing its job"
    for name in module.__all__:
        assert hasattr(module, name), f"{shim} no longer exports {name}"


def test_the_model_does_not_import_its_geojson_generator() -> None:
    """``generate_geojson`` imports ``hash_list``, so the dependency runs one way.

    When it ran both ways, the four generator calls in ``hash_list`` each needed a
    function-body import to dodge the cycle.
    """
    hash_list = _pymammotion_imports(PYMAMMOTION / "data" / "model" / "hash_list.py")
    assert "pymammotion.data.model.generate_geojson" not in hash_list

    generator = _pymammotion_imports(PYMAMMOTION / "data" / "model" / "generate_geojson.py")
    assert "pymammotion.data.model.hash_list" in generator


def test_the_model_does_not_call_into_the_device_layer() -> None:
    """A dataclass reaching up into ``device/`` was the last upward edge here."""
    for module in sorted((PYMAMMOTION / "data").rglob("*.py")):
        upward = {m for m in _pymammotion_imports(module) if m.startswith("pymammotion.device.")}
        assert not upward, f"{module.relative_to(PYMAMMOTION)} imports {upward}"
