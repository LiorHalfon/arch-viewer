"""Aggregate a model into the view for one root (requirements A6-A10)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from archview.model.cycles import components, find_cycles
from archview.model.graph import Import, Kind, Model, Node
from archview.model.layers import assign_layers
from archview.model.metrics import DEFAULT_THRESHOLD, metrics
from archview.model.names import ancestors, within


@dataclass(frozen=True, slots=True)
class ViewNode:
    """One box in the diagram: a direct child of the root, or an external package."""

    id: str
    name: str
    kind: Kind
    module_count: int
    layer: int
    in_cycle: bool
    fan_in: int
    fan_out: int
    abstract: bool = False
    abstractness: float = 0.0
    instability: float | None = None
    distance: float | None = None
    zone: str = "isolated"
    parent: str | None = None
    """The box this one is drawn inside, for a nested view. None for a top-level box."""


@dataclass(frozen=True, slots=True)
class ViewEdge:
    """All imports from one child of the root to another, counted.

    `abstract`: every import lands on an abstract module (UML realisation arrow).
    `type_checking`: every import is for type checkers only.
    """

    source: str
    target: str
    count: int
    in_cycle: bool
    imports: tuple[Import, ...] = field(default_factory=tuple)
    abstract: bool = False
    type_checking: bool = False


@dataclass(frozen=True, slots=True)
class View:
    root: str
    nodes: tuple[ViewNode, ...]
    edges: tuple[ViewEdge, ...]
    cycles: tuple[tuple[str, ...], ...]


def _owner(module: str, children: frozenset[str], sep: str) -> str | None:
    """The child of the root that `module` belongs to, if any."""
    return next((c for c in ancestors(module, sep) if c in children), None)


def _in_subtree(node_id: str, model: Model) -> list[Node]:
    return [n for n in model.nodes if within(n.id, node_id, model.separator)]


def _grouped_imports(model: Model, children: frozenset[str]) -> dict[tuple[str, str], list[Import]]:
    """Every import in the root's subtree, rolled up to the pair of children it connects."""
    grouped: dict[tuple[str, str], list[Import]] = defaultdict(list)
    for imp in model.imports:
        source = _owner(imp.importer, children, model.separator)
        target = _owner(imp.imported, children, model.separator)
        if source is not None and target is not None and source != target:
            grouped[(source, target)].append(imp)
    return grouped


def _externals(model: Model, root: str) -> set[str]:
    """External packages imported from inside `root`."""
    kinds = {n.id: n.kind for n in model.nodes}
    inside = frozenset({root})
    return {
        imp.imported
        for imp in model.imports
        if kinds.get(imp.imported) == "external" and _owner(imp.importer, inside, model.separator)
    }


def build_view(
    model: Model,
    root: str,
    externals: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
    keep: frozenset[str] = frozenset(),
) -> View:
    """The children of `root` and the counted edges between them; with `externals`,
    the third-party packages the subtree imports become boxes too, and `keep` names
    outside packages to show even without `externals` (a rule broken by reaching one)."""
    by_id = {n.id: n for n in model.nodes}
    internal = frozenset(n.id for n in model.nodes if n.parent == root and n.kind != "external")
    found = _externals(model, root)
    shown = found if externals else (found & keep)
    children = internal | frozenset(shown)
    grouped = _grouped_imports(model, children)
    counts = {pair: len(imports) for pair, imports in grouped.items()}

    component = components(children, counts)
    layer = assign_layers(children, counts)
    cycles = find_cycles(children, counts)
    cyclic = {name for cycle in cycles for name in cycle}
    abstract_ids = {n.id for n in model.nodes if n.abstract}

    nodes = tuple(
        _node(model, by_id, child, root, grouped, layer[child], child in cyclic, threshold)
        for child in sorted(children, key=lambda c: (by_id[c].kind == "external", c))
    )
    edges = tuple(
        ViewEdge(
            source=s,
            target=t,
            count=len(imports),
            in_cycle=component[s] == component[t],
            imports=tuple(imports),
            abstract=all(i.imported in abstract_ids for i in imports),
            type_checking=all(i.type_checking for i in imports),
        )
        for (s, t), imports in sorted(grouped.items())
    )
    return View(root=root, nodes=nodes, edges=edges, cycles=cycles)


def _node(
    model: Model,
    by_id: dict[str, Node],
    node_id: str,
    root: str,
    grouped: dict[tuple[str, str], list[Import]],
    layer: int,
    in_cycle: bool,
    threshold: float,
) -> ViewNode:
    node = by_id[node_id]
    files = [n for n in _in_subtree(node.id, model) if n.file is not None]
    abstract = sum(1 for n in files if n.abstract)
    incoming = [i for (_, t), imps in grouped.items() if t == node.id for i in imps]
    outgoing = [i for (s, t), imps in grouped.items() if s == node.id for i in imps]
    internal_out = [
        i for i in outgoing if i.imported in by_id and by_id[i.imported].kind != "external"
    ]
    m = metrics(
        ca=len({i.importer for i in incoming}),
        ce=len({i.imported for i in internal_out}),
        abstract=abstract,
        modules=len(files),
        threshold=threshold,
    )
    if node.kind == "external":
        return ViewNode(
            node.id, node.id, "external", 0, layer, in_cycle, len(incoming), 0, zone="external"
        )
    name = node.id[len(root) + 1 :]
    return ViewNode(
        id=node.id,
        name=name,
        kind=node.kind,
        module_count=len(files),
        layer=layer,
        in_cycle=in_cycle,
        fan_in=len(incoming),
        fan_out=len(outgoing),
        abstract=bool(files) and abstract == len(files),
        abstractness=m.abstractness,
        instability=m.instability,
        distance=m.distance,
        zone=m.zone,
    )


def tangled_packages(model: Model) -> frozenset[str]:
    """Packages that have a cycle among their children, or anywhere further down (V6)."""
    with_cycles = [
        n.id for n in model.nodes if n.kind == "package" and build_view(model, n.id).cycles
    ]
    tangled: set[str] = set()
    for package in with_cycles:
        tangled.update(ancestors(package, model.separator))
    return frozenset(tangled)
