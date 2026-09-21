"""Render a check report as text for humans or JSON for agents and CI (requirement C5)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from archview.model.cycles import describe_cycle
from archview.rules.check import Problem, Report

EXAMPLES = 5
RED, YELLOW, DIM, RESET = "\033[31m", "\033[33m", "\033[2m", "\033[0m"

LABELS = {
    "not_allowed": "VIOLATION",
    "forbidden": "FORBIDDEN",
    "undeclared": "UNDECLARED",
    "cycle": "CYCLE",
    "zone": "ZONE",
    "outside": "OUTSIDE",
    "private": "PRIVATE",
}
ZONE_NAMES = {"pain": "the zone of pain", "useless": "the zone of uselessness"}
# Problem kinds rendered as "A -> B" in text and as from/to in JSON.
PAIRS = ("not_allowed", "forbidden", "outside", "private")


def report_to_dict(report: Report) -> dict[str, Any]:
    return {
        "project": report.project,
        "ok": not report.failed,
        "components": list(report.components),
        "problems": [_problem_dict(p) for p in report.problems],
        "warnings": [asdict(w) for w in report.warnings],
        "metrics": {name: asdict(m) for name, m in sorted(report.metrics.items())},
        "unused_allowances": [{"from": s, "to": t} for s, t in report.unused],
    }


def _problem_dict(problem: Problem) -> dict[str, Any]:
    pair = problem.kind in PAIRS
    return {
        "kind": problem.kind,
        "rule": problem.rule,
        "from": problem.components[0] if pair else None,
        "to": problem.components[1] if pair else None,
        "components": list(problem.components),
        "count": problem.count,
        "fails": problem.fails,
        "baselined": problem.baselined,
        "hint": problem.hint,
        "imports": [asdict(i) for i in problem.imports],
    }


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _headline(problem: Problem, report: Report) -> str:
    label = LABELS[problem.kind]
    c = problem.components
    if problem.kind == "cycle":
        return f"{label} {describe_cycle(c)} ({_plural(problem.count, 'edge')})"
    if problem.kind == "zone":
        return f"{label} {c[0]} is in {ZONE_NAMES[report.metrics[c[0]].zone]}"
    if problem.kind == "undeclared":
        return f"{label} {c[0]} is not in [{problem.rule}]"
    assert problem.kind in PAIRS
    reason = "forbidden by" if problem.kind == "forbidden" else "not allowed by"
    return (
        f"{label} {c[0]} -> {c[1]} ({_plural(problem.count, 'import')}) {reason} [{problem.rule}]"
    )


def _problem_lines(problem: Problem, report: Report, paint) -> list[str]:
    headline = _headline(problem, report)
    if not problem.fails and problem.baselined:
        return [paint(DIM, f"known: {headline}  (in the baseline)")]
    if not problem.fails:
        headline += "  (reported only: switched off in the rules)"
    lines = [paint(RED if problem.fails else YELLOW, headline)]
    if problem.baselined:
        lines.append(f"  (new imports only; {problem.baselined} more are in the baseline)")
    shown = problem.imports[:EXAMPLES]
    width = max((len(f"{i.file}:{i.line}") for i in shown), default=0)
    for i in shown:
        where = f"{i.file}:{i.line}".ljust(width)
        target = "" if i.imported in i.text else paint(DIM, f"  [{i.imported}]")
        lines.append(f"  {where}  {i.text.strip()}{target}")
    if len(problem.imports) > EXAMPLES:
        lines.append(f"  ... and {len(problem.imports) - EXAMPLES} more (--format json lists all)")
    lines.append(f"  hint: {problem.hint}")
    return lines


def report_to_text(report: Report, color: bool = False) -> str:
    def paint(code: str, text: str) -> str:
        return f"{code}{text}{RESET}" if color else text

    lines: list[str] = []
    for problem in report.problems:
        lines += _problem_lines(problem, report, paint)
    for warning in report.warnings:
        lines.append(paint(YELLOW, f"warning: {warning.message}"))
    failing = sum(1 for p in report.problems if p.fails)
    components = _plural(len(report.components), "component")
    known = sum(1 for p in report.problems if p.baselined)
    if known:
        components += f", {known} known in the baseline"
    if failing:
        lines.append(paint(RED, f"{_plural(failing, 'problem')} in {components}. exit 1"))
    else:
        lines.append(f"ok: {report.project}, {components}, no failing problems")
    return "\n".join(lines) + "\n"
