"""`render/check.py`'s wording for each problem kind (requirement C5)."""

from __future__ import annotations

from archview.render.check import report_to_text
from archview.rules.check import Problem, Report


def _problem(kind: str, components: tuple[str, ...]) -> Problem:
    return Problem(
        kind=kind,
        rule="archview.forbidden",
        components=components,
        count=1,
        imports=(),
        hint="invert the dependency",
    )


def test_a_forbidden_problem_is_rendered_as_forbidden_by():
    """The branch inverted `reason = "not allowed by" if kind == "not_allowed" else
    "forbidden by"` to the other way round - a real fix, since the old form would have
    labelled an `outside` problem "forbidden by" - but nothing asserted the "forbidden
    by" wording (Fix 6, M7/M8 review)."""
    report = Report("proj", ("a", "b"), (_problem("forbidden", ("a", "b")),), ())

    text = report_to_text(report)

    assert "FORBIDDEN a -> b (1 import) forbidden by [archview.forbidden]" in text
    assert "not allowed by" not in text
