#!/usr/bin/env python3
"""Spike: extract a layered "architecture view" of a Python package using grimp.

This is a proof of concept for the arch-viewer project, not production code.
It demonstrates the core pipeline in ~200 lines:

  1. Build the module import graph of an importable package (grimp does the
     parsing, relative-import resolution and module-vs-attribute disambiguation).
  2. Pick a "root" (the package or any sub-package) and aggregate all imports
     between the root's *children* -> one edge per child pair with a count.
  3. Find cycles (strongly connected components) among those children.
  4. Assign layers: importers at the top, the most depended-upon at the bottom
     (topological order of the condensation DAG, exactly like Uncle Bob's
     arch-view does for Clojure namespaces).
  5. Optionally check the aggregated edges against an "allowed dependencies"
     map (the deterministic rules checker), exit 1 on violations.
  6. Emit JSON (for a future UI) and/or Graphviz DOT (for a quick picture).

Usage (from a venv where the target package is importable):

  python arch_graph.py importlinter                      # JSON to stdout
  python arch_graph.py importlinter --root importlinter.contracts --dot | dot -Tsvg > out.svg
  python arch_graph.py importlinter --rules rules.json   # exit 1 on violations

rules.json example (mirrors dependency-checker.edn's :allowed-dependencies):
  {"allowed": {"cli": ["application", "domain"], "application": ["domain"], "domain": []},
   "fail_on_cycles": true}
Component names are the child names relative to --root.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

import grimp
import networkx as nx


def _short(module: str, root: str) -> str:
    return module[len(root) + 1 :] if module.startswith(root + ".") else module


def _child_of(module: str, root: str, children: set[str]) -> str | None:
    """Map any descendant module of root to the direct child it belongs to."""
    for child in children:
        if module == child or module.startswith(child + "."):
            return child
    return None


def build_view(graph: grimp.ImportGraph, root: str) -> dict:
    children = set(graph.find_children(root))
    if not children:
        raise SystemExit(f"{root} has no children (it is a leaf module)")

    # 1. Aggregate module-level imports to child-level edges.
    counts: dict[tuple[str, str], int] = defaultdict(int)
    examples: dict[tuple[str, str], list[dict]] = defaultdict(list)
    members = {root} | set(graph.find_descendants(root))
    for importer in members:
        src = _child_of(importer, root, children)
        if src is None:
            continue
        for imported in graph.find_modules_directly_imported_by(importer):
            dst = _child_of(imported, root, children)
            if dst is None or dst == src:
                continue
            counts[(src, dst)] += 1
            if len(examples[(src, dst)]) < 3:
                for detail in graph.get_import_details(importer=importer, imported=imported):
                    examples[(src, dst)].append(
                        {"importer": importer, "imported": imported,
                         "line": detail["line_number"], "text": detail["line_contents"]})
                    break

    # 2. Cycles = strongly connected components with more than one member.
    g = nx.DiGraph()
    g.add_nodes_from(children)
    g.add_edges_from(counts.keys())
    sccs = [sorted(c) for c in nx.strongly_connected_components(g) if len(c) > 1]
    cyclic_nodes = {n for c in sccs for n in c}
    cyclic_edges = {(a, b) for (a, b) in counts if a in cyclic_nodes and b in cyclic_nodes
                    and nx.has_path(g, b, a)}

    # 3. Layers from the condensation DAG (cycles collapse into one node).
    cond = nx.condensation(g)
    layer_of_scc = {}
    for depth, generation in enumerate(nx.topological_generations(cond)):
        for scc_id in generation:
            layer_of_scc[scc_id] = depth
    layer_of = {n: layer_of_scc[cond.graph["mapping"][n]] for n in children}

    nodes = []
    for child in sorted(children):
        descendants = graph.find_descendants(child)
        nodes.append({
            "id": child,
            "name": _short(child, root),
            "kind": "package" if descendants else "module",
            "module_count": len(descendants) + 1,
            "layer": layer_of[child],
            "in_cycle": child in cyclic_nodes,
            "fan_in": sum(c for (a, b), c in counts.items() if b == child),
            "fan_out": sum(c for (a, b), c in counts.items() if a == child),
        })
    edges = [{
        "from": a, "to": b, "count": c, "in_cycle": (a, b) in cyclic_edges,
        "examples": examples[(a, b)],
    } for (a, b), c in sorted(counts.items())]
    return {"root": root, "nodes": nodes, "edges": edges, "cycles": sccs}


def check_rules(view: dict, rules: dict) -> list[str]:
    """Deterministic checker: every aggregated edge must be explicitly allowed."""
    allowed = rules.get("allowed", {})
    problems = []
    for e in view["edges"]:
        src, dst = _short(e["from"], view["root"]), _short(e["to"], view["root"])
        ok = allowed.get(src) == "all" or dst in allowed.get(src, [])
        if not ok:
            ex = e["examples"][0] if e["examples"] else {}
            where = f" (e.g. {ex.get('importer')}:{ex.get('line')})" if ex else ""
            problems.append(f"VIOLATION {src} -> {dst} ({e['count']} imports){where}")
    if rules.get("fail_on_cycles") and view["cycles"]:
        for cycle in view["cycles"]:
            problems.append("CYCLE " + " <-> ".join(_short(n, view["root"]) for n in cycle))
    return problems


def to_dot(view: dict) -> str:
    root = view["root"]
    out = [f'digraph "{root}" {{', "  rankdir=TB; newrank=true; splines=true; nodesep=0.5; ranksep=0.9;",
           '  node [shape=box style="rounded,filled" fontname="Helvetica" fillcolor="#e2ecf7" color="#7890a0"];',
           '  edge [color="#556677" fontname="Helvetica" fontsize=9];']
    by_layer: dict[int, list[dict]] = defaultdict(list)
    for n in view["nodes"]:
        by_layer[n["layer"]].append(n)
    for layer in sorted(by_layer):
        ids = " ".join(f'"{n["id"]}"' for n in by_layer[layer])
        out.append(f"  {{ rank=same; {ids} }}")
    for n in view["nodes"]:
        color = ' fontcolor="red"' if n["in_cycle"] else ""
        shape = "" if n["kind"] == "package" else ' fillcolor="#f7f7f7" penwidth=2'
        label = f'{n["name"]}\\n({n["module_count"]} modules)' if n["kind"] == "package" else n["name"]
        out.append(f'  "{n["id"]}" [label="{label}"{color}{shape}];')
    for e in view["edges"]:
        style = ' color="red" penwidth=2' if e["in_cycle"] else ""
        out.append(f'  "{e["from"]}" -> "{e["to"]}" [label="{e["count"]}"{style}];')
    out.append("}")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("package", help="importable top-level package, e.g. myapp")
    p.add_argument("--root", help="sub-package to view (default: the package itself)")
    p.add_argument("--dot", action="store_true", help="emit Graphviz DOT instead of JSON")
    p.add_argument("--rules", help="JSON file with allowed dependencies; exit 1 on violations")
    args = p.parse_args()

    graph = grimp.build_graph(args.package, cache_dir=None)
    view = build_view(graph, args.root or args.package)

    if args.rules:
        with open(args.rules) as f:
            problems = check_rules(view, json.load(f))
        for line in problems:
            print(line)
        print(f"{len(problems)} problem(s) in {view['root']}")
        return 1 if problems else 0

    print(to_dot(view) if args.dot else json.dumps(view, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
