"""Tests for the dev console's token-cache serialisation.

The console persists ``MammotionClient.to_cache()`` to JSON and restores it via
``restore_credentials()`` — the same round-trip HA performs against its config
entry.  These tests use the *nested generic* shapes that round-trip actually has
to survive, because a flat-model smoke test misses the interesting case entirely:
``Response`` is ``Generic[DataT]``, so ``Response.to_dict()`` leaves its ``data``
field as a live model, and a single-level conversion silently wrote that object's
``repr`` into the cache.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from pymammotion.http.model.http import (
    LoginResponseData,
    LoginResponseUserInformation,
    MQTTConnection,
    Response,
)
from pymammotion.http.model.response_factory import response_factory

_CONSOLE = Path(__file__).resolve().parents[3] / "examples" / "dev_console.py"


@pytest.fixture(scope="module")
def console() -> ModuleType:
    """Import examples/dev_console.py as a module (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("dev_console_under_test", _CONSOLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _login_response() -> Response:
    """A realistic ``mammotion_data`` entry — the nested-generic case."""
    return Response(
        code=0,
        msg="ok",
        data=LoginResponseData(
            access_token="access",
            token_type="Bearer",
            refresh_token="refresh",
            expires_in=2591999,
            authorization_code="authcode.eu",
            userInformation=LoginResponseUserInformation(
                areaCode="SWE",
                domainAbbreviation="SE",
                userId="896275795293503488",
                userAccount="64077101",
                authType="0",
                email="someone@example.com",
            ),
        ),
    )


def test_nested_generic_data_is_converted_to_a_dict(console: ModuleType) -> None:
    """Regression: ``Response.data`` used to survive as a live model."""
    result = console._jsonify_cache({"mammotion_data": _login_response()})
    assert isinstance(result["mammotion_data"], dict)
    assert isinstance(result["mammotion_data"]["data"], dict), "nested model was not converted"
    assert result["mammotion_data"]["data"]["access_token"] == "access"


def test_deeply_nested_models_are_converted(console: ModuleType) -> None:
    """userInformation sits two levels down and must be a dict too."""
    result = console._jsonify_cache({"mammotion_data": _login_response()})
    user = result["mammotion_data"]["data"]["userInformation"]
    assert isinstance(user, dict)
    assert user["areaCode"] == "SWE"


def test_the_whole_cache_is_json_serialisable_without_a_str_fallback(console: ModuleType) -> None:
    """The real failure mode: ``json.dumps(..., default=str)`` hid the miss.

    Dumping *without* a fallback is the assertion — any model the converter failed
    to reach raises here instead of being written as its repr and only blowing up
    later, on restore.
    """
    cache = {
        "mammotion_data": _login_response(),
        "mammotion_mqtt": MQTTConnection(host="tcp://h:1883", jwt="j", client_id="c", username="u"),
    }
    blob = json.dumps(console._jsonify_cache(cache), indent=2)  # no default=str
    assert "LoginResponseData(" not in blob, "a model leaked into the cache as its repr"


def test_round_trip_reconstructs_a_usable_response(console: ModuleType) -> None:
    """End to end: what we write must be what restore_credentials can parse.

    This is the exact path that raised
    ``InvalidFieldValue: Field "data" of type Optional[LoginResponseData]``.
    """
    blob = json.dumps(console._jsonify_cache({"mammotion_data": _login_response()}))
    restored = response_factory(Response[LoginResponseData], json.loads(blob)["mammotion_data"])

    assert restored.data is not None
    assert restored.data.access_token == "access"
    assert restored.data.refresh_token == "refresh"
    assert restored.data.userInformation.areaCode == "SWE"


def test_lists_of_models_are_converted(console: ModuleType) -> None:
    """``to_cache()`` also carries ``mammotion_device_list`` as a list of models."""
    result = console._jsonify_cache(
        {"devices": [MQTTConnection(host="h", jwt="j", client_id="c", username="u")]}
    )
    assert isinstance(result["devices"][0], dict)
    assert result["devices"][0]["jwt"] == "j"


def test_plain_values_pass_through(console: ModuleType) -> None:
    result = console._jsonify_cache({"already": {"a": 1}, "n": 3, "s": "x", "none": None})
    assert result == {"already": {"a": 1}, "n": 3, "s": "x", "none": None}
