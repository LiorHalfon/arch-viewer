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


def test_check_with_a_package_checks_that_package_alone(capsys):
    """`--package` drills `check` into one member exactly as it already does for
    `graph`/`cycles` - the same rules, the same exit code, as if run inside that
    package's own directory."""
    assert main(["check", str(FIXTURE), "--package", "core"]) == 0
    assert "ok: core" in capsys.readouterr().out


def test_check_with_a_package_that_has_no_rules_fails_clearly(capsys):
    assert main(["check", str(FIXTURE), "--package", "plugin"]) == 2
    assert "no archview.toml" in capsys.readouterr().err


def test_check_with_an_unknown_package_fails_clearly(capsys):
    assert main(["check", str(FIXTURE), "--package", "bogus"]) == 2
    assert "no package 'bogus' in workspace" in capsys.readouterr().err


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


def test_metrics_with_a_package_drills_in(capsys):
    """`_metrics` used `_open(args)` directly, skipping `_workspace_member` - so
    `--package` at a workspace root failed with "no package … (found: none)" even
    though the workspace listed packages (Fix 3, M7/M8 review)."""
    assert main(["metrics", str(FIXTURE), "--package", "core"]) == 0
    out = capsys.readouterr().out
    assert "model" in out
    assert "ports" in out


def test_metrics_with_an_unknown_package_fails_clearly(capsys):
    assert main(["metrics", str(FIXTURE), "--package", "bogus"]) == 2
    assert "no package 'bogus' in workspace" in capsys.readouterr().err


def test_deps_with_a_package_drills_in(capsys):
    """`deps`/`why`/`rdeps` all go through `_query_model`, which had the same bug as
    `_metrics` (Fix 3)."""
    assert main(["deps", "ports", str(FIXTURE), "--package", "core"]) == 0
    assert "model" in capsys.readouterr().out


def test_rdeps_with_a_package_drills_in(capsys):
    assert main(["rdeps", "model", str(FIXTURE), "--package", "core"]) == 0
    assert "ports" in capsys.readouterr().out


def test_why_with_a_package_drills_in(capsys):
    assert main(["why", "ports", "model", str(FIXTURE), "--package", "core"]) == 0
    assert "core.ports -> core.model" in capsys.readouterr().out


def test_deps_with_an_unknown_package_fails_clearly(capsys):
    assert main(["deps", "ports", str(FIXTURE), "--package", "bogus"]) == 2
    assert "no package 'bogus' in workspace" in capsys.readouterr().err


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


def test_runtime_only_at_a_workspace_root_is_rejected_for_cycles(capsys):
    """`--runtime-only` is the same class of bug as `--root`/`--hide-tests`/
    `--externals`: `cycles` accepts it (`_query_options`), but at a workspace root it
    was silently ignored - `workspace_cycles` never filters by it. `graph` has no
    `--runtime-only` flag at all, so it needs no rejection there."""
    assert main(["cycles", str(FIXTURE), "--runtime-only"]) == 2
    err = capsys.readouterr().err
    assert "--runtime-only" in err
    assert "--package" in err


@pytest.mark.parametrize("fmt", ["--mermaid", "--dot"])
def test_graph_at_a_workspace_root_marks_a_cross_package_violation(tmp_path, capsys, fmt):
    """Mirrors test_cli_check.py::test_graph_prints_mermaid_with_violations_marked:
    `_graph`'s workspace branch wires `violating_edges(view,
    failing_imports(check_workspace(ws).between))` into `dot`/`mermaid` output so a
    broken cross-package rule is highlighted without a flag - this pins that it
    actually highlights one, not just that the wiring exists."""
    root = workspace_dir(tmp_path, allowed={"core": (), "plugin": ()})

    code, out = run(capsys, "graph", str(root), fmt)

    assert code == 0
    if fmt == "--mermaid":
        assert "n_plugin -. 1 ✗ .-> n_core" in out
    else:
        assert '"plugin" -> "core" [label="1" color="#d9480f" style="dashed"' in out
