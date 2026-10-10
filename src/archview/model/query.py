"""The questions an agent asks about the structure (requirement G1, ADR 0009).

`why` explains a dependency, `dependencies`/`dependents` list the neighbours of a
name, `all_cycles` finds the cycles at every level with a real path through each.
Everything works on the model, so exclusions and filters apply as in `check`.
"""

from __future__ import annotations

import difflib
from collections import defaultdict, deque
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise

import networkx as nx

from archview.model.cycles import digraph, find_cycles
from archview.model.graph import Import, Model
from archview.model.names import truncate, within
from archview.model.view import ViewEdge, build_view

Edges = Mapping[tuple[str, str], Sequence[Import]]


class UnknownName(ValueError):
    """The name is not a module, package or external of the model."""


@dataclass(frozen=True, slots=True)
class Why:
    """The direct imports from `source` into `target`; only without them, the shortest chain."""

    source: str
    target: str
    direct: tuple[Import, ...]
    chain: tuple[Import, ...]

    @property
    def found(self) -> bool:
        return bool(self.direct or self.chain)


@dataclass(frozen=True, slots=True)
class Dependency:
    """One neighbour of a name, with the imports that connect them."""

    name: str
    imports: tuple[Import, ...]


@dataclass(frozen=True, slots=True)
class Step:
    source: str
    target: str
    imports: tuple[Import, ...]


@dataclass(frozen=True, slots=True)
class Cycle:
    """A cycle among the children of `level`: the shortest path through its first member.

    In a tangle of more than two members, `others` are the edges among the members
    that the path does not take, so every member's connections are shown. `rules` is
    the rules file whose components the members are, as shown; None when they are the
    package's children.
    """

    level: str
    members: tuple[str, ...]
    path: tuple[str, ...]
    steps: tuple[Step, ...]
    missed: tuple[str, ...]
    others: tuple[Step, ...] = ()
    rules: str | None = None


def _import_key(imp: Import) -> tuple[str, int, str, str]:
    return (imp.file, imp.line, imp.importer, imp.imported)


def resolve(model: Model, name: str) -> str:
    """A full name, a name relative to the project, or an external."""
    ids = sorted(n.id for n in model.nodes)
    known = set(ids)
    relative = f"{model.project}{model.separator}{name}"
    for candidate in (name, relative):
        if candidate in known:
            return candidate
    close = difflib.get_close_matches(relative, ids, n=3)
    close += difflib.get_close_matches(name, ids, n=3)
    hint = f"; did you mean {', '.join(dict.fromkeys(close))}?" if close else ""
    raise UnknownName(f"no module or package {name!r} in {model.project}{hint}")


def runtime_only(model: Model) -> Model:
    """Leave out imports that only type checkers see."""
    return replace(model, imports=tuple(i for i in model.imports if not i.type_checking))


def why(model: Model, source: str, target: str) -> Why:
    sep = model.separator
    for outer, inner in ((source, target), (target, source)):
        if within(inner, outer, sep):
            raise ValueError(f"{outer} contains {inner}; ask about two separate names")
    direct = sorted(
        (
            i
            for i in model.imports
            if within(i.importer, source, sep) and within(i.imported, target, sep)
        ),
        key=_import_key,
    )
    chain = () if direct else _shortest_chain(model, source, target)
    return Why(source, target, tuple(direct), chain)


def _shortest_chain(model: Model, source: str, target: str) -> tuple[Import, ...]:
    """Breadth-first from every module in `source`, never passing through either end."""
    sep = model.separator
    first: dict[tuple[str, str], Import] = {}
    for imp in sorted(model.imports, key=_import_key):
        first.setdefault((imp.importer, imp.imported), imp)
    successors: dict[str, list[str]] = defaultdict(list)
    for importer, imported in sorted(first):
        successors[importer].append(imported)

    starts = sorted({importer for importer, _ in first if within(importer, source, sep)})
    previous: dict[str, str | None] = dict.fromkeys(starts)
    queue = deque(starts)
    while queue:
        node = queue.popleft()
        for nxt in successors[node]:
            if within(nxt, target, sep):
                path = [nxt, node]
                while (before := previous[path[-1]]) is not None:
                    path.append(before)
                path.reverse()
                return tuple(first[pair] for pair in pairwise(path))
            if nxt in previous or within(nxt, source, sep):
                continue
            previous[nxt] = node
            queue.append(nxt)
    return ()


def dependencies(model: Model, name: str, externals: bool = False) -> tuple[Dependency, ...]:
    """What `name` imports from outside itself, shortened to its depth; third-party
    packages only with `externals`, as in the view."""
    found = _neighbours(model, name, outgoing=True)
    if externals:
        return found
    external = {n.id for n in model.nodes if n.kind == "external"}
    return tuple(d for d in found if d.name not in external)


def dependents(model: Model, name: str) -> tuple[Dependency, ...]:
    """What imports `name` from outside it, shortened to its depth."""
    return _neighbours(model, name, outgoing=False)


def _neighbours(model: Model, name: str, outgoing: bool) -> tuple[Dependency, ...]:
    sep = model.separator
    externals = {n.id for n in model.nodes if n.kind == "external"}
    depth = name.count(sep) + 1
    grouped: dict[str, list[Import]] = defaultdict(list)
    for imp in model.imports:
        here, there = (imp.importer, imp.imported) if outgoing else (imp.imported, imp.importer)
        if not within(here, name, sep) or within(there, name, sep):
            continue
        short = there if name in externals or there in externals else truncate(there, depth, sep)
        grouped[short].append(imp)
    return tuple(
        Dependency(other, tuple(sorted(imports, key=_import_key)))
        for other, imports in sorted(grouped.items())
    )


def all_cycles(
    model: Model, root: str | None = None, fold: bool = False, skip: Collection[str] = ()
) -> tuple[Cycle, ...]:
    """The cycles among the children of every package under `root` (default: all),
    except the packages in `skip`. With `fold`, a package's own modules count as one
    child named after the package (issue #25)."""
    root = root or model.project
    packages = sorted(
        n.id
        for n in model.nodes
        if n.kind == "package" and within(n.id, root, model.separator) and n.id not in skip
    )
    found: list[Cycle] = []
    for package in packages:
        view = build_view(model, package, fold=fold)
        found += cycles_among(package, (n.id for n in view.nodes), _view_edges(view.edges))
    return tuple(found)


def _view_edges(edges: Iterable[ViewEdge]) -> Edges:
    return {(e.source, e.target): e.imports for e in edges}


def cycles_among(
    level: str, members: Iterable[str], edges: Edges, rules: str | None = None
) -> list[Cycle]:
    """The cycles among `members`, the children of `level`, given the imports behind
    each edge between them; `rules` names the file the members come from, if any."""
    return [_cycle(level, cycle, edges, rules) for cycle in find_cycles(members, edges.keys())]


def _step(source: str, target: str, edges: Edges) -> Step:
    return Step(source, target, tuple(sorted(edges[(source, target)], key=_import_key)))


def _cycle(level: str, members: tuple[str, ...], edges: Edges, rules: str | None) -> Cycle:
    inside = set(members)
    graph = digraph(members, (pair for pair in edges if set(pair) <= inside))
    start = members[0]
    back: list[str] | None = None
    for nxt in sorted(graph.successors(start)):
        try:
            candidate = nx.shortest_path(graph, nxt, start)
        except nx.NetworkXNoPath:
            continue
        if back is None or len(candidate) < len(back):
            back = candidate
    path = (start, *(back or ()))
    steps = tuple(_step(s, t, edges) for s, t in pairwise(path))
    missed = tuple(m for m in members if m not in path)
    taken = set(pairwise(path))
    others = tuple(
        _step(s, t, edges) for s, t in sorted(edges) if {s, t} <= inside and (s, t) not in taken
    )
    return Cycle(level, members, path, steps, missed, others, rules)
