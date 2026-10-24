# 4. Module layout inside `archview`

Date: 2026-09-06

## Status

Accepted.

## Context

`docs/05-architecture.md` sketches `model/graph.py` as holding "Tree, Edge,
View, JSON (de)serialisation", and lists `cli`, `server` and `ui` as the presentation
layer. The first version needed somewhere to put the Graphviz DOT renderer, which is
presentation but is shared by the CLI today and by the server later (ADR 0007).

## Decision

`model/` is split by concern rather than kept in one file:

| Module | Holds |
|---|---|
| `model/graph.py` | `Node`, `Import`, `Model` — the tree and the raw imports |
| `model/view.py` | `View`, `ViewNode`, `ViewEdge`, `build_view` — aggregation for a root |
| `model/cycles.py` | strongly connected components |
| `model/layers.py` | topological layering |
| `model/serialize.py` | model and view <-> JSON, plus `schema.json` |

A new `render/` package holds format-only output (`render/dot.py` now, Mermaid and
SVG later, ADR 0008). `extract/discover.py` joins `extract/` because working out which
top-level packages a repo has is a Python-layout question.

## Consequences

The components the checker will police (ADR 0006) are `extract`, `model`, `render`, `cli`
— `render` is one more than `docs/05` lists. The dependency direction the tool holds
itself to is unchanged and already true: `cli` -> `extract`, `render` -> `model`, and
`model` imports nothing of ours.
