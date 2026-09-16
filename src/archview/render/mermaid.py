"""Render a view as a Mermaid flowchart, for markdown in PRs and docs (requirement V12)."""

from __future__ import annotations

import re
from collections.abc import Collection

from archview.model.view import View, ViewEdge, ViewNode

Pair = tuple[str, str]
CLASSES = [
    "  classDef cycle stroke:#d62828,color:#d62828,stroke-width:2px",
    "  classDef abstract fill:#dcefd9",
    "  classDef external stroke-dasharray:4 3",
]


def _id(node_id: str) -> str:
    return "n_" + re.sub(r"\W", "_", node_id)


def _node(node: ViewNode) -> str:
    modules = "1 module" if node.module_count == 1 else f"{node.module_count} modules"
    label = node.name if node.kind != "package" else f"{node.name}<br/>{modules}"
    shape = f'(["{label}"])' if node.kind == "external" else f'["{label}"]'
    return f"  {_id(node.id)}{shape}"


def _arrow(edge: ViewEdge, violating: bool) -> str:
    if violating:
        return f"-. {edge.count} ✗ .->"
    if edge.type_checking:
        return f"-. {edge.count} .->"
    return f"-- {edge.count} -->"


def to_mermaid(view: View, violations: Collection[Pair] = ()) -> str:
    lines = [f"%% archview: {view.root}", "flowchart TB"]
    lines.extend(_node(n) for n in view.nodes)
    lines.extend(
        f"  {_id(e.source)} {_arrow(e, (e.source, e.target) in violations)} {_id(e.target)}"
        for e in view.edges
    )
    lines.extend(CLASSES)
    for name, members in (
        ("cycle", [n for n in view.nodes if n.in_cycle]),
        ("abstract", [n for n in view.nodes if n.abstract]),
        ("external", [n for n in view.nodes if n.kind == "external"]),
    ):
        if members:
            lines.append(f"  class {','.join(_id(n.id) for n in members)} {name}")
    cyclic = [i for i, e in enumerate(view.edges) if e.in_cycle]
    if cyclic:
        lines.append(f"  linkStyle {','.join(map(str, cyclic))} stroke:#d62828,stroke-width:2px")
    return "\n".join(lines) + "\n"
