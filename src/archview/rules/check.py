"""Compare the actual dependencies with the rules (requirements C3, C4, G4).

The checker reports; it never fixes. Every problem carries the rule it breaks, the
components, the concrete imports behind it and a one-line remedy hint written for
an agent with a small context budget.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Literal

from archview.model.cycles import find_cycles
from archview.model.graph import Import, Model
from archview.model.metrics import Metrics, metrics
from archview.model.patterns import matches_name
from archview.rules.components import ComponentMap
from archview.rules.config import ALL, ALL_COMPONENTS, Config, ConfigError, Forbidden

ProblemKind = Literal[
    "not_allowed",
    "forbidden",
    "undeclared",
    "cycle",
    "zone",
    "outside",
    "private",
    "undeclared_externals",
]
Pair = tuple[str, str]
# How an extractor warning reads in the report; the viewer uses the same words.
WARNING_LABELS = {"dynamic_import": "dynamic import", "unresolved_import": "unresolved import"}


@dataclass(frozen=True, slots=True)
class Problem:
    kind: ProblemKind
    rule: str
    components: tuple[str, ...]
    count: int
    imports: tuple[Import, ...]
    hint: str
    fails: bool = True
    baselined: int = 0


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
    metrics: dict[str, Metrics] = field(default_factory=dict)
    unused: tuple[Pair, ...] = ()

    @property
    def failed(self) -> bool:
        return any(p.fails for p in self.problems)


@dataclass(frozen=True, slots=True)
class WorkspaceReport:
    """A workspace's check: each package's own report, plus the rules between them.

    Pure report data - nothing here references `workspace.py`, so `render/check.py`
    and its siblings can render `between` (an ordinary `Report`) without depending on
    `workspace`, `project` or `extract`.
    """

    name: str
    packages: tuple[tuple[str, Report], ...]
    between: Report

    @property
    def failed(self) -> bool:
        return self.between.failed or any(report.failed for _, report in self.packages)


def component_map(config: Config, project: str, sep: str) -> ComponentMap:
    return ComponentMap(project, sep, config.components, frozenset(config.ignored))


@dataclass(frozen=True, slots=True)
class Edges:
    """Imports grouped by the pair they connect, split by whether the target is inside."""

    internal: dict[Pair, list[Import]]
    outside: dict[Pair, list[Import]]
    exceptions_used: set[int]


def component_edges(model: Model, components: ComponentMap, config: Config | None = None) -> Edges:
    """Imports grouped by the components they connect, minus exempted ones.

    `outside` holds the imports whose target is an external node; `exceptions_used`
    holds the indexes of the exceptions that exempted something, so unused ones
    can be reported.
    """
    exemptions = config.exceptions if config else ()
    external = {n.id for n in model.nodes if n.kind == "external"}
    internal: dict[Pair, list[Import]] = defaultdict(list)
    outside: dict[Pair, list[Import]] = defaultdict(list)
    used: set[int] = set()
    for imp in model.imports:
        pair = _pair(imp, components, external)
        if pair is None:
            continue
        hit = _exemption(imp, exemptions, model.separator)
        if hit is not None:
            used.add(hit)
            continue
        bucket = outside if imp.imported in external else internal
        bucket[pair].append(imp)
    return Edges(dict(sorted(internal.items())), dict(sorted(outside.items())), used)


def _pair(imp: Import, components: ComponentMap, external: set[str]) -> Pair | None:
    """(source component, target) for an import the rules care about, else None."""
    source = components.of(imp.importer)
    if source is None:
        return None
    if imp.imported in external:
        target = components.outside(imp.imported)
        return None if target is None else (source, target)
    target = components.of(imp.imported)
    return None if target is None or target == source else (source, target)


def _exemption(imp: Import, exemptions, sep: str) -> int | None:
    for index, e in enumerate(exemptions):
        if matches_name(e.importer, imp.importer, sep) and matches_name(
            e.imported, imp.imported, sep
        ):
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


def checked_imports(model: Model, config: Config) -> Model:
    """The model as the rules see it: TYPE_CHECKING imports dropped unless included (A4)."""
    if config.type_checking_imports == "include":
        return model
    return replace(model, imports=tuple(i for i in model.imports if not i.type_checking))


def check(model: Model, config: Config, in_workspace: bool = False) -> Report:
    model = checked_imports(model, config)
    components = component_map(config, model.project, model.separator)
    present = present_components(model, components)
    _reject_outside_sources(model, config)
    edges = component_edges(model, components, config)
    table = config.table
    measured = component_metrics(
        model, components, edges.internal, present, config.metrics.threshold
    )

    problems = [
        *_rule_problems(edges, present, config, table),
        *_cycle_problems(edges.internal, present, config, table),
        *_zone_problems(measured, config, table),
    ]
    warnings = _warnings(model, config, components, present, edges, table, in_workspace)
    return Report(
        model.project,
        present,
        tuple(problems),
        tuple(warnings),
        measured,
        _unused(edges.internal, present, config),
    )


def component_metrics(
    model: Model,
    components: ComponentMap,
    edges: dict[Pair, list[Import]],
    present: tuple[str, ...],
    threshold: float,
) -> dict[str, Metrics]:
    files: dict[str, list[bool]] = defaultdict(list)
    for node in model.nodes:
        owner = components.of(node.id) if node.file else None
        if owner is not None:
            files[owner].append(node.abstract)
    result = {}
    for c in present:
        ca = {i.importer for (_, t), imps in edges.items() if t == c for i in imps}
        ce = {i.imported for (s, _), imps in edges.items() if s == c for i in imps}
        result[c] = metrics(len(ca), len(ce), sum(files[c]), len(files[c]), threshold)
    return result


def _unused(edges: dict[Pair, list[Import]], present: tuple[str, ...], config: Config):
    """Allowed dependencies no import uses - candidates for tightening the rules (V7)."""
    if config.allowed is None:
        return ()
    return tuple(
        (source, target)
        for source, targets in sorted(config.allowed.items())
        if targets != ALL and source in present
        for target in sorted(targets)
        if (source, target) not in edges
    )


def _zone_problems(measured: dict[str, Metrics], config: Config, table: str) -> list[Problem]:
    rules = config.metrics
    return [
        Problem(
            kind="zone",
            rule=f"{table}.metrics.fail_on_zones",
            components=(component,),
            count=0,
            imports=(),
            hint=_zone_hint(component, m),
        )
        for component, m in measured.items()
        if m.zone in rules.fail_on_zones and component not in rules.ignore
    ]


def _zone_hint(component: str, m: Metrics) -> str:
    numbers = f"I={m.instability}, A={m.abstractness}, D={m.distance}"
    if m.zone == "pain":
        return (
            f"{component} is concrete and depended upon ({numbers}): extract interfaces "
            "others can depend on, or move dependents away from its concrete modules."
        )
    return (
        f"{component} is abstract but nothing depends on it ({numbers}): remove unused "
        "abstractions or merge them into the code that implements them."
    )


def _rule_problems(
    edges: Edges, present: tuple[str, ...], config: Config, table: str
) -> list[Problem]:
    forbidden = _forbidden_pairs(config, present)
    allowed = config.allowed
    fails = config.fail_on_violations
    problems: list[Problem] = []
    if allowed is not None:
        for component in present:
            if component not in allowed:
                outgoing = [
                    i for (s, _), imps in edges.internal.items() if s == component for i in imps
                ]
                problems.append(_undeclared(component, outgoing, table, fails))
    for (source, target), imports in edges.internal.items():
        if (source, target) in forbidden:
            origin = forbidden[(source, target)].origin
            problems.append(_forbidden(source, target, imports, f"{table}.{origin}", fails))
        elif allowed is not None and source in allowed and not _may(allowed, source, target):
            problems.append(_not_allowed(source, target, imports, allowed, table, fails))
    problems += _outside_problems(edges.outside, forbidden, config, table)
    problems += _undeclared_externals_problems(edges.outside, config, table)
    return sorted(problems, key=lambda p: (p.components, p.kind))


def _forbidden_pairs(config: Config, present: tuple[str, ...]) -> dict[Pair, Forbidden]:
    """`forbidden` rules keyed by pair, with `from = "*"` expanded to every component."""
    pairs: dict[Pair, Forbidden] = {}
    for f in config.all_forbidden():
        sources = present if f.source == ALL_COMPONENTS else (f.source,)
        for source in sources:
            pairs.setdefault((source, f.target), f)
    return pairs


def _outside_problems(
    outside: dict[Pair, list[Import]], forbidden: dict[Pair, Forbidden], config: Config, table: str
) -> list[Problem]:
    externals = config.externals
    fails = config.fail_on_violations
    problems = []
    for (source, target), imports in outside.items():
        if (source, target) in forbidden:
            origin = forbidden[(source, target)].origin
            problems.append(_forbidden(source, target, imports, f"{table}.{origin}", fails))
        elif externals is not None and source in externals and not _may(externals, source, target):
            problems.append(_outside(source, target, imports, externals, table, fails))
    return problems


def _outside(
    source: str, target: str, imports: list[Import], externals: dict, table: str, fails: bool
) -> Problem:
    may = ", ".join(externals[source]) or "nothing outside the project"
    return Problem(
        kind="outside",
        rule=f"{table}.externals.{source}",
        components=(source, target),
        count=len(imports),
        imports=tuple(imports),
        hint=(
            f"{source} may reach {may}. Declare {target} in [{table}.externals].{source}, "
            f"or define the interface {source} needs inside {source} and let another "
            "component depend on the package."
        ),
        fails=fails,
    )


def _undeclared_externals_problems(
    outside: dict[Pair, list[Import]], config: Config, table: str
) -> list[Problem]:
    """Closed mode (`externals_undeclared = "error"`): every component that reaches
    outside the project must be a key of `[table.externals]`, exactly as `allowed`
    requires a component to be declared (issue #5)."""
    if config.externals_undeclared != "error":
        return []
    externals = config.externals or {}
    fails = config.fail_on_violations
    by_component: dict[str, list[Import]] = defaultdict(list)
    for (source, _target), imports in outside.items():
        if source not in externals:
            by_component[source] += imports
    return [
        _undeclared_externals(component, imports, table, fails)
        for component, imports in sorted(by_component.items())
    ]


def _undeclared_externals(
    component: str, imports: list[Import], table: str, fails: bool
) -> Problem:
    """`imports` arrives concatenated across every outside target `component` reaches,
    grouped by (source, target) pair sorted alphabetically by target - not by line -
    so it is re-sorted by file and line here for a reading order that matches the
    file, not the alphabet (N1, Fix 6, review)."""
    ordered = sorted(imports, key=lambda i: (i.file, i.line))
    return Problem(
        kind="undeclared_externals",
        rule=f"{table}.externals",
        components=(component,),
        count=len(ordered),
        imports=tuple(ordered),
        hint=(
            f"{component} reaches outside the project but is not declared in "
            f"[{table}.externals]; add {component} = [] there, or list what it may "
            "import if some of it is legitimate."
        ),
        fails=fails,
    )


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


def _forbidden(source: str, target: str, imports: list[Import], rule: str, fails: bool) -> Problem:
    return Problem(
        kind="forbidden",
        rule=rule,
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


def _reject_outside_sources(model: Model, config: Config) -> None:
    """`from` always names a component: nothing we can see imports out of a package."""
    external = {n.id for n in model.nodes if n.kind == "external"}
    for f in config.all_forbidden():
        if f.source in external:
            raise ConfigError(
                f"[{config.table}.{f.origin}] has from = {f.source!r}, a package outside "
                "the project; `from` must name a component"
            )


def _partial_externals_warnings(edges: Edges, config: Config, table: str) -> list[Notice]:
    """`[table.externals]` reads as a fence but is an opt-in allow-list: a component
    that is not a key is unconstrained. Flag this only for a package the table already
    names - so a repo with thirty third-party dependencies and two constrained
    components gets at most two lines, not thirty (issue #5). A component that is a
    key but omits the package is already constrained and fails properly; it is not
    this notice's business.

    One notice per *package*, not per (key, package) pair: two keys granting the same
    package used to repeat the same unconstrained-importer list verbatim, once per
    key. Repetitive warnings train people to ignore warnings, which is the failure
    this milestone exists to fix - so the notice names every granting key once.

    Silent under `externals_undeclared = "error"`: closed mode already fails every
    unconstrained importer this notice would name, as `undeclared_externals`, and the
    notice's own last sentence ("only components named in [table.externals] are
    checked") is exactly what closed mode stops being true. The table cannot be
    partial when it is closed.
    """
    if config.externals_undeclared == "error":
        return []
    externals = config.externals or {}
    importers = _importers_by_package(edges)
    warnings = []
    for package in _named_packages(externals):
        unconstrained = sorted(c for c in importers.get(package, ()) if c not in externals)
        if not unconstrained:
            continue
        keys = sorted(
            key for key, targets in externals.items() if targets != ALL and package in targets
        )
        warnings.append(_partial_externals(table, keys, package, unconstrained))
    return warnings


def _named_packages(externals: dict[str, tuple[str, ...] | str]) -> list[str]:
    """Every package a value in `externals` names, sorted - never `ALL`, which names
    no package in particular."""
    return sorted({name for targets in externals.values() if targets != ALL for name in targets})


def _importers_by_package(edges: Edges) -> dict[str, list[str]]:
    """Every package outside the project, mapped to the components that import it -
    `component_edges`' `outside` bucket, regrouped by target instead of by pair."""
    by_package: dict[str, list[str]] = defaultdict(list)
    for source, target in edges.outside:
        by_package[target].append(source)
    return by_package


def _and_join(items: list[str]) -> str:
    """`["a"]` -> "a", `["a", "b"]` -> "a and b", `["a", "b", "c"]` -> "a, b, and c" -
    an Oxford "and" so a serial comma before a trailing "but" cannot be misread as one
    more item in the list (Fix 9, review)."""
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _partial_externals(
    table: str, keys: list[str], package: str, unconstrained: list[str]
) -> Notice:
    grantors = _and_join(keys)
    who = _and_join(unconstrained)
    plural = len(unconstrained) > 1
    verb, be = ("also import", "are") if plural else ("also imports", "is")
    return Notice(
        "partial_externals",
        f"[{table}.externals] allows {package} for {grantors}, but {who} {verb} it and {be} "
        f"unconstrained; only components named in [{table}.externals] are checked",
    )


def _warnings(
    model: Model,
    config: Config,
    components: ComponentMap,
    present: tuple[str, ...],
    edges: Edges,
    table: str,
    in_workspace: bool = False,
) -> list[Notice]:
    external = {n.id for n in model.nodes if n.kind == "external"}
    known_components = set(present)
    # `allowed` is consulted only for `edges.internal` pairs (`_rule_problems`), where
    # both sides are components: an outside name or "*" there is a rule that can never
    # fire, so it must not be treated as known the way `forbidden` legitimately is.
    known = known_components | external | {ALL_COMPONENTS}
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
            if name not in known_components:
                warnings.append(
                    Notice(
                        "unknown_component",
                        f"[{table}.allowed.{component}] names {name!r}, which has no modules",
                    )
                )
    for component, targets in sorted((config.externals or {}).items()):
        if component not in present:
            warnings.append(
                Notice(
                    "unknown_component",
                    f"[{table}.externals.{component}] names {component!r}, which has no modules",
                )
            )
        for name in [] if targets == ALL else targets:
            if name not in external:
                warnings.append(
                    Notice(
                        "unknown_component",
                        f"[{table}.externals.{component}] names {name!r}, which nothing imports",
                    )
                )
    warnings += _partial_externals_warnings(edges, config, table)
    for f in config.all_forbidden():
        # A literal `forbidden` rule whose *target* is absent from the graph is the ban
        # working: the name is missing precisely because nobody imports it (issue #5).
        # Warning there trains people to ignore warnings. The *source* is different - a
        # `from` that names nothing can never fire, so it is still a typo. Rules derived
        # from `layers`/`independent` name components on both sides, so both still warn.
        checked = (f.source,) if f.origin == "forbidden" else (f.source, f.target)
        for name in checked:
            if name not in known:
                warnings.append(
                    Notice(
                        "unknown_component",
                        f"[{table}.{f.origin}] names {name!r}, which has no modules",
                    )
                )
    if config.public is not None and not in_workspace:
        warnings.append(
            Notice(
                "public_ignored",
                f"[{table}] public only constrains imports from other packages in a "
                "workspace; it has no effect here",
            )
        )
    for index, e in enumerate(config.exceptions):
        if index not in edges.exceptions_used:
            warnings.append(
                Notice(
                    "unused_exception",
                    f"exception {e.importer} -> {e.imported} matches no import; remove it",
                )
            )
    for w in model.warnings:
        target = f" ({w.target})" if w.target else ""
        label = WARNING_LABELS.get(w.kind, w.kind.replace("_", " "))
        warnings.append(
            Notice(w.kind, f"{w.file}:{w.line} {w.text}: {label}{target} is not checked")
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
