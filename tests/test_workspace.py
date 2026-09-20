"""Workspace mode: several packages checked and drawn as one architecture (issue #2)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from archview.model.graph import Model
from archview.project import Project
from archview.rules.baseline import baseline_of
from archview.rules.config import Config, ConfigError
from archview.workspace import (
    Package,
    _owner,
    aliases,
    check_workspace,
    cross_edges,
    open_workspace,
    workspace_cycles,
    workspace_view,
)
from tests.typescript_support import requires_typescript

FIXTURE = Path(__file__).parent / "fixtures" / "workspace"
TS_FIXTURE = Path(__file__).parent / "fixtures" / "ts-workspace"


def _toml_scalar(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple | list):
        return "[" + ", ".join(_toml_scalar(v) for v in value) + "]"
    raise TypeError(f"unsupported TOML value: {value!r}")


def _workspace_toml(table: dict) -> str:
    """A `[archview.workspace]` table, hand-rolled, from the same table shape parse_config reads."""
    lines = ["[archview.workspace]"]
    for key in ("packages", "fail_on_violations", "fail_on_cycles", "baseline"):
        if key in table:
            lines.append(f"{key} = {_toml_scalar(table[key])}")
    if "allowed" in table:
        lines.append("[archview.workspace.allowed]")
        lines += [f"{name} = {_toml_scalar(targets)}" for name, targets in table["allowed"].items()]
    for forbidden in table.get("forbidden", ()):
        lines.append("[[archview.workspace.forbidden]]")
        lines.append(f"from = {_toml_scalar(forbidden['from'])}")
        lines.append(f"to = {_toml_scalar(forbidden['to'])}")
    for exception in table.get("exceptions", ()):
        lines.append("[[archview.workspace.exceptions]]")
        lines += [f"{k} = {_toml_scalar(exception[k])}" for k in ("importer", "imported", "reason")]
    return "\n".join(lines) + "\n"


def _prepare_workspace(tmp_path: Path, **workspace_table) -> Path:
    """A copy of FIXTURE at tmp_path with its root [archview.workspace] table replaced,
    so each test varies exactly one thing. Not yet opened, so a test can still edit a
    package's own files (a source file, its own archview.toml) before extraction runs."""
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    table = {"packages": ["core", "plugin"], **workspace_table}
    (tmp_path / "archview.toml").write_text(_workspace_toml(table))
    return tmp_path


def workspace_with(tmp_path: Path, **workspace_table):
    """`_prepare_workspace`, opened."""
    return open_workspace(_prepare_workspace(tmp_path, **workspace_table))


def not_allowed(report):
    return [p.components for p in report.problems if p.kind == "not_allowed"]


def _fake_project(repo: Path, package: str, language: str = "python") -> Project:
    """A `Project` with no real extraction behind it, for unit-testing `aliases`."""
    model = Model(project=package, nodes=(), imports=(), language=language)
    return Project(
        repo=repo, package=package, source_root=repo, config=Config(), config_path=None, model=model
    )


def _fake_package(name: str, path: Path) -> Package:
    project = _fake_project(path, name)
    return Package(
        name=name, path=path, aliases=frozenset({name}), project=project, has_rules=False
    )


def test_open_workspace_finds_every_listed_package():
    ws = open_workspace(FIXTURE)
    assert [p.name for p in ws.packages] == ["core", "plugin"]
    assert ws.name == "workspace"


def test_a_package_knows_whether_it_has_its_own_rules():
    ws = open_workspace(FIXTURE)
    by_name = {p.name: p for p in ws.packages}
    assert by_name["core"].has_rules is True
    assert by_name["plugin"].has_rules is False


def test_a_python_package_is_aliased_by_its_top_level_module():
    ws = open_workspace(FIXTURE)
    by_name = {p.name: p for p in ws.packages}
    assert "core" in by_name["core"].aliases


def test_owner_attributes_an_outside_name_to_a_sibling():
    ws = open_workspace(FIXTURE)
    by_name = {p.name: p for p in ws.packages}
    assert _owner("core", by_name["plugin"], ws.packages) == "core"
    assert _owner("openai", by_name["plugin"], ws.packages) is None


def test_aliases_includes_npm_name_with_and_without_scope(tmp_path):
    pkg_dir = tmp_path / "core-ts"
    pkg_dir.mkdir()
    (pkg_dir / "package.json").write_text(json.dumps({"name": "@bespoke/core"}))
    project = _fake_project(pkg_dir, "core-ts", language="typescript")

    assert aliases(project) == frozenset({"core-ts", "@bespoke/core", "core"})


def test_aliases_ignores_missing_or_malformed_package_json(tmp_path):
    pkg_dir = tmp_path / "widget"
    pkg_dir.mkdir()
    project = _fake_project(pkg_dir, "widget", language="typescript")
    assert aliases(project) == frozenset({"widget"})

    (pkg_dir / "package.json").write_text("{not valid json")
    assert aliases(project) == frozenset({"widget"})


def test_aliases_of_a_python_package_ignores_a_stray_package_json(tmp_path):
    # package.json is only consulted for TypeScript packages.
    (tmp_path / "package.json").write_text(json.dumps({"name": "unrelated"}))
    project = _fake_project(tmp_path, "core")
    assert aliases(project) == frozenset({"core"})


def test_owner_resolves_a_relative_typescript_import_to_a_sibling(tmp_path):
    (tmp_path / "component").mkdir()
    (tmp_path / "plugin").mkdir()
    component = _fake_package("component", (tmp_path / "component").resolve())
    plugin = _fake_package("plugin", (tmp_path / "plugin").resolve())

    outside = "../component/src/story"
    assert _owner(outside, plugin, (component, plugin)) == "component"


def test_owner_returns_none_for_a_relative_import_outside_any_package(tmp_path):
    (tmp_path / "plugin").mkdir()
    plugin = _fake_package("plugin", (tmp_path / "plugin").resolve())

    assert _owner("../elsewhere/src/story", plugin, (plugin,)) is None


# ---------- a TypeScript package in a workspace: the real extractor, not a fake Project ----------


@requires_typescript
def test_a_typescript_package_joins_the_workspace():
    ws = open_workspace(TS_FIXTURE)
    assert [p.name for p in ws.packages] == ["core", "web"]


@requires_typescript
def test_a_typescript_package_is_aliased_by_its_npm_name():
    ws = open_workspace(TS_FIXTURE)
    by_name = {p.name: p for p in ws.packages}
    assert by_name["core"].aliases == frozenset({"core", "@fixture/core"})


@requires_typescript
def test_every_typescript_alias_kind_is_attributed_to_the_sibling():
    """`web` reaches `core` three ways: a relative import the TypeScript extractor
    resolves and classifies as external (`../core`), its scoped npm name
    (`@fixture/core`), and its bare package name (`core`). All three must join to the
    same sibling."""
    ws = open_workspace(TS_FIXTURE)
    edges = cross_edges(ws)
    assert list(edges) == [("web", "core")]
    assert len(edges[("web", "core")]) == 3


@requires_typescript
def test_the_typescript_workspace_passes_its_own_rules():
    report = check_workspace(open_workspace(TS_FIXTURE))
    assert not report.failed


def test_open_workspace_requires_a_workspace_table(tmp_path):
    (tmp_path / "archview.toml").write_text('[archview]\npackage = "root"\n')
    with pytest.raises(ConfigError, match=r"no \[archview\.workspace\] table"):
        open_workspace(tmp_path)


def test_open_workspace_error_uses_the_pyproject_table_name(tmp_path):
    """Every other rule name derives from `Config.table`; this one was hardcoded to
    "archview.workspace" (Fix 4, M7/M8 review)."""
    (tmp_path / "pyproject.toml").write_text('[tool.archview]\npackage = "root"\n')
    with pytest.raises(ConfigError, match=r"no \[tool\.archview\.workspace\] table"):
        open_workspace(tmp_path)


def test_between_rules_use_the_pyproject_table_name(tmp_path):
    """`_between_config` hardcoded `table="archview.workspace"`; a workspace root whose
    rules live under `[tool.archview.workspace]` (a `pyproject.toml`) reported problems
    against an identifier that does not exist in that file (Fix 4, M7/M8 review)."""
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    (tmp_path / "archview.toml").unlink()
    (tmp_path / "pyproject.toml").write_text(
        "[tool.archview.workspace]\n"
        'packages = ["core", "plugin"]\n\n'
        "[tool.archview.workspace.allowed]\n"
        "core = []\n"
        "plugin = []\n"
    )

    report = check_workspace(open_workspace(tmp_path))

    assert not_allowed(report.between) == [("plugin", "core")]
    assert report.between.problems[0].rule == "tool.archview.workspace.allowed.plugin"


def test_open_workspace_rejects_two_packages_with_the_same_name(tmp_path):
    (tmp_path / "a" / "shared").mkdir(parents=True)
    (tmp_path / "a" / "shared" / "__init__.py").write_text("")
    (tmp_path / "b" / "shared").mkdir(parents=True)
    (tmp_path / "b" / "shared" / "__init__.py").write_text("")
    (tmp_path / "archview.toml").write_text('[archview.workspace]\npackages = ["a", "b"]\n')

    with pytest.raises(ConfigError, match="both named 'shared'") as excinfo:
        open_workspace(tmp_path)
    message = str(excinfo.value)
    assert str((tmp_path / "a").resolve()) in message
    assert str((tmp_path / "b").resolve()) in message


def test_the_fixture_workspace_passes():
    report = check_workspace(open_workspace(FIXTURE))
    assert not report.failed


def test_a_package_without_rules_is_not_checked_inside():
    report = check_workspace(open_workspace(FIXTURE))
    assert [name for name, _ in report.packages] == ["core"]


def test_a_cross_package_import_that_is_not_allowed_fails(tmp_path):
    ws = workspace_with(tmp_path, allowed={"core": (), "plugin": ()})
    report = check_workspace(ws)
    assert not_allowed(report.between) == [("plugin", "core")]
    assert report.failed


def test_a_package_missing_from_the_workspace_allow_list_is_undeclared(tmp_path):
    ws = workspace_with(tmp_path, allowed={"core": ()})
    report = check_workspace(ws)
    assert [p.kind for p in report.between.problems if p.components == ("plugin",)] == [
        "undeclared"
    ]


def test_a_workspace_exception_exempts_a_cross_package_import(tmp_path):
    ws = workspace_with(
        tmp_path,
        allowed={"core": (), "plugin": ()},
        exceptions=[{"importer": "plugin.adapter", "imported": "core", "reason": "the port"}],
    )
    assert not check_workspace(ws).failed


def test_a_packages_own_exception_does_not_exempt_a_cross_package_import(tmp_path):
    """Only [[archview.workspace.exceptions]] may exempt a cross-package edge; a
    package's own [[archview.exceptions]] must not silently cancel a workspace rule
    (M7 widened exceptions to cover outside edges, and a package's own rules file is
    not the authority for what crosses a package line)."""
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ()})
    (root / "plugin" / "archview.toml").write_text(
        '[archview]\npackage = "plugin"\nsource_roots = ["src"]\n\n'
        "[[archview.exceptions]]\n"
        'importer = "plugin.adapter"\n'
        'imported = "core"\n'
        'reason = "must not exempt a workspace rule"\n'
    )

    report = check_workspace(open_workspace(root))

    assert not_allowed(report.between) == [("plugin", "core")]
    assert report.failed


def test_a_third_party_import_is_not_a_cross_package_edge(tmp_path):
    """plugin imports openai, which is nobody's sibling."""
    ws = workspace_with(tmp_path, allowed={"core": (), "plugin": ("core",)})
    assert "openai" not in {t for _, t in cross_edges(ws)}


def test_a_workspace_baseline_makes_a_known_problem_not_fail(tmp_path):
    raw_ws = workspace_with(tmp_path / "raw", allowed={"core": (), "plugin": ()})
    raw = check_workspace(raw_ws)
    assert raw.failed

    ws_root = tmp_path / "ws"
    ws = workspace_with(
        ws_root, allowed={"core": (), "plugin": ()}, baseline="archview-baseline.json"
    )
    (ws_root / "archview-baseline.json").write_text(baseline_of(raw.between).to_json())

    report = check_workspace(ws)
    assert not report.between.failed
    assert any(p.baselined for p in report.between.problems)


def test_a_missing_workspace_baseline_raises_a_config_error(tmp_path):
    ws = workspace_with(
        tmp_path, allowed={"core": (), "plugin": ()}, baseline="archview-baseline.json"
    )
    with pytest.raises(ConfigError, match=r"archview-baseline\.json"):
        check_workspace(ws)


TYPE_CHECKING_ADAPTER = '''"""A cross-package import that exists only for type checking."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports import Port


class Adapter:
    def __init__(self, port: "Port") -> None:
        self.port = port
'''


def test_a_type_checking_only_cross_package_import_is_ignored_by_default(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ()})
    (root / "plugin" / "src" / "plugin" / "adapter.py").write_text(TYPE_CHECKING_ADAPTER)

    report = check_workspace(open_workspace(root))

    assert "core" not in {t for _, t in cross_edges(open_workspace(root))}
    assert not report.between.failed


def test_a_type_checking_only_cross_package_import_counts_when_included(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ()})
    (root / "plugin" / "src" / "plugin" / "adapter.py").write_text(TYPE_CHECKING_ADAPTER)
    (root / "plugin" / "archview.toml").write_text(
        '[archview]\npackage = "plugin"\nsource_roots = ["src"]\n'
        'type_checking_imports = "include"\n'
    )

    report = check_workspace(open_workspace(root))

    assert not_allowed(report.between) == [("plugin", "core")]
    assert report.failed


def test_a_cycle_between_packages_fails_by_default(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": ("plugin",), "plugin": ("core",)})
    (root / "core" / "src" / "core" / "uses_plugin.py").write_text("from plugin import Adapter\n")

    report = check_workspace(open_workspace(root))

    cycles = [p for p in report.between.problems if p.kind == "cycle"]
    assert [c.components for c in cycles] == [("core", "plugin")]
    assert cycles[0].fails
    assert report.between.failed


def test_fail_on_cycles_false_suppresses_the_cross_package_cycle(tmp_path):
    root = _prepare_workspace(
        tmp_path,
        allowed={"core": ("plugin",), "plugin": ("core",)},
        fail_on_cycles=False,
    )
    (root / "core" / "src" / "core" / "uses_plugin.py").write_text("from plugin import Adapter\n")

    report = check_workspace(open_workspace(root))

    cycles = [p for p in report.between.problems if p.kind == "cycle"]
    assert cycles and not cycles[0].fails
    assert not report.between.failed


def test_the_workspace_view_is_the_packages_and_their_edges():
    view = workspace_view(open_workspace(FIXTURE))
    assert [n.id for n in view.nodes] == ["core", "plugin"]
    assert [(e.source, e.target, e.count) for e in view.edges] == [("plugin", "core", 1)]


def test_the_workspace_view_layers_the_packages():
    view = workspace_view(open_workspace(FIXTURE))
    layers = {n.id: n.layer for n in view.nodes}
    assert layers["plugin"] < layers["core"] or layers["core"] < layers["plugin"]


def test_a_package_node_counts_its_modules():
    view = workspace_view(open_workspace(FIXTURE))
    assert {n.id: n.module_count for n in view.nodes}["core"] == 3


def test_workspace_cycles_finds_none_in_the_fixture():
    assert workspace_cycles(open_workspace(FIXTURE)) == ()


def test_workspace_cycles_reports_a_cross_package_cycle_with_a_path(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": ("plugin",), "plugin": ("core",)})
    (root / "core" / "src" / "core" / "uses_plugin.py").write_text("from plugin import Adapter\n")

    found = workspace_cycles(open_workspace(root))

    assert [c.members for c in found] == [("core", "plugin")]
    assert found[0].path == ("core", "plugin", "core")
    assert [s.imports[0].text for s in found[0].steps] == [
        "from plugin import Adapter",
        "from core.ports import Port",
    ]
