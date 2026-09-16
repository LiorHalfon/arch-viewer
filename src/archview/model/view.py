"""Aggregate a model into the view for one root (requirement A6)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from archview.model.cycles import components, find_cycles
from archview.model.graph import Import, Kind, Model
from archview.model.layers import assign_layers


@dataclass(frozen=True, slots=True)
class ViewNode:
    """One box in the diagram: a direct child of the root."""

    id: str
    name: str
    kind: Kind
    module_count: int
    layer: int
    in_cycle: bool
    fan_in: int
    fan_out: int


@dataclass(frozen=True, slots=True)
class ViewEdge:
    """All imports from one child of the root to another, counted."""

    source: str
    target: str
    count: int
    in_cycle: bool
    imports: tuple[Import, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class View:
    root: str
    nodes: tuple[ViewNode, ...]
    edges: tuple[ViewEdge, ...]
    cycles: tuple[tuple[str, ...], ...]


def _owner(module: str, children: frozenset[str]) -> str | None:
    """The child of the root that `module` belongs to, if any."""
    parts = module.split(".")
    for i in range(len(parts)):
        candidate = ".".join(parts[: i + 1])
        if candidate in children:
            return candidate
    return None


def _module_count(model: Model, node_id: str) -> int:
    """How many source files live in this subtree, the node itself included."""
    prefix = node_id + "."
    return sum(
        1
        for n in model.nodes
        if n.file is not None and (n.id == node_id or n.id.startswith(prefix))
    )


def _grouped_imports(model: Model, children: frozenset[str]) -> dict[tuple[str, str], list[Import]]:
    """Every import in the root's subtree, rolled up to the pair of children it connects."""
    grouped: dict[tuple[str, str], list[Import]] = defaultdict(list)
    for imp in model.imports:
        source = _owner(imp.importer, children)
        target = _owner(imp.imported, children)
        if source is not None and target is not None and source != target:
            grouped[(source, target)].append(imp)
    return grouped


def build_view(model: Model, root: str) -> View:
    by_id = {n.id: n for n in model.nodes}
    children = frozenset(n.id for n in model.nodes if n.parent == root)
    grouped = _grouped_imports(model, children)
    counts = {pair: len(imports) for pair, imports in grouped.items()}

    component = components(children, counts)
    layer = assign_layers(children, counts)
    cycles = find_cycles(children, counts)
    cyclic = {name for cycle in cycles for name in cycle}

    nodes = tuple(
        ViewNode(
            id=child,
            name=child[len(root) + 1 :],
            kind=by_id[child].kind,
            module_count=_module_count(model, child),
            layer=layer[child],
            in_cycle=child in cyclic,
            fan_in=sum(c for (_, t), c in counts.items() if t == child),
            fan_out=sum(c for (s, _), c in counts.items() if s == child),
        )
        for child in sorted(children)
    )
    edges = tuple(
        ViewEdge(
            source=s,
            target=t,
            count=len(imports),
            in_cycle=component[s] == component[t],
            imports=tuple(imports),
        )
        for (s, t), imports in sorted(grouped.items())
    )
    return View(root=root, nodes=nodes, edges=edges, cycles=cycles)


def tangled_packages(model: Model) -> frozenset[str]:
    """Packages that have a cycle among their children, or anywhere further down (V6)."""
    with_cycles = [
        n.id for n in model.nodes if n.kind == "package" and build_view(model, n.id).cycles
    ]
    tangled: set[str] = set()
    for package in with_cycles:
        parts = package.split(".")
        tangled.update(".".join(parts[: i + 1]) for i in range(len(parts)))
    return frozenset(tangled)
