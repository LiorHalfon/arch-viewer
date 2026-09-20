"""`archview check` at a workspace root (M8): one run, one exit code."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from archview.cli import main
from archview.render.workspace import workspace_to_text
from archview.rules.check import Report, WorkspaceReport
from tests.test_golden import check as golden

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "workspace"


@pytest.fixture
def repo(tmp_path):
    """A writable copy of the (non-workspace) fixture project."""
    shutil.copytree(FIXTURES / "sample", tmp_path / "sample")
    return tmp_path


def run(capsys, *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


def workspace_dir(tmp_path: Path, **workspace_table) -> Path:
    """A writable copy of FIXTURE with its root `[archview.workspace]` table replaced
    by `workspace_table` (packages default to core/plugin), so a test can vary one rule
    without touching the others."""
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    table = {"packages": ["core", "plugin"], **workspace_table}
    lines = ["[archview.workspace]", f"packages = {json.dumps(table['packages'])}"]
    if "allowed" in table:
        lines.append("[archview.workspace.allowed]")
        lines += [
            f"{name} = {json.dumps(list(targets))}" for name, targets in table["allowed"].items()
        ]
    (tmp_path / "archview.toml").write_text("\n".join(lines) + "\n")
    return tmp_path


def test_check_at_a_workspace_root_checks_every_package(capsys):
    assert main(["check", str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert "core" in out
    assert "between packages" in out


def test_check_at_a_workspace_root_fails_on_a_cross_package_violation(tmp_path, capsys):
    root = workspace_dir(tmp_path, allowed={"core": (), "plugin": ()})

    assert main(["check", str(root)]) == 1
    assert "plugin -> core" in capsys.readouterr().out


def test_the_json_envelope(tmp_path, capsys):
    root = workspace_dir(tmp_path, allowed={"core": (), "plugin": ()})

    assert main(["check", str(root), "--format", "json"]) == 1
    data = json.loads(capsys.readouterr().out)

    assert data["workspace"] == root.name
    assert data["ok"] is False
    assert [p["package"] for p in data["packages"]] == ["core"]
    assert data["between"]["problems"][0]["from"] == "plugin"


def test_a_repo_without_a_workspace_table_is_unchanged(repo, capsys):
    """The existing single-package output must not move: this compares byte for byte
    against the golden file pinned before workspace mode existed, not just the
    presence or absence of the new keys."""
    run(capsys, "init", str(repo))
    rules = repo / "archview.toml"
    rules.write_text(rules.read_text().replace("fail_on_cycles = false", "fail_on_cycles = true"))

    code, out = run(capsys, "check", str(repo), "--format", "json")

    assert code == 1
    data = json.loads(out)
    assert "workspace" not in data
    assert "packages" not in data
    golden("sample-check.json", out)


def test_a_workspace_root_does_not_ask_you_to_pick_a_package(tmp_path, capsys):
    root = workspace_dir(tmp_path)
    assert main(["check", str(root)]) == 0


def test_the_header_columns_and_the_summary_are_pinned_exactly():
    """The header column width is reflow-sensitive - it is derived from the longest
    package name, so it silently changes whenever a package is added or removed
    (N1: identical input must give byte-identical output). Pin the literal lines,
    padding included, rather than only checking a substring appears somewhere.

    This also pins the summary line's package count: it must report every workspace
    member (from `between.components`, which lists all of them), not just the ones
    checked inside - a bare `len(report.packages)` undercounts a workspace where a
    member has no rules file of its own, as `plugin` does not in the real fixture.
    """
    a = Report("a", ("a",), (), ())
    bcdef = Report("bcdef", ("bcdef",), (), ())
    between = Report("workspace", ("a", "bcdef", "uncheckable"), (), ())
    report = WorkspaceReport("workspace", (("a", a), ("bcdef", bcdef)), between)

    text = workspace_to_text(report)

    assert text.splitlines() == [
        "a      ok",
        "bcdef  ok",
        "between packages  ok",
        "ok: workspace, 3 packages (2 checked inside), no failing problems",
    ]


def test_the_summary_does_not_qualify_the_count_when_every_package_has_rules():
    a = Report("a", ("a",), (), ())
    between = Report("workspace", ("a",), (), ())
    report = WorkspaceReport("workspace", (("a", a),), between)

    text = workspace_to_text(report)

    assert text.splitlines()[-1] == "ok: workspace, 1 package, no failing problems"


def test_graph_at_a_workspace_root_shows_the_packages(capsys):
    assert main(["graph", str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert "plugin" in out and "core" in out


def test_graph_with_a_package_drills_in(capsys):
    assert main(["graph", str(FIXTURE), "--package", "core"]) == 0
    assert "ports" in capsys.readouterr().out


def test_graph_with_an_unknown_package_fails_clearly(capsys):
    assert main(["graph", str(FIXTURE), "--package", "bogus"]) == 2
    assert "no package 'bogus' in workspace" in capsys.readouterr().err


def test_cycles_at_a_workspace_root_finds_none_in_the_fixture(capsys):
    assert main(["cycles", str(FIXTURE)]) == 0
    assert "no cycles under workspace" in capsys.readouterr().out


def test_cycles_with_a_package_drills_in(capsys):
    assert main(["cycles", str(FIXTURE), "--package", "core"]) == 0
    assert "no cycles under core" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["graph", "cycles"])
@pytest.mark.parametrize("flag", ["--root", "--hide-tests"])
def test_a_package_scoped_flag_at_a_workspace_root_is_rejected(capsys, command, flag):
    """Silently ignoring `--root`/`--hide-tests`/`--externals` at a workspace root
    would let a user believe they had scoped the view down when they had not."""
    argv = [command, str(FIXTURE), flag]
    if flag == "--root":
        argv.append("core")

    assert main(argv) == 2
    err = capsys.readouterr().err
    assert flag in err
    assert "--package" in err


def test_externals_at_a_workspace_root_is_rejected_for_graph(capsys):
    assert main(["graph", str(FIXTURE), "--externals"]) == 2
    err = capsys.readouterr().err
    assert "--externals" in err
    assert "--package" in err
