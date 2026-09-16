"""Render a view as Graphviz DOT: layered boxes, counted edges, red cycles.

Colours are set in the DOT so `archview graph --dot | dot -Tsvg` looks right on its
own; `class` attributes let the web UI restyle the same SVG for its themes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection

from archview.model.view import View, ViewNode

HEADER = [
    "  rankdir=TB; newrank=true; splines=true; nodesep=0.5; ranksep=0.9;",
    '  node [shape=box style="rounded,filled" fontname="Helvetica"'
    ' fillcolor="#e2ecf7" color="#7890a0"];',
    '  edge [color="#556677" fontname="Helvetica" fontsize=9];',
]


def _label(node: ViewNode, tangled: bool) -> str:
    mark = " ⟲" if tangled else ""
    if node.kind == "module":
        return node.name
    modules = "1 module" if node.module_count == 1 else f"{node.module_count} modules"
    return f"{node.name}{mark}\\n({modules})"


def _classes(node: ViewNode, tangled: bool) -> str:
    names = [node.kind]
    if node.in_cycle:
        names.append("cycle")
    if tangled:
        names.append("tangled")
    return " ".join(names)


def _node_line(node: ViewNode, tangled: bool) -> str:
    style = (
        ' shape=component style="filled"'
        if node.kind == "package"
        else (' fillcolor="#f7f7f7" penwidth=2')
    )
    red = ' fontcolor="red"' if node.in_cycle or tangled else ""
    return (
        f'  "{node.id}" [label="{_label(node, tangled)}"{red}{style}'
        f' class="{_classes(node, tangled)}"];'
    )


def to_dot(view: View, tangled: Collection[str] = ()) -> str:
    """`tangled`: packages whose subtree contains a cycle somewhere below this level."""
    by_layer: dict[int, list[ViewNode]] = defaultdict(list)
    for node in view.nodes:
        by_layer[node.layer].append(node)

    lines = [f'digraph "{view.root}" {{', *HEADER]
    for layer in sorted(by_layer):
        ids = " ".join(f'"{n.id}"' for n in by_layer[layer])
        lines.append(f"  {{ rank=same; {ids} }}")
    lines.extend(_node_line(n, n.id in tangled) for n in view.nodes)
    for edge in view.edges:
        cycle = ' color="red" penwidth=2 class="cycle"' if edge.in_cycle else ""
        lines.append(f'  "{edge.source}" -> "{edge.target}" [label="{edge.count}"{cycle}];')
    lines.append("}")
    return "\n".join(lines) + "\n"
