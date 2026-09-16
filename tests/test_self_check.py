"""The tool passes its own checker (requirement N8). Stands in for CI until there is one."""

from pathlib import Path

from archview.project import open_project
from archview.render.check import report_to_text
from archview.rules.check import check

REPO = Path(__file__).parent.parent


def test_archview_passes_its_own_rules():
    project = open_project(REPO)
    report = check(project.model, project.config)

    assert project.config_path == REPO / "archview.toml"
    assert not report.failed, report_to_text(report)
    assert report.warnings == ()
