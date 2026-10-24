"""The demo in examples/pizzeria: one cycle and one broken rule, both in the stations."""

from pathlib import Path

from archview.cli import main
from archview.model.view import build_view
from archview.project import open_project, project_report

PIZZERIA = Path(__file__).parent.parent / "examples" / "pizzeria"


def kinds(report):
    """A cycle's members in any order; a violation's (importer, imported) as reported."""
    return sorted(
        (p.kind, tuple(sorted(p.components)) if p.kind == "cycle" else p.components)
        for p in report.problems
    )


def test_the_top_level_passes():
    report = project_report(open_project(PIZZERIA))
    assert report.problems == ()
    assert report.warnings == ()
    assert report.unused == ()


def test_the_stations_have_one_cycle_and_one_broken_rule():
    report = project_report(open_project(PIZZERIA))
    [(_, stations)] = report.scopes
    assert stations.project == "pizzeria.kitchen.stations"
    assert kinds(stations) == [
        ("cycle", ("oven", "toppings")),
        ("not_allowed", ("boxing", "dough")),
    ]


def test_no_view_above_the_stations_draws_a_cycle():
    model = open_project(PIZZERIA).model
    assert build_view(model, "pizzeria").cycles == ()
    assert build_view(model, "pizzeria.kitchen").cycles == ()


def test_check_fails_on_the_demo(capsys):
    assert main(["check", str(PIZZERIA)]) == 1
