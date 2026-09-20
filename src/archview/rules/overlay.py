"""Where the rule problems show up in a view (requirement V7)."""

from __future__ import annotations

from archview.model.view import View
from archview.rules.check import Report

ImportKey = tuple[str, str, int]


def failing_imports(report: Report) -> frozenset[ImportKey]:
    """Every import behind a failing rule problem (cycles and zones are drawn elsewhere)."""
    return frozenset(
        (i.importer, i.imported, i.line)
        for p in report.problems
        if p.fails and p.kind in ("not_allowed", "forbidden", "undeclared")
        for i in p.imports
    )


def violating_edges(view: View, failing: frozenset[ImportKey]) -> set[tuple[str, str]]:
    """Edges of the view with at least one failing import behind them, at any depth."""
    return {
        (e.source, e.target)
        for e in view.edges
        if any((i.importer, i.imported, i.line) in failing for i in e.imports)
    }


def outside_targets(report: Report) -> frozenset[str]:
    """Names behind a failing outside/forbidden problem, for `build_view`'s `keep`.

    A `build_view` intersects this with the packages actually imported from outside,
    so a `forbidden` problem between two internal components contributes nothing.
    """
    return frozenset(
        p.components[1] for p in report.problems if p.fails and p.kind in ("outside", "forbidden")
    )
