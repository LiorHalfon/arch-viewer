"""Render a view as Graphviz DOT: layered boxes, counted edges, red cycles."""

from __future__ import annotations

from collections import defaultdict

from archview.model.view import View, ViewNode

HEADER = [
    "  rankdir=TB; newrank=true; splines=true; nodesep=0.5; ranksep=0.9;",
    '  node [shape=box style="rounded,filled" fontname="Helvetica"'
    ' fillcolor="#e2ecf7" color="#7890a0"];',
    '  edge [color="#556677" fontname="Helvetica" fontsize=9];',
]


def _label(node: ViewNode) -> str:
    if node.kind == "module":
        return node.name
    return f"{node.name}\\n({node.module_count} modules)"


def _node_line(node: ViewNode) -> str:
    style = "" if node.kind == "package" else ' fillcolor="#f7f7f7" penwidth=2'
    cycle = ' fontcolor="red"' if node.in_cycle else ""
    return f'  "{node.id}" [label="{_label(node)}"{cycle}{style}];'


def to_dot(view: View) -> str:
    by_layer: dict[int, list[ViewNode]] = defaultdict(list)
    for node in view.nodes:
        by_layer[node.layer].append(node)

    lines = [f'digraph "{view.root}" {{', *HEADER]
    for layer in sorted(by_layer):
        ids = " ".join(f'"{n.id}"' for n in by_layer[layer])
        lines.append(f"  {{ rank=same; {ids} }}")
    lines.extend(_node_line(n) for n in view.nodes)
    for edge in view.edges:
        cycle = ' color="red" penwidth=2' if edge.in_cycle else ""
        lines.append(f'  "{edge.source}" -> "{edge.target}" [label="{edge.count}"{cycle}];')
    lines.append("}")
    return "\n".join(lines) + "\n"
