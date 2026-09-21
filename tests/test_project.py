"""Opening a repo into a `Project` (issue #10)."""

from __future__ import annotations

import json

from archview.project import open_project, project_report
from tests.typescript_support import TS_SAMPLE, requires_typescript


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


def test_a_dot_source_root_is_not_a_false_positive(tmp_path):
    """`Path.resolve()` inside `build_model` normalises away a `.` segment, so a file
    built from a `.` root never literally starts with `./` - the naive prefix check
    would wrongly say the root that built the model contributed nothing to it."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "pkg"\nsource_roots = ["."]\n[archview.allowed]\na = []\n'
    )
    report = project_report(open_project(tmp_path))
    assert [w for w in report.warnings if w.kind == "empty_source_root"] == []


def test_a_root_that_never_wins_says_so_even_alongside_one_that_does(tmp_path):
    """Round 2's regression, pinned: a special case that always answers `True` for
    `"."` stops noticing `"."` even when - as here - the package lives only under
    `src/` and `.` never won anything."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "pkg"\nsource_roots = [".", "src"]\n[archview.allowed]\na = []\n'
    )
    report = project_report(open_project(tmp_path))
    notes = [w.message for w in report.warnings if w.kind == "empty_source_root"]
    assert notes == [
        "source root '.' contributed no modules to package 'pkg'; "
        "only code under the package is analysed"
    ]


def test_a_trailing_dot_slash_root_is_silent(tmp_path):
    """`"./"` names the same directory as `"."` - a spelling difference, not a
    different root."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "pkg"\nsource_roots = ["./"]\n[archview.allowed]\na = []\n'
    )
    report = project_report(open_project(tmp_path))
    assert [w for w in report.warnings if w.kind == "empty_source_root"] == []


def test_a_trailing_slash_root_is_silent(tmp_path):
    """`"src/"` names the same directory as `"src"`."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "pkg"\nsource_roots = ["src/"]\n[archview.allowed]\na = []\n'
    )
    report = project_report(open_project(tmp_path))
    assert [w for w in report.warnings if w.kind == "empty_source_root"] == []


def _ts_project(tmp_path):
    """A minimal TypeScript project - a `src/` layout, mirroring how
    test_typescript_project.py's `test_init_pins_the_inferred_source_root_...` builds
    one inline."""
    (tmp_path / "node_modules").symlink_to(TS_SAMPLE / "node_modules")
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "package.json").write_text(json.dumps({"name": "@acme/proj"}))
    (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["src"]}))
    (tmp_path / "src" / "api" / "a.ts").write_text("export const a = 1;\n")


@requires_typescript
def test_a_typescript_source_root_that_matches_nothing_says_so(tmp_path):
    """`open_project`'s TypeScript path never checks that a configured root matched
    any file - `_below` just filters, so a typo'd single root still lets it succeed,
    with an almost-empty model, unless something else says so (issue #10)."""
    _ts_project(tmp_path)
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "proj"\nsource_roots = ["lib"]\n'
    )
    report = project_report(open_project(tmp_path))
    note = next(w for w in report.warnings if w.kind == "empty_source_root")
    assert "lib" in note.message


@requires_typescript
def test_a_typescript_source_root_that_matches_is_quiet(tmp_path):
    _ts_project(tmp_path)
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "proj"\nsource_roots = ["src"]\n'
    )
    report = project_report(open_project(tmp_path))
    assert [w for w in report.warnings if w.kind == "empty_source_root"] == []
