# 3. Layers come from the condensation of the graph, not from removing edges

Date: 2026-09-06 (M1)

## Status

Accepted for M1; revisit if the viewer needs to name the edge that causes a cycle.

## Context

Requirement A8 describes layering as: remove a minimal (or good-enough) set of
cycle-causing edges, topologically order the rest, and still show the removed edges.
Finding a minimum feedback arc set is NP-hard, and "good enough" needs a ranking
heuristic and a tie-break rule to stay deterministic (N1).

## Decision

M1 collapses each strongly connected component into one node (networkx
`condensation`), layers the resulting DAG with `topological_generations`, and gives
every member of a component the layer of that component.

No edge is removed or hidden: the members of a cycle simply share a rank, and the
cyclic edges are drawn between them in red.

## Consequences

The picture is the same as arch-view's for acyclic parts, and for a cycle it shows
the members side by side instead of picking a victim edge. What is missing is the
cycle-breaker ranking ("this one edge, if inverted, would make the graph acyclic"),
which is the genuinely useful advice for the human. That belongs with the checker's
remedy hints (C4) and needs its own decision once we know what the hint should say.
