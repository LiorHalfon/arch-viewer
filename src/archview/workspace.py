"""Open a workspace: several packages, each with its own project, joined by name.

A cross-package import already shows up as an outside edge in each package's own
model (M7's outside edges). This module does the one new thing workspace mode needs:
attribute an outside name to the sibling package it belongs to, so a later checker or
view can treat it as a workspace edge rather than an ordinary third-party one.

The structure is a federation, not a merged model: each package keeps its own
`Project`, language and separator. Merging would collide Python's `.` ids with
TypeScript's `/` ids, since `Model` carries a single `project` string and a single
`separator` (see docs/superpowers/specs/2026-09-20-workspace-design.md).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from archview.model.cycles import components, find_cycles
from archview.model.graph import Import, Model
from archview.model.layers import assign_layers
from archview.model.metrics import DEFAULT_THRESHOLD
from archview.model.query import Cycle, _cycle
from archview.model.view import View, ViewEdge, ViewNode
from archview.project import Project, open_project, project_report
from archview.rules.baseline import apply_baseline, load_baseline
from archview.rules.check import (
    Edges,
    Pair,
    Report,
    WorkspaceReport,
    _cycle_problems,
    _exemption,
    _rule_problems,
    checked_imports,
    component_edges,
    component_map,
)
from archview.rules.config import (
    RULES_FILE,
    Config,
    ConfigError,
    WorkspaceRules,
    find_config,
    load_config,
)


@dataclass(frozen=True, slots=True)
class Package:
    """One workspace member: its own project, plus how siblings may refer to it."""

    name: str
    path: Path
    aliases: frozenset[str]
    project: Project
    has_rules: bool


@dataclass(frozen=True, slots=True)
class Workspace:
    name: str
    root: Path
    packages: tuple[Package, ...]
    config: Config


def open_workspace(
    root: Path, config_path: Path | None = None, config: Config | None = None
) -> Workspace:
    """Open every package the `[archview.workspace]` table at `root` lists. `config`,
    when given, is already parsed - a caller that had to load it anyway (`cli._workspace_root`)
    passes it through rather than having this function parse the rules file again."""
    root = Path(root).expanduser().resolve()
    path = config_path or find_config(root)
    if config is None:
        config = load_config(path) if path else Config()
    if config.workspace is None:
        raise ConfigError(f"no [archview.workspace] table in {path or root / RULES_FILE}")
    base = path.parent if path else root
    packages = _open_packages(config.workspace.packages, base)
    return Workspace(config.package or root.name, root, packages, config)


def _open_packages(entries: tuple[str, ...], base: Path) -> tuple[Package, ...]:
    """Open each listed package path, sorted by name; reject a name collision."""
    by_name: dict[str, Package] = {}
    for entry in entries:
        package = _open_package(base / entry)
        clash = by_name.get(package.name)
        if clash is not None:
            raise ConfigError(
                f"two workspace packages are both named {package.name!r}: "
                f"{clash.path} and {package.path}"
            )
        by_name[package.name] = package
    return tuple(sorted(by_name.values(), key=lambda p: p.name))


def _open_package(path: Path) -> Package:
    project = open_project(path)
    return Package(
        name=project.package,
        path=project.repo,
        aliases=aliases(project),
        project=project,
        has_rules=project.config_path is not None,
    )


def aliases(project: Project) -> frozenset[str]:
    """How siblings may refer to `project`: its top-level name, plus, for
    TypeScript, the name(s) its `package.json` gives it."""
    names = {project.package}
    if project.model.language == "typescript":
        names |= _npm_names(project.repo)
    return frozenset(names)


def _npm_names(repo: Path) -> set[str]:
    """The `package.json` `name`, with and without an `@scope/` prefix; a missing
    or malformed file is ignored rather than failing the run."""
    try:
        data = json.loads((repo / "package.json").read_text())
    except (OSError, ValueError):
        return set()
    name = data.get("name") if isinstance(data, dict) else None
    return {name, name.split("/", 1)[-1]} if isinstance(name, str) and name else set()


def _owner(outside: str, importer: Package, packages: tuple[Package, ...]) -> str | None:
    """Which sibling `outside` names, from `importer`'s point of view."""
    if outside.startswith("../"):
        return _owner_by_path(outside, importer, packages)
    return next(
        (p.name for p in sorted(packages, key=lambda p: p.name) if outside in p.aliases), None
    )


def _owner_by_path(outside: str, importer: Package, packages: tuple[Package, ...]) -> str | None:
    """A `../`-relative resolution belongs to whichever package's directory contains it."""
    target = (importer.path / outside).resolve()
    return next(
        (p.name for p in sorted(packages, key=lambda p: p.name) if target.is_relative_to(p.path)),
        None,
    )


def cross_edges(ws: Workspace) -> dict[Pair, list[Import]]:
    """Every package's outside edges (M7) whose target is a sibling, grouped by
    (source package, target package) and sorted.

    A workspace exception exempts a cross-package import the same way a package's own
    `[archview.exceptions]` exempt an internal one - `_exemption` is the same helper.
    """
    exceptions = ws.config.workspace.exceptions
    cross: dict[Pair, list[Import]] = defaultdict(list)
    for package in ws.packages:
        for outside, imports in _outside_imports(package).items():
            sibling = _owner(outside, package, ws.packages)
            if sibling is None or sibling == package.name:
                continue
            sep = package.project.model.separator
            surviving = [imp for imp in imports if _exemption(imp, exceptions, sep) is None]
            if surviving:
                cross[(package.name, sibling)] += surviving
    return {
        pair: sorted(imps, key=lambda i: (i.file, i.line)) for pair, imps in sorted(cross.items())
    }


def _outside_imports(package: Package) -> dict[str, list[Import]]:
    """A package's own outside edges, keyed by the outside name alone.

    `checked_imports` drops TYPE_CHECKING-only imports first, exactly as `check()`
    does for a package's own rules (A4): a workspace must not fire on the same
    pattern that is silently ignored inside a single package by default.
    """
    project = package.project
    model = checked_imports(project.model, project.config)
    components = component_map(project.config, model.project, model.separator)
    edges = component_edges(model, components, project.config)
    by_outside: dict[str, list[Import]] = defaultdict(list)
    for (_, outside), imports in edges.outside.items():
        by_outside[outside] += imports
    return by_outside


def check_workspace(ws: Workspace) -> WorkspaceReport:
    """Each package's own check, where it has rules, plus the rules between them."""
    packages = tuple((p.name, project_report(p.project)) for p in ws.packages if p.has_rules)
    return WorkspaceReport(ws.name, packages, _check_between(ws))


def _check_between(ws: Workspace) -> Report:
    rules = ws.config.workspace
    present = tuple(p.name for p in ws.packages)
    edges = Edges(internal=cross_edges(ws), outside={}, exceptions_used=set())
    config = _between_config(rules)
    problems = [
        *_rule_problems(edges, present, config, config.table),
        *_cycle_problems(edges.internal, present, config, config.table),
    ]
    report = Report(ws.name, present, tuple(problems), ())
    if rules.baseline:
        report = _apply_workspace_baseline(report, ws.root, rules.baseline)
    return report


def _between_config(rules: WorkspaceRules) -> Config:
    """A `Config` carrying just what `_rule_problems`/`_cycle_problems` need."""
    return Config(
        table="archview.workspace",
        allowed=rules.allowed,
        forbidden=rules.forbidden,
        fail_on_violations=rules.fail_on_violations,
        fail_on_cycles=rules.fail_on_cycles,
    )


def _apply_workspace_baseline(report: Report, root: Path, name: str) -> Report:
    path = root / name
    if not path.is_file():
        raise ConfigError(f"baseline {path} does not exist; `archview check --update-baseline`")
    return apply_baseline(report, load_baseline(path), path.name)


def workspace_view(ws: Workspace, threshold: float = DEFAULT_THRESHOLD) -> View:
    """The workspace's top level: each package a node, cross-package imports the
    edges between them. Mirrors `build_view`'s shape, and returns the same `View`, so
    `to_dot`, `to_mermaid`, `view_to_dict` and the violations overlay work on it
    unchanged.

    A package's abstractness and zone are not computed across packages - aggregating
    Martin metrics across languages is out of scope - so every node keeps `zone`
    "isolated" and the metric fields at their defaults, exactly as an external node
    does today. `threshold` is accepted only for signature parity with `build_view`;
    it plays no part here.
    """
    by_name = {p.name: p for p in ws.packages}
    children = frozenset(by_name)
    grouped = cross_edges(ws)
    counts = {pair: len(imports) for pair, imports in grouped.items()}

    component = components(children, counts)
    layer = assign_layers(children, counts)
    cycles = find_cycles(children, counts)
    cyclic = {name for cycle in cycles for name in cycle}

    nodes = tuple(
        _package_node(by_name[name], grouped, layer[name], name in cyclic)
        for name in sorted(children)
    )
    edges = tuple(
        ViewEdge(
            source=s,
            target=t,
            count=len(imports),
            in_cycle=component[s] == component[t],
            imports=tuple(imports),
            type_checking=all(i.type_checking for i in imports),
        )
        for (s, t), imports in sorted(grouped.items())
    )
    return View(root=ws.name, nodes=nodes, edges=edges, cycles=cycles)


def _package_node(
    package: Package, grouped: dict[Pair, list[Import]], layer: int, in_cycle: bool
) -> ViewNode:
    incoming = [i for (_, t), imps in grouped.items() if t == package.name for i in imps]
    outgoing = [i for (s, t), imps in grouped.items() if s == package.name for i in imps]
    return ViewNode(
        id=package.name,
        name=package.name,
        kind="package",
        module_count=_module_count(package.project.model),
        layer=layer,
        in_cycle=in_cycle,
        fan_in=len(incoming),
        fan_out=len(outgoing),
    )


def _module_count(model: Model) -> int:
    return sum(1 for n in model.nodes if n.file is not None)


def workspace_cycles(ws: Workspace) -> tuple[Cycle, ...]:
    """The cycles among the packages themselves, with a path each - the workspace's
    top-level analogue of `archview.model.query.all_cycles` for a single level."""
    view = workspace_view(ws)
    edges = {(e.source, e.target): e for e in view.edges}
    return tuple(_cycle(ws.name, members, edges) for members in view.cycles)
