"""`archview graph` (requirement G1, roadmap M1)."""

import json
import shutil
from pathlib import Path

import pytest

from archview.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def run(capsys, *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


@pytest.fixture
def repo(tmp_path):
    """A writable copy of the fixture project."""
    shutil.copytree(FIXTURES / "sample", tmp_path / "sample")
    return tmp_path


def rules_with_one_outside_violation(capsys, repo):
    run(capsys, "init", str(repo))
    rules = repo / "archview.toml"
    rules.write_text(rules.read_text() + "\n[archview.externals]\napi = []\n")


def test_prints_the_derived_view_of_the_root_as_json(capsys):
    code, out = run(capsys, "graph", str(FIXTURES), "--json")

    view = json.loads(out)
    assert code == 0
    assert view["root"] == "sample"
    assert [n["name"] for n in view["nodes"]] == ["api", "domain", "infra", "services"]


def test_reports_the_cycle_between_services_and_infra(capsys):
    _, out = run(capsys, "graph", str(FIXTURES), "--json")

    assert json.loads(out)["cycles"] == [["sample.infra", "sample.services"]]


def test_drills_down_into_a_sub_package(capsys):
    _, out = run(capsys, "graph", str(FIXTURES), "--root", "sample.api", "--json")

    view = json.loads(out)
    assert view["root"] == "sample.api"
    assert [n["name"] for n in view["nodes"]] == ["routes"]


def test_lists_the_imports_behind_an_edge(capsys):
    _, out = run(capsys, "graph", str(FIXTURES), "--json")

    edge = next(
        e
        for e in json.loads(out)["edges"]
        if (e["source"], e["target"]) == ("sample.api", "sample.services")
    )
    assert edge["imports"] == [
        {
            "importer": "sample.api.routes",
            "imported": "sample.services.pricing",
            "file": "sample/api/routes.py",
            "line": 11,
            "text": "from sample.services import pricing",
            "type_checking": False,
            "lazy": False,
            # null for Python: grimp squashes an external target, so a single
            # package's model cannot say more than `imported` already does.
            "resolved": None,
        }
    ]


def test_emits_graphviz_dot(capsys):
    _, out = run(capsys, "graph", str(FIXTURES), "--dot")

    assert out.startswith('digraph "sample" {')


def test_summarises_layers_and_cycles_as_text_by_default(capsys):
    _, out = run(capsys, "graph", str(FIXTURES))

    assert "sample.api" in out
    assert "sample.infra -> sample.services -> sample.infra" in out


def test_rejects_a_root_that_is_not_in_the_project(capsys):
    assert main(["graph", str(FIXTURES), "--root", "nope.at.all"]) == 2


def test_rejects_a_root_that_has_no_children(capsys):
    assert main(["graph", str(FIXTURES), "--root", "sample.domain.model"]) == 2
    assert "no children" in capsys.readouterr().err


def test_asks_which_package_to_use_when_a_repo_has_several(tmp_path, capsys):
    for name in ("alpha", "beta"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "__init__.py").write_text("")

    assert main(["graph", str(tmp_path)]) == 2
    assert "alpha, beta" in capsys.readouterr().err


def test_writes_module_counts_in_the_singular_when_there_is_only_one(capsys):
    _, out = run(capsys, "graph", str(FIXTURES), "--root", "sample.api")

    assert "(1 module," in out


def test_shows_a_violating_outside_package_without_externals(repo, capsys):
    rules_with_one_outside_violation(capsys, repo)

    code, out = run(capsys, "graph", str(repo), "--json")

    assert code == 0
    view = json.loads(out)
    assert "grimp" in [n["id"] for n in view["nodes"]]
    assert ("sample.api", "grimp") in [(e["source"], e["target"]) for e in view["edges"]]


def test_does_not_show_an_external_package_no_rule_breaks_on(capsys):
    _, out = run(capsys, "graph", str(FIXTURES), "--json")

    assert "grimp" not in [n["id"] for n in json.loads(out)["nodes"]]


def test_shows_no_outside_package_when_there_is_no_rules_file(repo, capsys):
    code, out = run(capsys, "graph", str(repo), "--json")

    assert code == 0
    assert "grimp" not in [n["id"] for n in json.loads(out)["nodes"]]


def test_graph_degrades_when_the_rules_file_is_broken(repo, capsys):
    """A broken rules file (here, a baseline that does not exist) must not stop `graph`
    from drawing the view - `server/state.py::_analyse` already degrades this way, and
    `graph` reversed an earlier ruling to match it (Fix 5, M7/M8 review)."""
    run(capsys, "init", str(repo))
    rules = repo / "archview.toml"
    rules.write_text(
        rules.read_text().replace(
            "fail_on_cycles = false", 'fail_on_cycles = false\nbaseline = "gone.json"'
        )
    )

    code, out = run(capsys, "graph", str(repo), "--json")

    assert code == 0
    assert json.loads(out)["root"] == "sample"


def test_a_path_without_a_command_opens_the_viewer(monkeypatch):
    from archview import cli

    seen = {}
    monkeypatch.setattr(cli, "_serve", lambda args: seen.setdefault("path", args.path) and 0)

    assert main([str(FIXTURES)]) == 0
    assert seen["path"] == FIXTURES


def test_no_arguments_opens_the_viewer_on_the_current_directory(monkeypatch):
    from archview import cli

    seen = {}
    monkeypatch.setattr(cli, "_serve", lambda args: seen.setdefault("path", args.path) and 0)

    assert main([]) == 0
    assert seen["path"] == Path(".")
