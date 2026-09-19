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
)

FIXTURE = Path(__file__).parent / "fixtures" / "workspace"


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


def workspace_with(tmp_path: Path, **workspace_table):
    """A copy of FIXTURE at tmp_path with its root [archview.workspace] table replaced,
    so each test varies exactly one thing."""
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    table = {"packages": ["core", "plugin"], **workspace_table}
    (tmp_path / "archview.toml").write_text(_workspace_toml(table))
    return open_workspace(tmp_path)


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


def test_open_workspace_requires_a_workspace_table(tmp_path):
    (tmp_path / "archview.toml").write_text('[archview]\npackage = "root"\n')
    with pytest.raises(ConfigError, match=r"no \[archview\.workspace\] table"):
        open_workspace(tmp_path)


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
