"""Render a `WorkspaceReport` (M8): the presentation layer for `archview check` at a
workspace root - a section per package, then the cross-package section, then a
single total. The workspace counterpart of `render/check.py`, and deliberately built
on top of it rather than beside it: each section's body is `report_to_text`'s own
output, minus the one-line total it prints for a single project.
"""

from __future__ import annotations

from typing import Any

from archview.render.check import RED, RESET, report_to_dict, report_to_text
from archview.rules.check import Report, WorkspaceReport

BETWEEN = "between packages"


def workspace_to_dict(report: WorkspaceReport) -> dict[str, Any]:
    return {
        "workspace": report.name,
        "ok": not report.failed,
        "packages": [{"package": name, **report_to_dict(r)} for name, r in report.packages],
        "between": report_to_dict(report.between),
    }


def workspace_to_text(report: WorkspaceReport, color: bool = False) -> str:
    sections = [*report.packages, (BETWEEN, report.between)]
    width = max((len(name) for name, _ in report.packages), default=0)
    lines: list[str] = []
    for name, section in sections:
        lines += _section(name, section, width, color)
    lines.append(_total(report, sections, color))
    return "\n".join(lines) + "\n"


def _paint(code: str, text: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def _section(name: str, report: Report, width: int, color: bool) -> list[str]:
    failing = _failing(report)
    status = "ok" if not failing else _plural(failing, "problem")
    header = f"{name.ljust(width)}  {status}"
    lines = [_paint(RED, header, color) if failing else header]
    lines += [f"  {line}" for line in _body(report, color)]
    return lines


def _body(report: Report, color: bool) -> list[str]:
    """`report_to_text`'s own lines, minus the one-line total it ends with - the
    workspace run prints a single total across every section instead."""
    return report_to_text(report, color).rstrip("\n").split("\n")[:-1]


def _total(report: WorkspaceReport, sections: list[tuple[str, Report]], color: bool) -> str:
    if not report.failed:
        return f"ok: {report.name}, {_summary(report)}, no failing problems"
    failing = sum(_failing(section) for _, section in sections)
    return _paint(RED, f"{_plural(failing, 'problem')}. exit 1", color)


def _summary(report: WorkspaceReport) -> str:
    """Every workspace member, not just the ones checked inside: `between.components`
    lists all of them (`_check_between` sets it from every package, with or without
    its own rules), while `report.packages` only holds the ones that have rules of
    their own. A bare `len(report.packages)` would undercount a workspace where a
    member has no rules file, as `plugin` does not in the M8 fixture."""
    total = len(report.between.components)
    checked = len(report.packages)
    summary = _plural(total, "package")
    return summary if checked == total else f"{summary} ({checked} checked inside)"


def _failing(report: Report) -> int:
    return sum(1 for p in report.problems if p.fails)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
