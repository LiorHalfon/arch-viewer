"""Baseline mode: known problems do not fail, new ones do (requirement C7).

A baseline is a list of fingerprints taken from a report: one per import behind a
rule problem, one per cycle (its members), one per component in a failing zone.
Checked against a baseline, a problem only fails for what the baseline does not
cover. A cycle is covered while its members stay inside a recorded cycle, so it
fails again as soon as it grows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from archview.rules.check import Notice, Problem, Report
from archview.rules.config import ConfigError

BASELINE_FILE = "archview-baseline.json"
FORMAT = 1


@dataclass(frozen=True, slots=True)
class Baseline:
    entries: frozenset[tuple[str, ...]]

    def to_json(self) -> str:
        rows = [list(entry) for entry in sorted(self.entries)]
        return json.dumps({"archview_baseline": FORMAT, "entries": rows}, indent=1) + "\n"


WHOLE = ("cycle", "zone", "undeclared", "undeclared_externals")  # not fingerprinted per import


def _fingerprints(problem: Problem) -> list[tuple[str, ...]]:
    if problem.kind in WHOLE:
        return [(problem.kind, *problem.components)]
    return [(problem.kind, *problem.components, i.importer, i.imported) for i in problem.imports]


def baseline_of(report: Report) -> Baseline:
    """Everything that fails today."""
    return Baseline(frozenset(fp for p in report.problems if p.fails for fp in _fingerprints(p)))


def load_baseline(path: Path) -> Baseline:
    try:
        data = json.loads(path.read_text())
    except OSError as error:
        raise ConfigError(f"cannot read baseline {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"baseline {path.name} is not valid JSON: {error}") from error
    if not isinstance(data, dict) or data.get("archview_baseline") != FORMAT:
        raise ConfigError(f"{path.name} is not an archview baseline (format {FORMAT})")
    return Baseline(frozenset(tuple(entry) for entry in data["entries"]))


def _covering(problem: Problem, baseline: Baseline) -> set[tuple[str, ...]]:
    """Baseline entries that cover this problem as a whole."""
    if problem.kind == "cycle":
        members = set(problem.components)
        return {e for e in baseline.entries if e[0] == "cycle" and members <= set(e[1:])}
    fingerprint = _fingerprints(problem)[0]
    return {fingerprint} if fingerprint in baseline.entries else set()


def _apply(problem: Problem, baseline: Baseline) -> tuple[Problem, set[tuple[str, ...]]]:
    """The problem as far as the baseline does not cover it, and the entries it used."""
    if not problem.fails:
        return problem, set()
    if problem.kind in WHOLE:
        used = _covering(problem, baseline)
        return (replace(problem, fails=False, baselined=1) if used else problem), used
    fingerprints = _fingerprints(problem)
    used = {fp for fp in fingerprints if fp in baseline.entries}
    new = tuple(i for i, fp in zip(problem.imports, fingerprints, strict=True) if fp not in used)
    if not new:
        return replace(problem, fails=False, baselined=len(problem.imports)), used
    baselined = len(problem.imports) - len(new)
    return replace(problem, imports=new, count=len(new), baselined=baselined), used


def apply_baseline(report: Report, baseline: Baseline, name: str = BASELINE_FILE) -> Report:
    problems, used = [], set()
    for problem in report.problems:
        applied, hits = _apply(problem, baseline)
        problems.append(applied)
        used |= hits
    warnings = list(report.warnings)
    stale = len(baseline.entries - used)
    if stale:
        warnings.append(
            Notice(
                "stale_baseline",
                f"{stale} baseline entries no longer occur - good; run "
                f"`archview check --update-baseline` to shrink {name}",
            )
        )
    return replace(report, problems=tuple(problems), warnings=tuple(warnings))
