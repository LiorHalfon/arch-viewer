"""Strongly connected components: the cycles at one level (requirement A7)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

import networkx as nx


def digraph(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> nx.DiGraph:
    """Built from sorted input so the result never depends on insertion order (N1)."""
    graph = nx.DiGraph()
    graph.add_nodes_from(sorted(nodes))
    graph.add_edges_from(sorted(edges))
    return graph


def components(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Map each node to a stable id for its component: the name of its smallest member."""
    graph = digraph(nodes, edges)
    return {
        member: min(group) for group in nx.strongly_connected_components(graph) for member in group
    }


def find_cycles(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> tuple[tuple[str, ...], ...]:
    """Every component with more than one member, sorted by name."""
    members: dict[str, list[str]] = defaultdict(list)
    for node, component in components(nodes, edges).items():
        members[component].append(node)
    return tuple(sorted(tuple(sorted(g)) for g in members.values() if len(g) > 1))


def describe_cycle(members: tuple[str, ...]) -> str:
    """`a -> b -> a` for two members; with more, the order is not a real path, so say so."""
    if len(members) == 2:
        return f"{members[0]} -> {members[1]} -> {members[0]}"
    return f"tangle of {len(members)}: {', '.join(members)}"
