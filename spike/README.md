# Spike: the whole pipeline in one file

`arch_graph.py` is a ~200-line proof of concept that shows the core of the tool works with off-the-shelf parts:

1. **grimp** builds the import graph of an installed/importable package (relative imports, function-level imports, module-vs-attribute resolution all handled).
2. Imports are aggregated to the children of a chosen root (package → package edges with counts and example `module:line` locations).
3. **networkx** finds cycles (strongly connected components) and layers (topological generations of the condensation DAG) — the same idea as Uncle Bob's arch-view.
4. Output is JSON (for a future UI) or Graphviz DOT (for a picture), and `--rules` turns it into a deterministic checker with exit code 1 on violations or cycles.

## Run it

```bash
uv venv && source .venv/bin/activate          # or any venv
uv pip install grimp networkx import-linter   # import-linter only as a sample target
python arch_graph.py importlinter                                  # JSON view of the top level
python arch_graph.py importlinter --root importlinter.application  # drill down one level
python arch_graph.py importlinter --dot | dot -Tsvg > out.svg      # picture (needs Graphviz)
python arch_graph.py importlinter --rules rules.example.json       # checker; exit 1 (one edge is deliberately missing from the rules)
```

To run it on your own project, make the package importable (e.g. `PYTHONPATH=src`) and pass its top-level package name.

`example-importlinter.svg` is the rendered top level of import-linter itself: cli / api / contracts on top, configuration → adapters → application → domain below. That is the picture the real tool should produce interactively, with click-to-drill-down and click-to-open-source.

## Viewer: `viewer/view.py`

A drill-down viewer for any Python repo, in one self-contained HTML file. It needs no
setup beyond `uv` - the script carries its own dependencies (PEP 723), finds the repo's
top-level packages itself, and opens the result in your browser:

```bash
uv run spike/viewer/view.py                    # analyse the current directory
uv run spike/viewer/view.py ~/git/some-repo    # analyse another repo
uv run spike/viewer/view.py ~/git/some-repo -p mypkg -o out.html --no-open
```

- **Detection** handles the three common layouts: `src/<pkg>/`, a flat `<pkg>/` at the
  repo root, and `src/` as the package itself. `tests`, `docs`, `build` and friends are
  skipped. Every package found becomes a root button in the header; `-p` overrides.
- **Drill down** by clicking a package; the breadcrumb walks back up; the root is in the
  URL hash, so back/forward and reload work.
- **Cycles** are red - nodes, edges and the count in the header.
- **Click an edge** to see the imports behind it (`module:line` plus the import line),
  which is what you need to decide which edge to break.
- The output inlines the views, the Graphviz DOT and Graphviz-WASM
  (`vendor/viz-global.js`, from `npm pack @viz-js/viz`), so it is ~1.5 MB, works offline
  and can be mailed to someone. Nothing is fetched at runtime.

Same rules as the rest of the spike: the analysed project is never imported or executed,
only parsed.

## What the spike does *not* do (and the real tool must)

- The viewer is a generated static file, not `archview serve`: no source panel, no
  hover details, no cross-package edges (each top-level package is its own graph).
- Cycle handling for layering uses networkx's condensation (cycles collapse into one node) rather than choosing which edge to break.
- No abstractness detection, no metrics, no exclusions/config file, no baseline, no JSON schema, no tests.
- Checker only supports an `allowed` map + `fail_on_cycles`; no forbidden edges, exceptions, or hints.
