"""Structural guards on the auth/credential module split out of client.py.

CLAUDE.md states these as prose; asserting them here means a future edit that
breaks one fails a test rather than only a review.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pymammotion.client_auth as client_auth
from pymammotion.client import MammotionClient
from pymammotion.client_auth import CloudAuthMixin

AUTH_SRC = pathlib.Path(client_auth.__file__)
CLIENT_SRC = pathlib.Path(inspect.getfile(MammotionClient))


def _calls_in(source: pathlib.Path, func_name: str) -> set[str]:
    tree = ast.parse(source.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == func_name:
            return {
                c.func.attr for c in ast.walk(node) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            }
    raise AssertionError(f"{func_name} not found in {source.name}")


def test_the_client_actually_mixes_the_auth_in() -> None:
    assert issubclass(MammotionClient, CloudAuthMixin)


def test_token_manager_is_constructed_in_exactly_one_place() -> None:
    """Two managers for one account means two schedulers rotating one refresh token."""
    sites = [
        f"{path.name}:{node.lineno}"
        for path in (AUTH_SRC, CLIENT_SRC)
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "TokenManager"
    ]
    assert len(sites) == 1, f"TokenManager constructed in {sites}"


def test_only_login_reaches_a_password_grant() -> None:
    """``login_v2`` is the library's only password grant; nothing else may reach it."""
    callers = [
        node.name
        for path in (AUTH_SRC, CLIENT_SRC)
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
        and any(
            isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "login_v2"
            for c in ast.walk(node)
        )
    ]
    assert callers == ["login_and_initiate_cloud"], f"login_v2 reachable from {callers}"


def test_both_public_entry_points_start_the_refresh_scheduler() -> None:
    """Renewal is clock-driven; an entry point that skips this lets credentials rot."""
    for entry in ("login_and_initiate_cloud", "restore_credentials"):
        assert "_start_token_refresh" in _calls_in(AUTH_SRC, entry), f"{entry} does not start the scheduler"


def test_auth_module_does_not_import_the_client() -> None:
    """The mixin is imported *by* client.py; importing back would be a cycle."""
    tree = ast.parse(AUTH_SRC.read_text())
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    } | {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert "pymammotion.client" not in imported
