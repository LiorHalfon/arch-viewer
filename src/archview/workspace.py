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
from dataclasses import dataclass, replace
from pathlib import Path

from archview.extract.siblings import resolve_targets
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
    Notice,
    Pair,
    Problem,
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
    ALL,
    RULES_FILE,
    Config,
    ConfigError,
    WorkspaceRules,
    _read_toml,
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
        raise ConfigError(f"no [{config.table}.workspace] table in {path or root / RULES_FILE}")
    # Guards a synthetic `config` passed in with a workspace table but no file behind
    # it (e.g. built in a test): there is no raw TOML to re-read an inert key from, so
    # the check below cannot run.
    if path is not None:
        _reject_inert_root_keys(config, path)
    base = path.parent if path else root
    packages = _open_packages(config.workspace.packages, base)
    return Workspace(config.package or root.name, root, packages, config)


# Keys `Config` happily parses at a workspace root's bare `[archview]` table but never
# consults there: each member is checked with its own `Config` (`type_checking_imports`,
# issue #8), and `between` is checked with a `Config` `_between_config` builds fresh,
# which does not carry `externals_undeclared` either (review). Both used to read as
# applied when they were not.
_INERT_ROOT_KEYS = frozenset({"type_checking_imports", "externals_undeclared"})


def _reject_inert_root_keys(config: Config, path: Path) -> None:
    """A key in `_INERT_ROOT_KEYS`, set at a workspace root, can never take effect
    there. Detecting this needs the raw table, not the parsed `Config`: a key's own
    default (`type_checking_imports`'s "include", `externals_undeclared`'s "allow")
    does not tell a set value apart from an unset one.
    """
    present = sorted(_INERT_ROOT_KEYS & _root_table(path, config.table).keys())
    if present:
        key = present[0]
        raise ConfigError(
            f"[{config.table}] {key} has no effect at a workspace root - each "
            "package is checked with its own config. Set it in the package's own "
            "rules file instead."
        )


def _root_table(path: Path, table: str) -> dict:
    """The raw table `table` names (e.g. "archview" or "tool.archview") in `path`,
    parsed but not validated - so a rejected key can still be seen before `Config`
    would ever carry it."""
    data = _read_toml(path)
    for key in table.split("."):
        data = data.get(key) if isinstance(data, dict) else None
        if not isinstance(data, dict):
            return {}
    return data


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


@dataclass(frozen=True, slots=True)
class CrossEdges:
    """One pass over the workspace, three views of the same imports.

    `by_package` is what M8 checked: (source package, target package). `by_component`
    narrows the target to the component actually reached - (source package,
    "target.component") - which is what a public surface is checked against (issue #4).
    `unplaced` holds the imports whose component could not be determined; they are still
    checked at package level and reported, never silently passed.
    """

    by_package: dict[Pair, list[Import]]
    by_component: dict[Pair, list[Import]]
    unplaced: tuple[Import, ...]


def cross_edges(ws: Workspace) -> CrossEdges:
    """Every package's outside edges (M7) whose target is a sibling, attributed.

    A workspace exception exempts a cross-package import the same way a package's own
    `[archview.exceptions]` exempt an internal one - `_exemption` is the same helper.
    """
    exceptions = ws.config.workspace.exceptions
    targets = resolve_targets(_python_roots(ws))
    by_package: dict[Pair, list[Import]] = defaultdict(list)
    by_component: dict[Pair, list[Import]] = defaultdict(list)
    unplaced: list[Import] = []
    for package in ws.packages:
        for outside, imports in _outside_imports(package).items():
            sibling = _owner(outside, package, ws.packages)
            if sibling is None or sibling == package.name:
                continue
            sep = package.project.model.separator
            surviving = [imp for imp in imports if _exemption(imp, exceptions, sep) is None]
            if not surviving:
                continue
            by_package[(package.name, sibling)] += surviving
            for imp in surviving:
                component = _component_of(imp, outside, package, sibling, ws, targets)
                if component is None:
                    unplaced.append(imp)
                else:
                    by_component[(package.name, component)].append(imp)
    return CrossEdges(
        _sorted_edges(by_package),
        _sorted_edges(by_component),
        tuple(sorted(unplaced, key=lambda i: (i.file, i.line))),
    )


def _sorted_edges(edges: dict[Pair, list[Import]]) -> dict[Pair, list[Import]]:
    return {
        pair: sorted(imps, key=lambda i: (i.file, i.line)) for pair, imps in sorted(edges.items())
    }


def _python_roots(ws: Workspace) -> dict[str, Path]:
    """The source roots of the workspace's Python packages, for `resolve_targets`."""
    return {
        p.name: p.project.source_root for p in ws.packages if p.project.model.language == "python"
    }


def _component_of(
    imp: Import,
    outside: str,
    importer: Package,
    sibling: str,
    ws: Workspace,
    targets: dict[tuple[str, int], str],
) -> str | None:
    """`sibling.component` for the part of `sibling` this import reaches, or None.

    Python comes from the workspace resolution pass, the only thing that can see past
    grimp's squashing. TypeScript carries `Import.resolved`, the path tsc resolved
    before the extractor squashed the target to a package name - so every TypeScript
    form that tsc can resolve places, and one it cannot is reported rather than
    guessed at (ADR 0013).
    """
    module = targets.get((imp.importer, imp.line))
    if module is not None:
        return _qualified(module, sibling, ".")
    if imp.resolved is not None:
        return _qualified_by_path(imp.resolved, importer, sibling, ws)
    return None


def _qualified(module: str, sibling: str, sep: str) -> str:
    """`core.model.Thing` -> `core.model`; the package root itself -> `core`."""
    rest = module[len(sibling) :].lstrip(sep)
    return f"{sibling}{sep}{rest.split(sep)[0]}" if rest else sibling


def _qualified_by_path(resolved: str, importer: Package, sibling: str, ws: Workspace) -> str | None:
    """`resolved` is a path relative to the *importing* package's repo.

    The component comes from the owner's own model rather than from path arithmetic:
    a TypeScript node id drops the source root (`src/index.ts` -> `core/index.ts`), so
    only the extractor that built the ids can map a file back to one.
    """
    owner = _package_by_name(ws, sibling)
    try:
        inside = (importer.path / resolved).resolve().relative_to(owner.path.resolve())
    except ValueError:
        return None
    wanted = inside.as_posix()
    node = next((n for n in owner.project.model.nodes if n.file == wanted), None)
    if node is None:
        return None
    return _qualified(node.id, sibling, owner.project.model.separator)


def _package_by_name(ws: Workspace, name: str) -> Package:
    return next(p for p in ws.packages if p.name == name)


def _outside_imports(package: Package) -> dict[str, list[Import]]:
    """A package's own outside edges, keyed by the outside name alone.

    `checked_imports` drops TYPE_CHECKING-only imports first, exactly as `check()`
    does for a package's own rules (A4): a workspace must not fire on the same
    pattern that is silently ignored inside a single package by default.

    The package's own `[[archview.exceptions]]` are stripped before `component_edges`
    sees them: M7 widened exceptions to exempt outside edges too, so a package's own
    exception would otherwise exempt a cross-package import before `cross_edges` ever
    saw it - the root rules file, via `[[archview.workspace.exceptions]]`, is the only
    authority for what crosses a package line. The package's own `check()` still
    applies its own exceptions to its own `[archview.externals]` rules; only this
    workspace-attribution pass ignores them.
    """
    project = package.project
    model = checked_imports(project.model, project.config)
    components = component_map(project.config, model.project, model.separator)
    edges = component_edges(model, components, replace(project.config, exceptions=()))
    by_outside: dict[str, list[Import]] = defaultdict(list)
    for (_, outside), imports in edges.outside.items():
        by_outside[outside] += imports
    return by_outside


def check_workspace(ws: Workspace) -> WorkspaceReport:
    """Each package's own check, where it has rules, plus the rules between them."""
    packages = tuple(
        (p.name, project_report(p.project, in_workspace=True)) for p in ws.packages if p.has_rules
    )
    return WorkspaceReport(ws.name, packages, _check_between(ws))


def _check_between(ws: Workspace) -> Report:
    rules = ws.config.workspace
    present = tuple(p.name for p in ws.packages)
    cross = cross_edges(ws)
    _reject_unpublished_grants(ws, rules)
    edges = Edges(internal=cross.by_package, outside={}, exceptions_used=set())
    config = _between_config(ws.config, rules)
    problems = [
        *_rule_problems(edges, present, _package_level(config, rules), config.table),
        *_cycle_problems(edges.internal, present, config, config.table),
        *_component_problems(cross.by_component, ws, rules, config),
    ]
    ordered = tuple(sorted(problems, key=lambda p: (p.components, p.kind)))
    report = Report(ws.name, present, ordered, _unplaced_warnings(cross, ws))
    if rules.baseline:
        report = _apply_workspace_baseline(report, ws.root, rules.baseline)
    return report


def _unplaced_warnings(cross: CrossEdges, ws: Workspace) -> tuple[Notice, ...]:
    """An import we could not attribute to a component is named, never passed over.

    It still counts at package level; what is missing is only the public-surface
    check, and silently skipping that is exactly the "looks protected but is not"
    failure this tool exists to prevent.
    """
    owner = {imp: name for (_, name), imps in cross.by_package.items() for imp in imps}
    return tuple(
        Notice(
            "unplaced_import",
            f"{imp.file}:{imp.line} {imp.text.strip()}: could not tell which component of "
            f"{owner.get(imp, 'the sibling')} this reaches, so its public surface was not checked",
        )
        for imp in sorted(cross.unplaced, key=lambda i: (i.file, i.line))
    )


def _package(name: str) -> str:
    """`core.ports` -> `core`; `core` -> `core`."""
    return name.split(".", 1)[0]


def _package_level(config: Config, rules: WorkspaceRules) -> Config:
    """The workspace `allowed` table as the package-level check sees it.

    A qualified grant (`core.ports`) grants the package; the narrowing it expresses is
    enforced separately by `_component_problems`. Without this the package-level check
    would deny the very import the grant exists to permit.
    """
    if not rules.allowed:
        return config
    widened = {
        source: targets if targets == ALL else tuple(sorted({_package(t) for t in targets}))
        for source, targets in rules.allowed.items()
    }
    return replace(config, allowed=widened)


def _published(ws: Workspace, package: str) -> tuple[str, ...] | None:
    """The components `package` offers its siblings, or None when it publishes all."""
    owner = next((p for p in ws.packages if p.name == package), None)
    return owner.project.config.public if owner else None


def _reject_unpublished_grants(ws: Workspace, rules: WorkspaceRules) -> None:
    """A grant naming a component its owner does not publish can never usefully fire.

    `public` would override it, so it is a config error rather than a silent no-op -
    the reasoning ADR 0011 used for a stdlib target. A deliberate one-off belongs in
    `[[archview.workspace.exceptions]]`, which already requires a written reason.
    """
    for source, targets in sorted((rules.allowed or {}).items()):
        for target in () if targets == ALL else targets:
            if "." not in target:
                continue
            published = _published(ws, _package(target))
            if published is not None and target.split(".", 1)[1] not in published:
                package = _package(target)
                may = ", ".join(f"{package}.{n}" for n in published) or "nothing"
                raise ConfigError(
                    f"[{ws.config.table}.workspace.allowed.{source}] names {target!r}, "
                    f"which {package} does not publish. {package} publishes: {may}"
                )


def _component_problems(
    by_component: dict[Pair, list[Import]],
    ws: Workspace,
    rules: WorkspaceRules,
    config: Config,
) -> list[Problem]:
    """An import must satisfy both the owner's `public` and any qualified grant."""
    allowed = rules.allowed or {}
    problems = []
    for (source, target), imports in by_component.items():
        package = _package(target)
        published = _published(ws, package)
        component = target.split(".", 1)[1] if "." in target else None
        if published is not None and (component is None or component not in published):
            owner = next(p for p in ws.packages if p.name == package)
            problems.append(
                _private(source, target, imports, published, owner.project.config.table, config)
            )
            continue
        grants = allowed.get(source)
        qualified = () if grants in (None, ALL) else tuple(t for t in grants if "." in t)
        constrains = qualified and _package(target) in {_package(t) for t in qualified}
        if constrains and target not in qualified:
            problems.append(_not_allowed_component(source, target, imports, qualified, config))
    return problems


def _private(
    source: str,
    target: str,
    imports: list[Import],
    published: tuple[str, ...],
    owner_table: str,
    config: Config,
) -> Problem:
    package = _package(target)
    may = ", ".join(f"{package}.{name}" for name in published) or "nothing"
    return Problem(
        kind="private",
        rule=f"{owner_table}.public",
        components=(source, target),
        count=len(imports),
        imports=tuple(imports),
        hint=(
            f"{target} is not part of {package}'s public surface. {package} publishes: "
            f"{may}. Import one of those, or ask {package}'s owner to publish it."
        ),
        fails=config.fail_on_violations,
    )


def _not_allowed_component(
    source: str, target: str, imports: list[Import], qualified: tuple[str, ...], config: Config
) -> Problem:
    may = ", ".join(qualified)
    return Problem(
        kind="not_allowed",
        rule=f"{config.table}.allowed.{source}",
        components=(source, target),
        count=len(imports),
        imports=tuple(imports),
        hint=(
            f"{source} may import only: {may}. Move the code that needs {target}, go "
            "through an allowed component, or ask a human to change the rule."
        ),
        fails=config.fail_on_violations,
    )


def _between_config(root: Config, rules: WorkspaceRules) -> Config:
    """A `Config` carrying just what `_rule_problems`/`_cycle_problems` need. `table`
    derives from the root rules file's own table, exactly as every other rule name
    does, so a `pyproject.toml`-based workspace ("tool.archview") does not report
    problems against "archview.workspace", an identifier that does not exist there."""
    return Config(
        table=f"{root.table}.workspace",
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
    cross = cross_edges(ws)
    grouped = cross.by_package
    counts = {pair: len(imports) for pair, imports in grouped.items()}

    component = components(children, counts)
    layer = assign_layers(children, counts)
    cycles = find_cycles(children, counts)
    cyclic = {name for cycle in cycles for name in cycle}

    nodes = [
        _package_node(by_name[name], grouped, layer[name], name in cyclic)
        for name in sorted(children)
    ]
    nodes += _public_nodes(ws, layer)
    drawn = _drawn_edges(cross, ws)
    edges = tuple(
        ViewEdge(
            source=s,
            target=t,
            count=len(imports),
            in_cycle=component[s] == component.get(_package(t), s),
            imports=tuple(imports),
            type_checking=all(i.type_checking for i in imports),
        )
        for (s, t), imports in sorted(drawn.items())
    )
    return View(root=ws.name, nodes=tuple(nodes), edges=edges, cycles=cycles)


def _public_nodes(ws: Workspace, layer: dict[str, int]) -> list[ViewNode]:
    """One box per published component, drawn inside its package's box.

    A package that declares no `public` list draws exactly as it did before: one node,
    no children. Chosen over a label on the node because a legal dependency then
    visibly terminates at a port and a violation visibly bypasses one (ADR 0013).
    """
    found = []
    for package in ws.packages:
        published = package.project.config.public
        if published is None:
            continue
        sep = package.project.model.separator
        for name in sorted(published):
            found.append(
                ViewNode(
                    id=f"{package.name}{sep}{name}",
                    name=name,
                    kind="package",
                    module_count=0,
                    layer=layer.get(package.name, 0),
                    in_cycle=False,
                    fan_in=0,
                    fan_out=0,
                    parent=package.name,
                )
            )
    return found


def _drawn_edges(cross: CrossEdges, ws: Workspace) -> dict[Pair, list[Import]]:
    """Cross-package edges, landing on a published component where there is one.

    An import that reaches a private component keeps the package as its target, so it
    is drawn going past the ports rather than through one.
    """
    published = {
        p.name: p.project.config.public for p in ws.packages if p.project.config.public is not None
    }
    component_of = {imp: target for (_, target), imps in cross.by_component.items() for imp in imps}
    drawn: dict[Pair, list[Import]] = defaultdict(list)
    for (source, package), imports in cross.by_package.items():
        for imp in imports:
            target = component_of.get(imp)
            surface = published.get(package)
            reaches = target.split(".", 1)[1] if target and "." in target else None
            landing = target if surface is not None and reaches in surface else package
            drawn[(source, landing)].append(imp)
    return _sorted_edges(drawn)


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
