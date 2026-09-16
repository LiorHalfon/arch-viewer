"""Compare the actual dependencies with the rules (requirements C3, C4, G4).

The checker reports; it never fixes. Every problem carries the rule it breaks, the
components, the concrete imports behind it and a one-line remedy hint written for
an agent with a small context budget.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from archview.model.cycles import find_cycles
from archview.model.graph import Import, Model
from archview.model.patterns import matches_name
from archview.rules.components import ComponentMap
from archview.rules.config import ALL, Config

ProblemKind = Literal["not_allowed", "forbidden", "undeclared", "cycle"]
Pair = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Problem:
    kind: ProblemKind
    rule: str
    components: tuple[str, ...]
    count: int
    imports: tuple[Import, ...]
    hint: str
    fails: bool = True


@dataclass(frozen=True, slots=True)
class Notice:
    kind: str
    message: str


@dataclass(frozen=True, slots=True)
class Report:
    project: str
    components: tuple[str, ...]
    problems: tuple[Problem, ...]
    warnings: tuple[Notice, ...]

    @property
    def failed(self) -> bool:
        return any(p.fails for p in self.problems)


def component_map(config: Config, project: str) -> ComponentMap:
    return ComponentMap(project, config.components, frozenset(config.ignored))


def component_edges(
    model: Model, components: ComponentMap, config: Config | None = None
) -> tuple[dict[Pair, list[Import]], set[int]]:
    """Imports grouped by the pair of components they connect, minus exempted ones.

    Also returns the indexes of the exceptions that exempted something, so unused
    exceptions can be reported.
    """
    exemptions = config.exceptions if config else ()
    grouped: dict[Pair, list[Import]] = defaultdict(list)
    used: set[int] = set()
    for imp in model.imports:
        source, target = components.of(imp.importer), components.of(imp.imported)
        if source is None or target is None or source == target:
            continue
        hit = _exemption(imp, exemptions)
        if hit is not None:
            used.add(hit)
            continue
        grouped[(source, target)].append(imp)
    return dict(sorted(grouped.items())), used


def _exemption(imp: Import, exemptions) -> int | None:
    for index, e in enumerate(exemptions):
        if matches_name(e.importer, imp.importer) and matches_name(e.imported, imp.imported):
            return index
    return None


def present_components(model: Model, components: ComponentMap) -> tuple[str, ...]:
    """Components that own at least one file; the project root only if it imports or is imported."""
    found = {components.of(n.id) for n in model.nodes if n.file and n.id != model.project}
    touched = {components.of(i.importer) for i in model.imports} | {
        components.of(i.imported) for i in model.imports
    }
    if components.of(model.project) in touched:
        found.add(components.of(model.project))
    found.discard(None)
    return tuple(sorted(found))  # type: ignore[arg-type]


def check(model: Model, config: Config) -> Report:
    components = component_map(config, model.project)
    present = present_components(model, components)
    edges, used = component_edges(model, components, config)
    table = config.table

    problems = [
        *_rule_problems(edges, present, config, table),
        *_cycle_problems(edges, present, config, table),
    ]
    warnings = _warnings(model, config, components, present, used, table)
    return Report(model.project, present, tuple(problems), tuple(warnings))


def _rule_problems(
    edges: dict[Pair, list[Import]], present: tuple[str, ...], config: Config, table: str
) -> list[Problem]:
    forbidden = {(f.source, f.target) for f in config.forbidden}
    allowed = config.allowed
    fails = config.fail_on_violations
    problems: list[Problem] = []
    if allowed is not None:
        for component in present:
            if component not in allowed:
                outgoing = [i for (s, _), imps in edges.items() if s == component for i in imps]
                problems.append(_undeclared(component, outgoing, table, fails))
    for (source, target), imports in edges.items():
        if (source, target) in forbidden:
            problems.append(_forbidden(source, target, imports, table, fails))
        elif allowed is not None and source in allowed and not _may(allowed, source, target):
            problems.append(_not_allowed(source, target, imports, allowed, table, fails))
    return sorted(problems, key=lambda p: (p.components, p.kind))


def _may(allowed: dict, source: str, target: str) -> bool:
    targets = allowed.get(source, ())
    return targets == ALL or target in targets


def _undeclared(component: str, outgoing: list[Import], table: str, fails: bool) -> Problem:
    return Problem(
        kind="undeclared",
        rule=f"{table}.allowed",
        components=(component,),
        count=len(outgoing),
        imports=tuple(outgoing),
        hint=(
            f"{component} is not declared in [{table}.allowed]; a human decides what a new "
            "component may import - ask before adding it."
        ),
        fails=fails,
    )


def _forbidden(source: str, target: str, imports: list[Import], table: str, fails: bool) -> Problem:
    return Problem(
        kind="forbidden",
        rule=f"{table}.forbidden",
        components=(source, target),
        count=len(imports),
        imports=tuple(imports),
        hint=(
            f"{source} must never depend on {target}: invert the dependency (declare the "
            f"interface in {source}, implement it in {target}) or move the code."
        ),
        fails=fails,
    )


def _not_allowed(
    source: str, target: str, imports: list[Import], allowed: dict, table: str, fails: bool
) -> Problem:
    if _may(allowed, target, source):
        hint = (
            f"{target} may depend on {source}, so this import runs against the declared "
            f"direction: invert it (declare the interface {source} needs inside {source}, "
            f"implement it in {target}) or move the code that needs {target} out of {source}."
        )
    else:
        may = ", ".join(allowed[source]) or "nothing"
        hint = (
            f"{source} may import only: {may}. Move the code that needs {target}, go through "
            "an allowed component, or ask a human to change the rule."
        )
    return Problem(
        kind="not_allowed",
        rule=f"{table}.allowed.{source}",
        components=(source, target),
        count=len(imports),
        imports=tuple(imports),
        hint=hint,
        fails=fails,
    )


def _cycle_problems(
    edges: dict[Pair, list[Import]], present: tuple[str, ...], config: Config, table: str
) -> list[Problem]:
    problems = []
    for cycle in find_cycles(present, edges):
        members = set(cycle)
        inside = {pair: imps for pair, imps in edges.items() if set(pair) <= members}
        weakest = min(inside, key=lambda pair: (len(inside[pair]), pair))
        problems.append(
            Problem(
                kind="cycle",
                rule=f"{table}.fail_on_cycles",
                components=cycle,
                count=len(inside),
                imports=tuple(i for imps in inside.values() for i in imps),
                hint=(
                    f"break the cycle where it is thinnest: {weakest[0]} -> {weakest[1]} "
                    f"({_imports(len(inside[weakest]))}) - invert that dependency or move the code."
                ),
                fails=config.fail_on_cycles,
            )
        )
    return problems


def _imports(count: int) -> str:
    return "1 import" if count == 1 else f"{count} imports"


def _warnings(
    model: Model,
    config: Config,
    components: ComponentMap,
    present: tuple[str, ...],
    used: set[int],
    table: str,
) -> list[Notice]:
    known = set(present)
    warnings = []
    if config.allowed is None:
        warnings.append(
            Notice(
                "no_rules",
                f"no [{table}.allowed] table: only cycles are checked; "
                "run `archview init` to write one",
            )
        )
    for component, targets in sorted((config.allowed or {}).items()):
        for name in [component] + ([] if targets == ALL else list(targets)):
            if name not in known:
                warnings.append(
                    Notice(
                        "unknown_component",
                        f"[{table}.allowed.{component}] names {name!r}, which has no modules",
                    )
                )
    for f in config.forbidden:
        for name in (f.source, f.target):
            if name not in known:
                warnings.append(
                    Notice(
                        "unknown_component",
                        f"[[{table}.forbidden]] names {name!r}, which has no modules",
                    )
                )
    for index, e in enumerate(config.exceptions):
        if index not in used:
            warnings.append(
                Notice(
                    "unused_exception",
                    f"exception {e.importer} -> {e.imported} matches no import; remove it",
                )
            )
    modules = [n.id for n in model.nodes]
    for name, pattern in components.unmatched_patterns(modules):
        warnings.append(
            Notice(
                "unmatched_pattern",
                f"[{table}.components.{name}] pattern {pattern!r} matches no module",
            )
        )
    return _dedupe(warnings)


def _dedupe(warnings: list[Notice]) -> list[Notice]:
    return list(dict.fromkeys(warnings))
