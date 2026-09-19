"""`archview check` at a workspace root (M8): one run, one exit code."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from archview.cli import main
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
