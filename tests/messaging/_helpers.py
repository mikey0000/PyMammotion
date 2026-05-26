"""Shared helpers for saga + broker + queue tests.

Plain functions (not pytest fixtures) so call sites stay terse —
``_make_command_builder()`` rather than threading a fixture parameter through
every test.  Pytest fixtures live in ``conftest.py``; these helpers live here
so tests can call them directly without registering them as parameters.
"""
from __future__ import annotations

from unittest.mock import MagicMock


def make_command_builder() -> MagicMock:
    """MagicMock command-builder where every named method returns empty bytes.

    Saga tests instantiate sagas with a stub builder; the bytes value doesn't
    matter to saga logic, only that the methods exist and return something
    payload-shaped.  Explicit ``return_value = b""`` for the methods saga code
    paths actually invoke keeps the call-counting assertions
    (``cb.method.call_count``) clean.
    """
    cb = MagicMock()
    for name in (
        "get_area_name_list",
        "get_all_boundary_hash_list",
        "synchronize_hash_data",
        "get_regional_data",
        "get_hash_response",
        "generate_route_information",
        "get_line_info_list",
    ):
        getattr(cb, name).return_value = b""
    return cb
