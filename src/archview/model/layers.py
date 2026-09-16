"""Vertical ranks: importers on top, the most depended-upon at the bottom (A8)."""

from __future__ import annotations

from collections.abc import Iterable

import networkx as nx

from archview.model.cycles import digraph


def assign_layers(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> dict[str, int]:
    """Topological generations of the condensation, so a cycle's members share a layer."""
    condensed = nx.condensation(digraph(nodes, edges))
    return {
        member: depth
        for depth, generation in enumerate(nx.topological_generations(condensed))
        for component in generation
        for member in condensed.nodes[component]["members"]
    }
