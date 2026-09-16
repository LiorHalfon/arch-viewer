"""`archview graph` (requirement G1, roadmap M1)."""

import json
from pathlib import Path

from archview.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def run(capsys, *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


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
