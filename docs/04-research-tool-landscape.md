# Research — existing open-source tools and building blocks

Researched 2026-08-30. Versions/dates come from PyPI/npm registry metadata and fetched GitHub/docs pages; the Python tools were additionally installed and run against a fixture package (relative import `from ..domain import models`, an `__init__` re-export, a function-level import forming a cycle, an `if TYPE_CHECKING:` import, and `importlib.import_module("...")`). Anything not confirmed first-hand is marked *unverified*.

## 0. Bottom line

| Need | Best foundation | Why | Runner-up |
|---|---|---|---|
| Python import-graph extraction | **grimp** 3.16 (BSD-2, 2026-08-28) | Library-first, Rust parser, resolves relative imports and module-vs-attribute correctly, gives `file:line` per import, ships the exact higher-order queries we need (children/descendants, upstream/downstream, shortest chains, layer violations, cycle-breaker nomination). Same author/cadence as import-linter. | `ruff analyze graph` (experimental, CLI-only, finds string imports); tree-sitter + own resolver (only when going multi-language) |
| Rule enforcement | **import-linter** contracts as the reference semantics; our own thin rules file on top of grimp | Covers forbidden/layers/independence/protected/acyclic-siblings with custom contract classes and exit codes, but has text-only output and no JSON; we need agent-readable JSON and a DC-style `allowed` map. | tach's `depends_on`/`interfaces` model + `--output json` shape (copy the diagnostic format) |
| Viewer | Build our own web UI on the model JSON; start with **Graphviz-in-the-browser** (`@viz-js/viz`), graduate to **ELK + React Flow** | import-linter's `explore` already proves the drill-down-with-Graphviz pattern in ~11 KB of JS; ELK's layered algorithm with partitions is the only free layout that does compound nodes + forced layers + orthogonal routing. | LikeC4 (embed a ready-made React drill-down viewer, Graphviz layouts, MCP server) |
| Multi-language later | tree-sitter grammars (or scip indexers) feeding the same JSON | Everything above the extractor is language-agnostic by design. | repowise/graphify (AGPL / MIT, agent-oriented, no rules) |

## 1. Python: extraction and enforcement

### Behaviour on the fixture (what each tool actually resolves)

| Tool | `from ..pkg import mod` | `from pkg import submod` → edge to `pkg.submod`? | Function-level import | `TYPE_CHECKING` import | Dynamic string import | Sees through `__init__` re-export? |
|---|---|---|---|---|---|---|
| grimp 3.16 | yes | yes | yes | included; `exclude_type_checking_imports=True` drops it | no | no (edge stops at the package) |
| tach 0.35.0 | yes | yes | yes | ignored by default | `tach map` yes; `tach check` does not flag | no |
| `ruff analyze graph` 0.16.5 | yes | yes | yes | `--no-type-checking-imports` | with `--detect-string-imports` | no |
| pydeps 3.0.7 | yes | yes (+ noisy extra edges to every ancestor package) | yes | included | no | no |
| pyreverse (pylint 4.0.8) | **no — `..` imports silently dropped** | yes | yes | dashed edge | no | no |
| pytestarch 4.0.1 | yes | **no** (edge to the package) | yes | included | no | no |
| findimports 3.0.0 | yes | yes | yes | included | no | no |
| ArchUnitPython 1.5.0 | edge to `domain/__init__.py` | no | yes | tagged `type` | **yes** (tagged `dynamic`) | no |
| pytest-archon 0.0.7 | bug: `from .service` inside `__init__` mis-resolved | yes | yes | option | no | no |
| deply 1.1.0 | class imports only | **module imports invisible** | — | — | no | — |

### grimp — https://github.com/python-grimp/grimp (BSD-2; 3.16, 2026-08-28; Python ≥ 3.10)
`grimp.build_graph("pkg", include_external_packages=..., exclude_type_checking_imports=..., cache_dir=...)` returns an `ImportGraph` with: `modules`, `find_children`, `find_descendants`, `find_matching_modules`, `direct_import_exists`, `find_modules_directly_imported_by`, `find_modules_that_directly_import`, `get_import_details` (line number + source line), `count_imports`, `find_upstream_modules`, `find_downstream_modules`, `find_shortest_chain(s)`, `chain_exists`, `find_illegal_dependencies_for_layers(layers, containers)` (returns importer/imported plus the concrete routes), `nominate_cycle_breakers(package)`, and mutation helpers (`add/remove_module`, `add/remove_import`, `squash_module`) for what-if analysis. Rust core using ruff's Python parser with multithreaded scanning (since 3.9–3.11); on-disk cache. Limitations: no serializer (we write the JSON), no "enumerate all cycles" (we compute SCCs ourselves — trivial with networkx or Tarjan), the analysed package must be locatable via the import system (it is not executed), no symbol-level resolution through re-exports.

### import-linter — https://github.com/seddonym/import-linter (BSD-2; 2.14, 2026-08-28; requires grimp ≥ 3.14)
Contracts in `.importlinter` / `setup.cfg` / `pyproject.toml`: `forbidden`, `protected`, `layers` (containers, closed layers, `|` for independent siblings), `independence`, `acyclic_siblings`, plus custom contract classes (`importlinter.Contract` with `check(graph)`), `ignore_imports` wildcards, and `broken_contract_guidance` text (2.14) shown on failure. `lint-imports` exits 1 on failure; **no JSON output**. Since 2.10 (Feb 2026): `import-linter explore PACKAGE` starts a local FastAPI/uvicorn page (`pip install import-linter[ui]`) that draws the *immediate children* of a package as a Graphviz graph (rendered client-side with bundled `viz-standalone.js`), aggregated edge counts, click-to-drill into child packages, toggles for import totals / module counts / cycle breakers (dashed). `import-linter drawgraph PACKAGE` prints that DOT. It has no module→source view and no whole-tree layering, but it is the closest existing thing to arch-view for Python and the fastest thing to fork (`src/importlinter/ui/`: `server.py`, `explorer.py`, ~11 KB `explorer.js`).

### tach — https://github.com/tach-org/tach (MIT; 0.35.0 on PyPI, 2026-05-12; Rust core on ruff's parser + petgraph)
Modular-monolith enforcement: `tach.toml` with `[[modules]]` (`depends_on`, `cannot_depend_on`, `layer`, `visibility`, `utility`, `unchecked`), `[[interfaces]]` (`expose` regexes — public-interface enforcement of *what* is imported), ordered `layers`, `forbid_circular_dependencies`, `external` deps checking. `tach check --output json` gives structured diagnostics with file/line; `tach sync` writes discovered `depends_on` into the config (the equivalent of DC `--init`); `tach map` dumps a file-level import JSON; `tach show` draws the **declared** rule graph (not the actual imports), `--web` uploads to a hosted viewer. History: gauge-sh/tach → unmaintained for ~7 months in 2025 → revived under `tach-org` in 2026 (monthly releases Jan–May 2026, nothing since May). CLI-first, no documented Python API. Worth copying: the diagnostic JSON shape, `interfaces`, `tach-ignore` comments.

### pydeps — https://github.com/thebjorn/pydeps (BSD-2; 3.0.7, 2026-08-03)
Graphviz pictures from a bytecode `ModuleFinder` scan: `--show-cycles`, `--cluster`, `--max-bacon`, `--max-module-depth`, `--only/--exclude`, `--rankdir`, JSON deps map (`--show-deps`), DOT out. Needs importable code and the `dot` binary; adds noisy ancestor edges; no rules; no interactivity. Fine for a one-off picture, not as a foundation.

### pyreverse (in pylint 4.0.8, GPL-2.0)
`pyreverse -o mmd|puml|dot|html -p name src/` produces package and class diagrams via astroid, but two-dot relative imports produced no edges in the fixture and `--max-depth` filters nodes instead of rolling edges up. Not reliable for package-level dependency analysis; GPL.

### pytestarch — https://github.com/zyskarch/pytestarch (Apache-2.0; 4.0.1, 2025-08-08)
ArchUnit-style fluent rules as pytest tests (`Rule().modules_that()...should_not().import_modules_that()...`, `LayeredArchitecture`). Uses `ast` + networkx; `from X import y` resolves to `X` even when `y` is a module, and modules are named relative to the root's parent. Pytest-bound; no CLI/JSON.

### ArchUnitPython — https://github.com/LukasNiessen/ArchUnitPython (MIT; 1.5.0, 2026-07-18)
Fluent rules over folders/globs (`project_files(".").in_folder("infra").should_not().depend_on_files().in_folder("domain")`, `have_no_cycles()`, layers/slices/metrics). `extract_graph()` returns edges tagged `import|from_import|relative|type|dynamic` — the only tool in the set that detected the `importlib.import_module` string import. Relative imports resolve to `__init__.py` rather than the module; selector semantics are easy to get wrong. Young, but a useful reference for a fluent rule API.

### Others, briefly
- **`ruff analyze graph`** (experimental, prints a warning): file-level import JSON, `--direction dependencies|dependents`, `--detect-string-imports`, TYPE_CHECKING toggle. CLI only, may change; good as an independent oracle in tests.
- **deptry** 0.25.1 (MIT): declared-vs-used third-party dependencies (DEP001–004). Not architecture.
- **ruff TID251/252/253**: bans a module/member everywhere; no importer side, no layers, no cycles. Nested `ruff.toml` per package is the only way to scope a ban.
- **findimports** 3.0.0 (MIT): small `ast` CLI with DOT/JSON out, package roll-up (`-p`), collapse levels (`-l N`), collapse cycles (`-c`); resolved the fixture correctly. Handy reference implementation.
- **importlab** (Google) — archived 2025-05; **modulegraph** — bytecode scanner for freezing tools, drags in the stdlib; **snakefood3** — GPL, 2022; **pyan3** — revived 2026, GPL, *call* graphs (complementary, not import graphs); **code2flow** — MIT, unmaintained since 2023, call graphs.
- **deply** 1.1.0 (BSD-3): YAML layers via collectors + rules + Mermaid, but models classes/functions, not modules — module imports are invisible to it.
- **pytest-archon** 0.0.7 (Apache-2.0): fnmatch rules; mis-resolved a relative import inside `__init__.py` in the fixture.
- New in 2026: **Fensu** (opinionated structural linter, prescribed layout), **pylint-clean-architecture** (regex layer mapping, alpha), **arch-lint** (Fluid Attacks; pins grimp < 3), **pyscn** (Go + tree-sitter quality analyser; reported "no cycles" while its own matrix showed one), **py-import-cycles**, **importee**. None is a better base than grimp.
- **scip-python** (MIT; npm 0.6.6, 2025-09) + `scip` CLI: Pyright-based symbol-level index (definitions/references across modules) — the way to see through `__init__` re-exports if that ever matters; heavy (Node + full type analysis). **tree-sitter-python** 0.25 / py-tree-sitter 0.26: fast error-tolerant parsing, but you re-implement grimp's resolver; keep for the multi-language phase.

## 2. Viewers you could fork or embed

| Tool | License / status | What it is | Verdict for us |
|---|---|---|---|
| **import-linter `explore`** | BSD-2, 2026 | Graphviz-WASM drill-down of a package's children on top of grimp; FastAPI server + tiny vanilla JS | **Fastest path to a demo**; add source panel, layering (`rank=same`), cycles list, violations overlay |
| **LikeC4** — https://likec4.dev | MIT; 1.59.2 (npm, 2026-07-22); very active | "Architecture as code" DSL + React viewer (`@likec4/diagram` = React Flow + dagre; layouts via Graphviz WASM), drill-down navigation, element details, static site export, `gen mermaid|dot|d2|plantuml`, VS Code extension, `@likec4/mcp` server, Builder API to construct models programmatically | Strong "embed instead of build" option: map model JSON → LikeC4 model → `<ReactLikeC4 />`; costs: one view per level, C4 vocabulary, Graphviz-only layout, scale *unverified* |
| **Emerge** — https://github.com/glato/emerge | MIT; 2.0.7 (2024-08), dormant | Multi-language file-level dependency scan → interactive D3 force-graph HTML + GraphML/JSON; metrics, git hotspots | Not layered, no compound nodes, jQuery-era front-end; only its export format is interesting |
| **CodeCharta** — https://github.com/MaibornWolff/codecharta | BSD-3; 1.143 (2026), active | "Code city" 3D metrics map from `cc.json`; importers for Sonar/Tokei/git; optional `edges` metrics | Complementary (hotspots), not a dependency viewer |
| **Sourcetrail** | original archived 2021 (GPL-3); fork petermost/Sourcetrail 2026.6 active but **Python support removed** | Desktop C++ symbol explorer | No |
| **depends** — https://github.com/multilang-depends/depends | MIT; 0.9.7, dormant | JVM CLI extracting file/method-level deps for cpp/java/ruby/python/pom → JSON/DOT/PlantUML/Excel (DSM-oriented) | Possible multi-language extractor later; Python quality *unverified* |
| **Structurizr** | Lite/CLI/cloud EOL (Feb 2026); consolidated `structurizr/structurizr` (Apache-2.0, 2026.06) | C4 DSL, hand-modelled, exports PlantUML/Mermaid, has an MCP plugin | Not derived from code; export target at most |
| **codeflow**, **graphify**, **codebase-memory-mcp**, **code-review-graph**, **repowise** (AGPL), **GitNexus** (non-commercial), **CodeBoarding** (LLM-driven), **oh-my-mermaid** (LLM-driven) | 2025–2026 wave of "codebase map for AI agents" tools | tree-sitter or regex extraction, force graphs / 3D UIs, MCP tools like `shortest_path`, `blast_radius` | None does layered, rule-aware module views; the useful idea is **exposing graph queries to agents over MCP** |

## 3. Design inspiration from other ecosystems

- **dependency-cruiser** (JS/TS, MIT, 18.2.0, 2026-08-10) — the most complete design to steal from: rules are regex-on-path with capture-group substitution (`from.path: "^src/([^/]+)/"` → `to.pathNot: "^src/$1/"` expresses "slices may not cross-talk"); `forbidden`/`allowed`/`required` rules with severities; `circular` as a rule attribute with `via` filters; `moreUnstable` (Stable-Dependencies Principle) and `reachable`; **cruise once → JSON → many reporters** (`dot`, folder-level `ddot`, collapsed `archi`, `mermaid`, `d2`, `json`, `metrics` (Ca/Ce/I), `html`/`csv` dependency matrix, `x-dot-webpage` with hover highlighting); `--focus`, `--reaches`, `--affected <git rev>`, `--collapse`, baseline file for legacy violations; `depcruise-fmt` re-renders a saved JSON without re-analysing. Its cruise-result JSON is a good template for our model schema.
- **ArchUnit** (Java): `layeredArchitecture().layer("Service").definedBy("..service..").whereLayer("Service").mayOnlyBeAccessedByLayers("Controller")`, onion presets, `slices().should().beFreeOfCycles()`, `FreezingArchRule` (baseline), and `adhereToPlantUmlDiagram(...)` — a *diagram as an executable rule*, a nice V2 idea for the viewer (draw the intended structure, check the code against it).
- **deptrac** (PHP, MIT, 4.6.2, 2026-07): layers by collectors (directory/className/regex/boolean), `ruleset: Layer: [allowed]`, `skip_violations` baseline, "uncovered" reporting, formatters table/github-actions/junit/graphviz/mermaid/json.
- **go-arch-lint** (MIT, 2026-07) / **arch-go** (MIT, 2026-02): YAML components by path globs + `mayDependOn`, `check`/`mapping`/`graph`; compliance thresholds.
- **jQAssistant** (GPL): scan into Neo4j, rules as Cypher queries — the "graph database + query-defined rules" approach.
- **Nx project graph** (MIT): focus a project + proximity, group by folder, trace path start→end, "affected", composite (expandable) nodes, click an edge to see the files that create it — built on Cytoscape + dagre. Great UX reference for V2.
- **IntelliJ DSM** (commercial): dependency matrix with cycles in red and row-selection highlighting; **Structure101 / Sonargraph / Lattix / NDepend / CodeScene**: levelized structure maps, DSM partitioning, CQL-style rules, hotspots — feature ideas only (*not verified this session*).

## 4. Layout and rendering libraries (for the web viewer)

| Library | License / latest | Compound (nested) nodes | Edge routing | Notes |
|---|---|---|---|---|
| **ELK / elkjs** — https://github.com/kieler/elkjs | EPL-2.0; 0.12.0 (2026-07-17) | yes (`hierarchyHandling=INCLUDE_CHILDREN`) | orthogonal / polyline / splines | Layered (Sugiyama) + `partitioning.activate` with per-node `partitioning.partition` = forced horizontal bands (our layers). ~8 MB unpacked, Web-Worker friendly, Java-flavoured options, slows past a few thousand nodes (*rule of thumb*) |
| **Graphviz in the browser** — `@viz-js/viz` 3.29.0 (MIT, 2026-08-05, bundles Graphviz 15.1.1), `@hpcc-js/wasm-graphviz` 1.28.0 (Apache-2.0), `d3-graphviz` 5.6.0 (BSD-3, 2024) | — | `subgraph cluster_*`, `compound=true`, `newrank=true` + `rank=same` | splines with cluster avoidance (best-in-class) | Accepts DOT or JSON, returns SVG or JSON with coordinates; d3-graphviz animates transitions between drill-down levels; SVG DOM limits at thousands of nodes |
| **dagre** — `@dagrejs/dagre` 3.1.1 (MIT, 2026-08-08) | partial (sub-flows break when children connect outside) | polylines only | small and fast; `dagre-d3` renderer unmaintained (Mermaid uses a fork) |
| **React Flow** — `@xyflow/react` 12.11.5 (MIT, 2026-08-25) | yes (`parentId`, `extent: 'parent'`) | none built in (docs recommend elkjs) | nodes are React components → badges, buttons, metrics for free; you own layout + routing |
| **Cytoscape.js** 3.34.2 (MIT, 2026-08-25) + `cytoscape-elk` 2.3.0 / `cytoscape-fcose` 2.2.0 / `cytoscape-dagre` 4.0.1 | yes (native) | via layouts | canvas rendering scales further; stylesheet-driven; Nx's viewer is built on it |
| **Sigma.js** 3.0.3 + graphology (MIT) | no | no | WebGL, thousands of nodes; only for a whole-codebase overview |
| **vis-network** 10.1.2 (Apache-2.0/MIT) | clustering, not nesting | no | built-in hierarchical (tree-ish) layout; Python wrapper `pyvis` (stale, 2023) |
| **D3** 7.9 (ISC) | — | — | hierarchical edge bundling for a package-coupling overview; `d3-hierarchy` treemaps |
| **Mermaid** 11.17.2 (MIT) (+ `@mermaid-js/layout-elk`) | `subgraph` nesting | dagre/ELK | `maxEdges` default 500; export/docs format, not the viewer |
| **PlantUML** (GPL by default) / **Gephi** 0.11 (GPL) | — | — | export target / analysis app only |
| **DSM** | no maintained JS/Python widget found | — | — | trivial to render as a sorted adjacency table from our JSON (order rows by layer; cycles show above the diagonal) |

Python-side prototyping: `graphviz` 0.21 (MIT; needs `dot`), `pygraphviz` 2.0.1, `networkx` 3.6.1 (SCC, condensation, `topological_generations`), `pyvis` (stale), `ipysigma`/`dash-cytoscape` for notebooks, **Textual** 8.2.8 + **netext** 0.5.0 if a TUI is ever wanted.

## 5. What to reuse vs. build

| Layer of the tool | Decision | Rationale |
|---|---|---|
| Python import extraction | **Reuse grimp** | Verified correct on the fixture, fast, maintained, BSD; writing our own resolver would reproduce its edge cases |
| Graph algorithms (SCC, condensation, layering, shortest chains, metrics) | **Build** (small) on networkx or plain Python; grimp for chains/upstream/downstream | Tens of lines each; keeps the model language-agnostic |
| Model JSON schema | **Build**, modelled on arch-view EDN + dependency-cruiser cruise-result | One interchange format for viewer, checker, exports, agents |
| Rules file + checker | **Build** (DC-style `allowed` map first) | Agent-friendly, one line per component; later: import import-linter contracts / export tach config |
| Viewer | **Build** on Graphviz-WASM first (import-linter `explore` pattern), then ELK + React Flow if interactions demand it | Smallest possible front-end for the MVP; clean upgrade path |
| Exports | DOT/SVG via Graphviz, Mermaid text | Existing formats, zero new code beyond templates |
| Agent interface | **Build** CLI queries; MCP server in V2 | Idea validated by the 2025–26 wave of agent-oriented code-graph tools |
| Other languages | tree-sitter (or scip) extractors into the same JSON | Deferred by decision (LH: Python first) |

## 6. Sources

Python tools: https://github.com/python-grimp/grimp · https://grimp.readthedocs.io/ · https://github.com/seddonym/import-linter · https://import-linter.readthedocs.io/ (contract types, custom contracts, `ui/`, release notes) · https://github.com/tach-org/tach · https://docs.gauge.sh/ · https://github.com/astral-sh/ruff/discussions/20699 · https://github.com/thebjorn/pydeps · https://pylint.readthedocs.io/en/stable/additional_tools/pyreverse/ · https://github.com/zyskarch/pytestarch · https://github.com/LukasNiessen/ArchUnitPython · https://github.com/vashkatsi/deply · https://github.com/jwbargsten/pytest-archon · https://github.com/mgedmin/findimports · https://github.com/google/importlab · https://github.com/ronaldoussoren/modulegraph · https://github.com/Technologicat/pyan · https://github.com/scottrogowski/code2flow · https://github.com/osprey-oss/deptry · https://docs.astral.sh/ruff/rules/banned-api/ · https://github.com/sourcegraph/scip-python · https://github.com/sourcegraph/scip · https://github.com/tree-sitter/tree-sitter-python · https://github.com/chio-labs/fensu · https://github.com/repowise-dev/repowise · https://github.com/ludo-technologies/pyscn · https://pypi.org/project/pylint-clean-architecture/ · https://pypi.org/project/arch-lint/ · https://roman.pt/posts/python-architecture-linter/ · PyPI JSON API for release dates.

Viewers and design references: https://github.com/glato/emerge · https://github.com/MaibornWolff/codecharta · https://github.com/CoatiSoftware/Sourcetrail · https://github.com/petermost/Sourcetrail · https://github.com/multilang-depends/depends · https://github.com/structurizr/structurizr · https://docs.structurizr.com/eol · https://github.com/likec4/likec4 · https://likec4.dev/tooling/react/ · https://github.com/sverweij/dependency-cruiser (doc/rules-reference.md, doc/cli.md) · https://nx.dev/features/explore-graph · https://github.com/pahen/madge · https://www.archunit.org/userguide/html/000_Index.html · https://github.com/deptrac/deptrac · https://github.com/fe3dback/go-arch-lint · https://github.com/arch-go/arch-go · https://github.com/jQAssistant/jqassistant · https://www.jetbrains.com/help/idea/dsm-analysis.html · https://github.com/braedonsaunders/codeflow · https://github.com/safishamsi/graphify · https://github.com/DeusData/codebase-memory-mcp · https://github.com/abhigyanpatwari/GitNexus · https://github.com/CodeBoarding/CodeBoarding · https://github.com/oh-my-mermaid/oh-my-mermaid.

Layout/rendering: https://github.com/kieler/elkjs · https://eclipse.dev/elk/reference/options/org-eclipse-elk-partitioning-partition.html · https://github.com/dagrejs/dagre · https://github.com/mdaines/viz-js · https://viz-js.com/api/ · https://github.com/hpcc-systems/hpcc-js-wasm · https://github.com/magjac/d3-graphviz · https://graphviz.org/docs/attrs/newrank/ · https://js.cytoscape.org/ · https://github.com/cytoscape/cytoscape.js-elk · https://reactflow.dev/learn/layouting/layouting · https://reactflow.dev/learn/layouting/sub-flows · https://github.com/jacomyal/sigma.js · https://visjs.github.io/vis-network/docs/network/layout.html · https://mermaid.js.org/config/schema-docs/config.html · https://plantuml.com/license · https://gephi.org/ · https://dsmsuite.github.io/about.html · npm registry metadata for versions.

Uncle Bob's tools: https://github.com/unclebob/arch-view · https://github.com/unclebob/dependency-checker · https://github.com/unclebob/empire-2025 · https://github.com/unclebob/swarm-forge · https://github.com/unclebob/crap4java · https://github.com/unclebob/crap4clj · https://github.com/unclebob/crap4go · https://github.com/unclebob/Acceptance-Pipeline-Specification.
