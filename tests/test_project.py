"""Opening a repo into a `Project` (issue #10)."""

from __future__ import annotations

from archview.project import open_project, project_report


def test_a_source_root_that_contributes_nothing_says_so(tmp_path):
    """`tests/` here is a real package; it is just not under `package`, so the scoping
    drops it - silently, until now (issue #10)."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_a.py").write_text("from pkg import a\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "pkg"\nsource_roots = ["src", "tests"]\n[archview.allowed]\na = []\n'
    )
    report = project_report(open_project(tmp_path))
    note = next(w for w in report.warnings if w.kind == "empty_source_root")
    assert "tests" in note.message


def test_a_source_root_that_contributes_modules_is_quiet(tmp_path):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "pkg"\nsource_roots = ["src"]\n[archview.allowed]\na = []\n'
    )
    report = project_report(open_project(tmp_path))
    assert [w for w in report.warnings if w.kind == "empty_source_root"] == []
