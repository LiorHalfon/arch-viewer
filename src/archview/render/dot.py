"""Render a view as Graphviz DOT: layered boxes, counted edges, red cycles.

Colours are set in the DOT so `archview graph --dot | dot -Tsvg` looks right on its
own; `class` attributes let the web UI restyle the same SVG for its themes.

Legend (V6-V8): packages are UML components, modules plain boxes, abstract nodes
green, external packages dashed. Edges to abstractions end in a hollow triangle,
edges only for type checkers are dotted, cyclic edges red, rule violations orange
and dashed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection

from archview.model.view import View, ViewEdge, ViewNode

HEADER = [
    "  rankdir=TB; newrank=true; splines=true; nodesep=0.5; ranksep=0.9;",
    '  node [shape=box style="rounded,filled" fontname="Helvetica"'
    ' fillcolor="#e2ecf7" color="#7890a0"];',
    '  edge [color="#556677" fontname="Helvetica" fontsize=9];',
]
ABSTRACT_FILL = "#dcefd9"
Pair = tuple[str, str]


def _label(node: ViewNode, tangled: bool) -> str:
    mark = " ⟲" if tangled else ""
    if node.kind in ("module", "external"):
        return node.name
    modules = "1 module" if node.module_count == 1 else f"{node.module_count} modules"
    return f"{node.name}{mark}\\n({modules})"


def _classes(node: ViewNode, tangled: bool) -> str:
    names = [node.kind]
    if node.in_cycle:
        names.append("cycle")
    if tangled:
        names.append("tangled")
    if node.abstract:
        names.append("abstract")
    if node.zone in ("pain", "useless"):
        names.append(f"zone-{node.zone}")
    return " ".join(names)


def _shape(node: ViewNode) -> str:
    if node.kind == "package":
        return ' shape=component style="filled"'
    if node.kind == "external":
        return ' style="rounded,dashed" fillcolor="#ffffff"'
    return ' fillcolor="#f7f7f7" penwidth=2'


def _node_line(node: ViewNode, tangled: bool) -> str:
    red = ' fontcolor="red"' if node.in_cycle or tangled else ""
    green = f' fillcolor="{ABSTRACT_FILL}"' if node.abstract else ""
    return (
        f'  "{node.id}" [label="{_label(node, tangled)}"{red}{_shape(node)}{green}'
        f' class="{_classes(node, tangled)}"];'
    )


def _edge_line(edge: ViewEdge, violating: bool) -> str:
    attrs, classes = [], []
    if edge.in_cycle:
        attrs.append('color="red" penwidth=2')
        classes.append("cycle")
    if violating:
        attrs.append('color="#d9480f" style="dashed" penwidth=2')
        classes.append("violation")
    elif edge.type_checking:
        attrs.append('style="dotted"')
        classes.append("typing")
    if edge.abstract:
        attrs.append("arrowhead=onormal")
        classes.append("abstract")
    extra = "".join(f" {a}" for a in attrs)
    cls = f' class="{" ".join(classes)}"' if classes else ""
    return f'  "{edge.source}" -> "{edge.target}" [label="{edge.count}"{extra}{cls}];'


def to_dot(view: View, tangled: Collection[str] = (), violations: Collection[Pair] = ()) -> str:
    """`tangled`: packages with a cycle somewhere inside; `violations`: edges that break rules."""
    by_layer: dict[int, list[ViewNode]] = defaultdict(list)
    for node in view.nodes:
        by_layer[node.layer].append(node)

    lines = [f'digraph "{view.root}" {{', *HEADER]
    for layer in sorted(by_layer):
        ids = " ".join(f'"{n.id}"' for n in by_layer[layer])
        lines.append(f"  {{ rank=same; {ids} }}")
    lines.extend(_node_line(n, n.id in tangled) for n in view.nodes)
    lines.extend(_edge_line(e, (e.source, e.target) in violations) for e in view.edges)
    lines.append("}")
    return "\n".join(lines) + "\n"
