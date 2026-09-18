"""The OSM tile fetcher's identity and the compatibility shim.

``pymammotion`` does not know what is embedding it, so the tile User-Agent must not
name a particular host (CLAUDE.md: "pymammotion doesn't know HA exists") — while
OSM's tile usage policy still requires a User-Agent that identifies the application.
"""

from __future__ import annotations

import pytest

from pymammotion.render import map_renderer


@pytest.fixture(autouse=True)
def _restore_user_agent() -> None:
    """The UA is module-level config; put it back so test order can't matter."""
    original = map_renderer.OSM_USER_AGENT
    yield
    map_renderer.OSM_USER_AGENT = original


def test_default_user_agent_names_the_library_not_a_host() -> None:
    assert map_renderer.OSM_USER_AGENT.startswith("pymammotion/")
    assert "HomeAssistant" not in map_renderer.OSM_USER_AGENT


def test_default_user_agent_carries_a_real_version() -> None:
    """Sourced from installed metadata, because ``__version__`` is stale (0.0.5)."""
    assert "/unknown" not in map_renderer.OSM_USER_AGENT
    assert "/0.0.5" not in map_renderer.OSM_USER_AGENT


def test_default_user_agent_satisfies_the_osm_policy_shape() -> None:
    """OSM wants an identifiable app plus a contact route."""
    assert "+https://" in map_renderer.OSM_USER_AGENT


def test_a_host_can_identify_itself() -> None:
    map_renderer.set_osm_user_agent("HomeAssistant-Mammotion-Map/1.0")
    assert map_renderer.OSM_USER_AGENT == "HomeAssistant-Mammotion-Map/1.0"


def test_the_old_import_path_still_works() -> None:
    """A 450-line PIL renderer is not a leaf helper, but out-of-tree callers import it."""
    from pymammotion.utility import map_renderer as shim

    for name in shim.__all__:
        assert hasattr(shim, name)
    assert shim.render_map_png is map_renderer.render_map_png
