"""The mechanical half of ``docs/testing.md``, asserted against the suite itself.

Only rules a machine can decide live here; the judgement-shaped ones belong to
the ``test-reviewer`` agent.  Each rule carries a baseline of the files that
predate it so the suite is green today.  A baseline is a ratchet: exceeding an
entry fails, and so does *undershooting* one — an improvement must be recorded
by tightening or deleting the entry, otherwise the debt silently grows back.

The text-matching rules see string literals and comments too, which is why this
one module exempts itself from the scan: it necessarily spells out every
construct it bans.  Nothing else is exempt.
"""

from __future__ import annotations

import ast
import collections
import pathlib
import re
import tomllib

SELF = pathlib.Path(__file__).resolve()
TESTS = pathlib.Path(__file__).parents[1]
PYMAMMOTION = TESTS.parent / "pymammotion"
PYPROJECT = TESTS.parent / "pyproject.toml"

MAX_MODULE_LINES = 600

#: Files under ``tests/`` that are not valid Python.
UNPARSEABLE: frozenset[str] = frozenset()

#: The bare asyncio marker, redundant under ``asyncio_mode = "auto"``.
#: (The same marker *with* a ``loop_scope`` argument is not redundant and is not counted.)
BARE_ASYNCIO_MARKER: dict[str, int] = {}

#: Test modules over the size cap, at the length they had when the cap landed.
OVERSIZED = {
    "integration/test_credential_restore.py": 881,
    "integration/test_sagas.py": 977,
    "unit/auth/test_token_manager.py": 712,
    "unit/data/model/test_generate_geojson.py": 1201,
    "unit/data/model/test_hash_list.py": 790,
    "unit/device/test_handle.py": 1682,
    "unit/test_client.py": 2052,
    "unit/transport/test_aliyun_mqtt.py": 1153,
    "unit/transport/test_ble.py": 740,
}

#: Builders defined in more than one test module instead of the package ``_helpers.py``.
DUPLICATE_BUILDERS: dict[str, tuple[str, ...]] = {}

#: Test modules under ``unit/`` with no ``pymammotion`` module of the same name.
UNMIRRORED_UNIT_MODULES = frozenset(
    {
        "unit/auth/test_aliyun_token_consistency.py",
        "unit/auth/test_network_errors.py",
        "unit/auth/test_refresh_scheduler.py",
        "unit/device/test_debounced_bus.py",
        "unit/device/test_mqtt_properties.py",
        "unit/device/test_ota_progress.py",
        "unit/device/test_registry_keys.py",
        "unit/device/test_rtk_properties.py",
        "unit/device/test_send_raw_rate_limit.py",
        "unit/device/test_sleeping_poll.py",
        "unit/device/test_user_priority.py",
        "unit/examples/test_dev_console_cache.py",
        "unit/http/test_token_refresh.py",
        "unit/http/test_wake_up_device.py",
        "unit/messaging/test_ha_saga_skip.py",
        "unit/render/test_svg_center.py",
        "unit/render/test_svg_chunk.py",
        "unit/render/test_svg_routing.py",
        "unit/state/test_device_availability.py",
        "unit/test_review_invariants.py",
        "unit/transport/test_mammotion_mqtt.py",
        "unit/utility/test_constant_package.py",
        "unit/utility/test_layering.py",
        "unit/utility/test_sleep_rain_gates.py",
        "unit/utility/test_work_modes.py",
    }
)

#: Modules carrying a script entry point instead of leaving collection to pytest.
MODULE_RUNNERS: frozenset[str] = frozenset()

BUILDER_NAME = re.compile(r"_?make_[a-z0-9_]+")
SKIP_MARKS = ("pytest.mark.skip", "pytest.mark.skipif", "pytest.mark.xfail")
PYTEST_BUILTIN_MARKS = frozenset({"parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings", "asyncio"})


def _python_files() -> list[pathlib.Path]:
    """Every test module except this one — its own literals are the rules, not violations.

    Only this file is exempt.  Excluding the whole ``meta`` package would let any
    module added beside it opt out of the entire constitution silently.
    """
    return sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts and p.resolve() != SELF)


def _test_modules() -> list[pathlib.Path]:
    return [p for p in _python_files() if p.name.startswith("test_")]


def _rel(path: pathlib.Path) -> str:
    return path.relative_to(TESTS).as_posix()


def _parse(path: pathlib.Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


def _assert_ratchet(actual: dict[str, int], baseline: dict[str, int], rule: str, fix: str) -> None:
    """Fail on a new or worsened violation, and on an improvement left unrecorded."""
    problems: list[str] = []
    for name, count in sorted(actual.items()):
        allowed = baseline.get(name, 0)
        if count > allowed:
            problems.append(f"{name}: {count} (baseline {allowed}) — {fix}")
    for name, allowed in sorted(baseline.items()):
        count = actual.get(name, 0)
        if count < allowed:
            entry = f"set it to {count}" if count else "delete the entry"
            problems.append(f"{name}: down to {count} from {allowed} — {entry} in {rule}")
    assert not problems, f"{rule} (docs/testing.md):\n" + "\n".join(f"  {p}" for p in problems)


def test_every_test_directory_is_a_package() -> None:
    """Without ``__init__.py`` two directories cannot share a test-module basename."""
    missing = sorted(
        {
            _rel(directory)
            for module in _test_modules()
            for directory in module.parents
            if directory != TESTS and TESTS in directory.parents and not (directory / "__init__.py").exists()
        }
    )
    assert not missing, f"test directories missing __init__.py: {missing}"


def test_every_module_is_valid_python() -> None:
    unparseable = {_rel(p) for p in _python_files() if _parse(p) is None}
    assert unparseable == set(UNPARSEABLE), (
        f"unparseable modules under tests/: {sorted(unparseable)} (baseline {sorted(UNPARSEABLE)})"
    )


def test_every_module_has_a_docstring() -> None:
    """The docstring says what surface the module covers — section 3."""
    missing = [
        _rel(p)
        for p in _python_files()
        if p.name != "__init__.py" and (tree := _parse(p)) is not None and ast.get_docstring(tree) is None
    ]
    assert not missing, f"test modules without a docstring: {missing}"


def test_test_module_filenames_are_snake_case() -> None:
    bad = [_rel(p) for p in _test_modules() if not re.fullmatch(r"test_[a-z0-9_]+\.py", p.name)]
    assert not bad, f"test modules must be snake_case test_<subject>.py: {bad}"


def test_unit_test_modules_mirror_the_package() -> None:
    """``unit/<pkg>/test_<module>.py`` pairs with ``pymammotion/<pkg>/<module>.py`` — section 2.

    A concern split (``test_handle_transport_selection.py``) counts as mirrored
    because it is prefixed with the module it splits.
    """
    unmirrored: set[str] = set()
    for module in _test_modules():
        if module.parts[len(TESTS.parts)] != "unit":
            continue
        package = PYMAMMOTION.joinpath(*module.relative_to(TESTS / "unit").parts[:-1])
        stem = module.stem.removeprefix("test_")
        if package.is_dir() and any(
            source.stem == stem or stem.startswith(f"{source.stem}_") for source in package.glob("*.py")
        ):
            continue
        unmirrored.add(_rel(module))
    assert unmirrored == set(UNMIRRORED_UNIT_MODULES), (
        f"unit test modules with no matching source module: {sorted(unmirrored - UNMIRRORED_UNIT_MODULES)}; "
        f"baseline entries no longer violating: {sorted(UNMIRRORED_UNIT_MODULES - unmirrored)}"
    )


def test_no_bare_asyncio_marker() -> None:
    """``asyncio_mode = "auto"`` already applies it — section 6."""
    counts = {
        _rel(p): len(re.findall(r"pytest\.mark\.asyncio(?!\s*\()", p.read_text()))
        for p in _python_files()
        if re.search(r"pytest\.mark\.asyncio(?!\s*\()", p.read_text())
    }
    _assert_ratchet(counts, BARE_ASYNCIO_MARKER, "BARE_ASYNCIO_MARKER", "delete the decorator")


def test_nothing_calls_time_sleep() -> None:
    """A blocking sleep stalls the event loop and the whole suite — section 6."""
    offenders = [_rel(p) for p in _python_files() if re.search(r"\btime\.sleep\(", p.read_text())]
    assert not offenders, f"blocking sleep is banned in tests: {offenders}"


def test_nothing_sleeps_on_the_wall_clock() -> None:
    """A fixed sleep is a hope, not a synchronisation — section 6.

    ``wait_until`` is the replacement, and the two cases a sleep really is the right
    tool — holding a critical section open, and letting a production timer age — are
    ``let_others_run`` and ``advance_real_time`` in ``tests/_helpers.py``.  Those are
    the only definitions allowed to call it, which is what makes them greppable.
    ``tests/fakeserver`` is exempt: it is a running service, not a test.
    """
    offenders: list[str] = []
    for path in _python_files():
        if path.relative_to(TESTS).parts[0] == "fakeserver" or path.name == "_helpers.py":
            continue
        # Any callable whose name ends in ``sleep``: ``real_sleep = asyncio.sleep`` hid a
        # one-second poll from an ``asyncio.sleep``-only pattern.  An alias named
        # something else still evades this — deliberate evasion is not the threat here.
        for value in re.findall(r"\b\w*sleep\(\s*([0-9][0-9.]*)", path.read_text()):
            if float(value) > 0:
                offenders.append(f"{_rel(path)} — sleep({value})")
    assert not offenders, (
        "use wait_until / let_others_run / advance_real_time from tests/_helpers.py: " + str(offenders)
    )


def test_unit_tests_do_not_use_the_fake_server() -> None:
    """A test that needs the fake cloud is an integration test — section 1."""
    offenders = [
        _rel(p)
        for p in _python_files()
        if p.relative_to(TESTS).parts[0] == "unit" and "tests.fakeserver" in p.read_text()
    ]
    assert not offenders, f"unit tests importing tests.fakeserver belong in tests/integration/: {offenders}"


def test_no_module_runners() -> None:
    """Tests are run by pytest; a ``__main__`` block hides a second entry point — section 8."""
    runners = {
        _rel(p) for p in _test_modules() if re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', p.read_text())
    }
    assert runners == set(MODULE_RUNNERS), (
        f"new __main__ runners: {sorted(runners - MODULE_RUNNERS)}; "
        f"baseline entries no longer violating: {sorted(MODULE_RUNNERS - runners)}"
    )


def test_builders_are_not_duplicated_across_modules() -> None:
    """A builder a second module needs moves to the package ``_helpers.py`` — section 4."""
    where: dict[str, list[str]] = collections.defaultdict(list)
    for module in _test_modules():
        if (tree := _parse(module)) is None:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and BUILDER_NAME.fullmatch(node.name):
                where[node.name].append(_rel(module))
    duplicated = {name: tuple(sorted(paths)) for name, paths in where.items() if len(paths) > 1}
    grew = {
        name: sorted(set(paths) - set(DUPLICATE_BUILDERS.get(name, ())))
        for name, paths in duplicated.items()
        if set(paths) - set(DUPLICATE_BUILDERS.get(name, ()))
    }
    shrank = {
        name: sorted(set(baseline) - set(duplicated.get(name, ())))
        for name, baseline in DUPLICATE_BUILDERS.items()
        if set(baseline) - set(duplicated.get(name, ()))
    }
    assert not grew and not shrank, (
        f"builders duplicated into a new module (promote to _helpers.py): {grew}; "
        f"builders no longer duplicated in these modules — update DUPLICATE_BUILDERS: {shrank}"
    )


def test_only_registered_markers_are_used() -> None:
    registered = {
        marker.split(":")[0].strip()
        for marker in tomllib.loads(PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]["markers"]
    }
    used = set(re.findall(r"pytest\.mark\.(\w+)", "\n".join(p.read_text() for p in _python_files())))
    unknown = used - registered - PYTEST_BUILTIN_MARKS
    assert not unknown, f"markers used but not registered in pyproject.toml: {sorted(unknown)}"


def test_regression_tests_document_the_defect() -> None:
    """A regression test's docstring records what the code did wrong — section 7."""
    undocumented: list[str] = []
    for module in _test_modules():
        if (tree := _parse(module)) is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            marked = any(
                ast.unparse(decorator).startswith("pytest.mark.regression") for decorator in node.decorator_list
            )
            if marked and not ast.get_docstring(node):
                undocumented.append(f"{_rel(module)}::{node.name}")
    assert not undocumented, f"regression tests without a docstring naming the defect: {undocumented}"


def test_test_modules_stay_under_the_size_cap() -> None:
    """Past the cap, split by concern — ``test_<module>_<concern>.py``, section 2."""
    lengths = {
        _rel(p): len(p.read_text().splitlines())
        for p in _test_modules()
        if len(p.read_text().splitlines()) > MAX_MODULE_LINES
    }
    _assert_ratchet(lengths, OVERSIZED, "OVERSIZED", f"split by concern (cap {MAX_MODULE_LINES} lines)")


def _states_a_reason(decorator: ast.expr, text: str) -> bool:
    """Whether a skip/xfail decorator names its blocker.

    ``pytest.mark.skip`` reads a positional string as the reason; ``skipif`` and
    ``xfail`` take the condition there and read the reason from keywords only.
    """
    if not isinstance(decorator, ast.Call):
        return False
    if any(keyword.arg == "reason" for keyword in decorator.keywords):
        return True
    positional_reason = text.startswith("pytest.mark.skip(") and decorator.args
    return bool(positional_reason and isinstance(decorator.args[0], ast.Constant))


def test_no_divider_comments() -> None:
    """Section rules go stale and start lying about what follows them."""
    offenders = [
        _rel(p) for p in _python_files() if re.search(r"^[ \t]*#[ \t]*[=\-_*]{5,}[ \t]*$", p.read_text(), re.MULTILINE)
    ]
    assert not offenders, f"divider comments are banned: {offenders}"


def test_nothing_prints() -> None:
    """A test reports through assertions and pytest, not stdout — section 8.

    ``tests/fakeserver`` is exempt: it is a runnable service with a CLI, not a test.
    """
    offenders = [
        _rel(p)
        for p in _python_files()
        if p.relative_to(TESTS).parts[0] != "fakeserver" and re.search(r"(^|[^.\w])print\(", p.read_text())
    ]
    assert not offenders, f"print() is banned in tests — assert instead: {offenders}"


def test_nothing_exits_the_process() -> None:
    """A module that can exit takes the whole run down with it — section 8."""
    offenders = [_rel(p) for p in _python_files() if re.search(r"\bsys\.exit\(", p.read_text())]
    assert not offenders, f"sys.exit() is banned in tests: {offenders}"


def test_skipped_and_expected_failures_state_a_reason() -> None:
    """A skip with no reason becomes permanent — nobody can tell what unblocks it, section 8."""
    unexplained: list[str] = []
    for module in _test_modules():
        if (tree := _parse(module)) is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                text = ast.unparse(decorator)
                if not text.startswith(SKIP_MARKS):
                    continue
                if not _states_a_reason(decorator, text):
                    unexplained.append(f"{_rel(module)}::{node.name} — {text}")
    assert not unexplained, f"skip/xfail without a reason= naming the blocker: {unexplained}"
