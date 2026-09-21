# Requirements — Architecture Viewer + Dependency Rules Checker (Python and TypeScript)

Status: draft v1, 2026-08-30. Derived from the video (`01-video-notes.md`, timestamps in parentheses), Bob's real tools (`03-reference-uncle-bob-tools.md`, marked AV = arch-view, DC = dependency-checker), and Lior's decisions (marked LH). Priority: **MVP** = needed for the first useful version, **V2** = next, **Later** = idea parked.

## 1. Vision

A local, deterministic tool that lets a human see the modular structure of a Python code base and the direction of its dependencies at any level of detail, and lets AI coding agents be *held* to a declared dependency structure they cannot argue with. It fits a workflow where agents write most of the code: the human does the strategic work (partitioning, dependency direction) by looking at the picture (26:06–27:31), and the checker keeps the agents inside those lines (27:31–28:06).

Two faces, one model:

- **Viewer** — interactive, drill-down UML-ish diagram of packages/modules and where dependencies run.
- **Checker** — a spec file that says which components may depend on which, and a fast pass/fail command for CI, pre-commit hooks and agent loops.

Both read the *actual* imports from the source. Guidance never overrides reality; it is compared against it (AV: "prioritizes actual dependencies").

## 2. Users and how they use it

| User | Job to be done | Consequence for the tool |
|---|---|---|
| The human architect (Lior) | After the agents finish a story or two, look at the structure, decide how modules should be partitioned and how they should communicate, then write that down as rules (37:50–38:13). Also: learn an unfamiliar code base quickly (49:24). | Fast to launch, zero setup for the default case, drill-down in a few clicks, cycles and violations impossible to miss. |
| AI coding agents (Claude Code and friends) | (a) Obey the rules: run the checker, read the failures, fix them by inverting a dependency / inserting an interface / splitting a module (27:48). (b) Answer questions about the structure with ground truth instead of guesses (26:18). | Non-zero exit codes; terse, actionable, machine-readable output with `file:line`; a query CLI (optionally an MCP server later) so agents ask the tool instead of the human. |
| CI / pre-commit | Block merges that break the declared architecture. | Deterministic, quick (seconds), no network, no code execution, stable output. |

## 3. Glossary

- **Module** — one Python file (`app/services/pricing.py` → `app.services.pricing`). Leaf in the tree.
- **Package** — a directory with modules (`app.services`). Non-leaf. Nested arbitrarily deep.
- **Root** — the package currently being viewed; its direct children are the boxes on screen.
- **Component** — an architectural unit named in the rules file. By default the direct children of the project's top-level package (DC: "second namespace segment"), optionally defined explicitly by patterns (AV `:component-rules`).
- **Dependency / edge** — module A imports something from module B (statically). Aggregated edges between children of the root carry a count and the list of concrete module-level imports behind them.
- **Dependency direction** — edges point from the importer to the imported. Bob's rule: low-level (near IO) depends on high-level (far from IO), never the reverse (swarm-forge architect prompt).
- **Layer** — the vertical rank a box gets from the topological order of the dependency graph (AV). Not to be confused with a *declared* layer in a rules file.
- **Cycle** — a strongly connected set of two or more nodes at the current level.
- **Abstract module** — a module that defines an abstraction (`typing.Protocol`, `abc.ABC`/`ABCMeta`, `@abstractmethod`) (AV/DC: `defprotocol`, `defmulti`).
- **Violation** — an actual dependency the rules do not allow (or forbid), or a cycle when cycles are forbidden.

## 4. Functional requirements — analysis core (shared by viewer and checker)

| ID | Requirement | Pri | Source |
|---|---|---|---|
| A1 | Build the module-level import graph of a Python project **statically** (no importing/executing the target code), from `import x`, `from x import y`, relative imports, imports nested in functions/classes, and `__init__.py` re-exports attributed to the package. | MVP | AV, LH |
| A2 | Resolve `from pkg import name` correctly whether `name` is a submodule or an attribute (the edge goes to `pkg.name` only if it is a module). | MVP | research (pyreverse/pytestarch get this wrong) |
| A3 | Ignore third-party and stdlib imports by default; optionally include them as squashed nodes ("externals") for a boundary view. | MVP / V2 | AV (project namespaces only) |
| A4 | Treat `if TYPE_CHECKING:` imports as configurable: excluded by default from rule checking, visible in the viewer as a distinct edge style. | V2 | research (grimp/tach offer the toggle) |
| A5 | Detect dynamic imports (`importlib.import_module("...")`, `__import__`) on a best-effort basis and report them as **warnings**, never silently drop them. | V2 | DC (dynamic lookups → warnings) |
| A6 | Represent the package tree (root → packages → modules) so any node can be a root; aggregate edges between the children of any root from all imports in their subtrees, with counts and the underlying module-level imports (`importer`, `imported`, `file`, `line`, source text). | MVP | AV drill-down; 27:12 |
| A7 | Find cycles at every level (strongly connected components among the children of a root) and mark nodes and edges that take part in them. | MVP | AV legend; 27:54 |
| A8 | Compute layers: remove a minimal (or good-enough) set of cycle-causing edges, topologically order the rest, high-level importers at the top, most depended-upon at the bottom; peers side by side; removed edges still shown. Deterministic ordering (stable sort by name). | MVP | AV layer rationale |
| A9 | Mark abstract modules/packages (see glossary) and classify edges as `direct` or `abstract` (target is abstract). | V2 | AV/DC |
| A10 | Compute Bob's component metrics: fan-in, fan-out, instability `I`, abstractness `A`, distance `D = |A + I − 1|`, zone (healthy / pain / useless) with a configurable threshold (default 0.3). | V2 | DC |
| A11 | Exclusions: configurable directories/patterns (tests, migrations, generated code) and ignored components. | MVP | DC `:ignored-components` |
| A12 | Export the full model as JSON (tree, edges with details, cycles, layers, components, metrics, violations) — the single interchange format the viewer, the checker, exports and agents all consume. | MVP | AV `--out/--in-edn`, `--no-gui` |
| A13 | Language-agnostic model: nothing in the JSON schema or the viewer is Python-specific; a second extractor (TypeScript for the frontend repo) must be pluggable later. | MVP (design) / M6 (impl, ADR 0010) | LH |
| A14 | Speed: full analysis of a few thousand modules in seconds; per-view aggregation instantaneous. Optional on-disk cache. | MVP | 16:18 (checks must not make agents slower than humans) |
| A15 | TypeScript extractor: tsc's own resolution (paths, extends, references), ids that keep file extensions split by '/', type-only and lazy flags, unresolved-import warnings. Needs Node and the project's installed typescript. | M6 | LH |

## 5. Functional requirements — viewer

| ID | Requirement | Pri | Source |
|---|---|---|---|
| V1 | Show the children of the current root as UML component-style boxes, laid out in layers (A8), with the package name and module count. | MVP | 27:03–27:10; AV |
| V2 | Show where dependencies run between those boxes: direction and count. AV uses top/bottom "triangles" plus hover popups instead of drawing every arrow; the Python version may draw arrows for small views and fall back to indicators when the view is dense. | MVP | 27:10; AV legend |
| V3 | Inspect an edge: list the concrete module→module imports behind it with `file:line`, click to open the source at that line. | MVP | AV hover popup; agents need the same data |
| V4 | Drill down: click a package → it becomes the root. Breadcrumb / back button restores the previous root **and its scroll/zoom position**. Unlimited depth. | MVP | 27:12–27:25; AV navigation |
| V5 | Leaf → code: click a module → its source opens in a panel (read-only, syntax-highlighted, import lines highlighted). | MVP | 27:16–27:20 |
| V6 | Cycles are unmissable: red names for subtrees containing a cycle, red edges/indicators for cyclic dependencies, and a list of cycles in `a → b → c → a` form for the current view. | MVP | AV legend |
| V7 | Violations overlay: edges that break the rules file are styled distinctly (e.g. red dashed) and listed; optionally show allowed-but-unused rules. | V2 | 27:31; AV V2 "guidance vs actual diff" |
| V8 | Abstract modules/packages are visually distinct (AV: green), and edges to abstractions use the UML closed-triangle arrowhead. | V2 | AV legend |
| V9 | Reanalyze: a button (and/or file watching) rescans and redraws the current view without losing navigation state. | V2 | AV `Reanalyze` |
| V10 | Filters and focus: hide tests/externals, focus a node and its neighbours, "what reaches X" (impact), collapse/expand packages in place. | V2 | dependency-cruiser `--focus/--reaches`; Nx graph |
| V11 | Metrics panel per node (A10), with zone colouring. | V2 | DC |
| V12 | Export the current view as SVG/PNG (for PRs and docs) and as Mermaid/DOT (for markdown). | V2 | AV V2 "export and CI" |
| V13 | Launch with one command from the project root (`archview .` / `uv run archview`), opens in the browser, works offline, no accounts, no telemetry. | MVP | LH (Claude Code workflow) |
| V14 | Handles a view of a few hundred boxes interactively; larger views are automatically collapsed to packages. | MVP | — |
| V15 | File drawer: a hideable panel on the left lists the packages (folders) and modules (files) under the current root, with a `..` row to go up. Clicking a folder makes it the root, clicking a file opens its source; folders expand in place. Follows Hide tests. | V2 | LH |

## 6. Functional requirements — checker

| ID | Requirement | Pri | Source |
|---|---|---|---|
| C1 | A small, human- and agent-writable **rules file** in the repo (working name `archview.toml`, or a `[tool.archview]` table in `pyproject.toml`) declaring: `allowed` dependencies per component (with `"all"` wildcard), `forbidden` edges, `exceptions` at module level, `ignored` components, `fail_on_violations`, `fail_on_cycles`. | MVP | 27:34–27:46; DC config |
| C2 | Components default to the direct sub-packages of the project package; optional explicit mapping (pattern → component) for flat layouts or grouping. | MVP | DC discovery; AV `:component-rules` |
| C3 | `archview check` compares actual aggregated edges with the rules and exits non-zero on any violation (and on cycles when `fail_on_cycles`). Self-dependencies are always allowed. | MVP | 27:48; DC |
| C4 | Every violation names the rule, the components, the count, and at least one concrete `importer_module:line → imported_module`, plus a one-line remedy hint (invert the dependency, introduce an interface owned by the higher-level module, split the module, move the code). | MVP | 27:54–28:00; swarm-forge architect prompt |
| C5 | Output formats: coloured text for humans, `--format json` for agents/CI, optionally GitHub Actions annotations. | MVP (text+json) / V2 | DC `--format edn`, deptrac formatters |
| C6 | `archview init` infers a starter rules file from the current dependencies (like DC `--init` / tach `sync`), so adoption on an existing repo takes one command; re-running with `--force` regenerates. | MVP | DC `--init` |
| C7 | Baseline mode: record known violations so legacy debt does not block, while any *new* violation fails. | V2 | dependency-cruiser / deptrac baselines |
| C8 | Optional ordered `layers` rule ("api → services → domain → infra…") and `independent` sibling rules as sugar over allowed/forbidden. | V2 | import-linter contracts; ArchUnit |
| C9 | Metrics report with optional thresholds (e.g. fail if a component enters the zone of pain). | V2 | DC metrics |
| C10 | Runs in < a few seconds on a typical service repo so it can sit in a pre-commit hook and in the agent's fix-it loop. | MVP | 16:52–17:25 |
| C11 | Config evolution: unknown/legacy keys produce a clear error with a hint, not silent acceptance. | V2 | DC |
| C12 | `allowed`/`forbidden`/`exceptions` can name a package outside the project (a PyPI/npm dependency, or a workspace sibling before M8 tells them apart) via a new `[archview.externals]` allow-list; `forbidden` needs no new syntax. A stdlib target is a config error, not a silent no-op. | MVP (M7) | GitHub issue #1; ADR 0011 |
| C13 | A `[archview.workspace]` table at a repo's root lists several packages (Python and/or TypeScript), each opened with its own rules file when it has one; `check` runs every package's own check plus a declared `allowed`/`forbidden`/`exceptions` table for the imports *between* them, with one exit code. A cross-package import is attributed to its sibling by the M7 outside name it already produces. | MVP (M8) | GitHub issue #2; ADR 0012 |
| C14 | A package declares its contract with `public` in its own rules file; a sibling may reach only those components, and the workspace tables accept qualified `package.component` targets. The component an import reaches is resolved, not guessed: the sibling packages are analysed together for Python, and `Import.resolved` carries tsc's resolution for TypeScript. A grant naming an unpublished component is a config error; an import that cannot be placed is reported, never assumed public. | MVP (M9) | GitHub issue #4; ADR 0013 |
| C15 | `check` says what it is not checking. `type_checking_imports` defaults to `"include"`, and the key is a `ConfigError` where it cannot take effect (a workspace root's bare `[archview]` table). A `[archview.externals]` table that covers one component and not a neighbour reaching the same package says so, by name (`partial_externals`). `externals_undeclared = "error"` closes the table, failing a component that reaches outside without a key (`undeclared_externals`). A `source_roots` entry that contributes no modules to the package says so (`empty_source_root`). | MVP (M10) | GitHub issues #5, #8, #10; ADR 0014 |

## 7. Agent integration

| ID | Requirement | Pri | Source |
|---|---|---|---|
| G1 | A query CLI agents can call: `archview graph --root pkg --json`, `archview why A B` (the direct imports, else the shortest import chain), `archview deps M` / `archview rdeps M` (direct dependencies / dependents), `archview cycles`. | MVP (built in M5, ADR 0009) | 26:18–26:32 (interrogating agents about structure) |
| G2 | Optional: an MCP server exposing the same queries, for agents without a shell or if repeated CLI queries prove too slow. Claude Code uses the G1 CLI. See ADR 0005. | Later | LH (Claude Code workflow) |
| G3 | A ready-made snippet for `CLAUDE.md` / a hook so that `archview check` must pass before an agent hands off; checker messages are written to be read by an agent with a small context budget (terse, no decoration in `--format json`). | MVP | 12:33–15:14 (deterministic tools beat steering) |
| G4 | The checker never auto-fixes; it reports. The agent (or human) decides how to restore the dependency direction. | MVP | 27:48–28:06 |

## 8. Non-functional requirements

- **N1 Deterministic.** Same source → byte-identical JSON and identical layout; sorting is by name everywhere ties exist. Required for CI diffs and for agents.
- **N2 Static only.** Never import or execute the analysed project's own source (safety, speed, no side effects). One carve-out, from M6: to read TypeScript, archview loads and runs the **compiler** from the analysed repo's `node_modules` (`typescript`), because tsc's resolution is what makes a tsconfig mean what it says. The repo's sources are parsed, never executed, but analysing an untrusted repo does run that repo's installed `typescript`.
- **N3 Local & offline.** No network calls; no hosted viewer (unlike tach's `--web`).
- **N4 Python target.** Analyse Python 3.11+ code; the tool itself runs on 3.12+. Install with `uv tool install` / `uvx` or as a dev dependency.
- **N5 Permissive dependencies only** (MIT/BSD/Apache/EPL-2.0 for ELK); no GPL/AGPL/non-commercial libraries in the runtime path.
- **N6 Tested the way Bob builds tools**: unit tests for the core, a small fixture project with relative imports, re-exports, `TYPE_CHECKING` imports, a dynamic import and a cycle; golden JSON tests; high coverage; small functions (his notes: cyclomatic complexity ≤ 5 where practical).
- **N7 Dogfooding.** Run it on `tiny-tale-backend` from the first milestone; the fixture for the viewer should be a real repo, read-only, like Bob's empire-2025.
- **N8 Clean separation** inside the tool itself: extraction (Python-specific) → model (language-agnostic) → analysis (layers, cycles, metrics, rules) → presentation (CLI, JSON, DOT, web). The tool must pass its own checker.

## 9. Out of scope (for now)

Call graphs and class diagrams (pyan3/pyreverse territory), runtime tracing, git history/hotspots (CodeCharta/CodeScene territory), multi-repo graphs, LLM-generated descriptions of components (CodeBoarding does this; not deterministic), auto-refactoring.

## 10. Open decisions for the Claude Code sessions

1. **Viewer stack**: Graphviz-in-the-browser (fastest, matches import-linter's `explore`) vs React + ELK + React Flow (more app-like, better for V2 interactions). See `05-approach-and-roadmap.md`.
2. **Rules format**: a minimal `allowed`-map (DC style, agent-friendly) vs adopting import-linter contract semantics so existing `.importlinter` files work. Recommendation: DC-style first, import-linter import/export later.
3. **Edge granularity for `__init__` re-exports**: attribute to the package (grimp default) vs resolve to the defining module (needs symbol resolution, e.g. scip-python). Start with grimp's behaviour; revisit if re-exports hide real dependencies.
4. **Name**: working name `archview` (package/CLI). Bob's tool is `arch-view`; pick something distinct before publishing.
5. **Component definition for flat packages**: default = sub-packages; decide on the pattern syntax for explicit components (glob vs regex).

## 11. Acceptance for the MVP (definition of done)

- `uvx archview .` on `tiny-tale-backend` opens a browser view of the top-level packages in layers, with dependency counts, drill-down to files, source panel, and any cycles listed — in under 10 seconds from cold.
- `archview init` writes a rules file that `archview check` passes; deleting one allowed edge makes `archview check` fail with exit code 1 and a message pointing at a `file:line`.
- `archview check --format json` output is stable across runs and parseable by a script.
- `archview graph --root tiny_tale --json` and `archview why a.b c.d` work from the command line.
- The tool's own package passes `archview check` with a rules file committed in the repo.

## 12. Implementation status (2026-09-22, after M10)

| Area | Built | Not yet |
|---|---|---|
| Analysis | A1–A15. A3 externals are opt-in boxes. A9 "abstract" is defined in ADR 0008 | — |
| Viewer | V1–V9, V11–V13, V15. V10: hide tests, show externals, focus neighbours, what reaches / is reached. A workspace root's top level is the packages, drilling into each (ADR 0012) | V10 collapse/expand in place (needs the ELK step); V14 auto-collapse of very large views |
| Checker | C1–C4, C6–C15. C5 text + JSON | C5 GitHub Actions annotations |
| Agents | G1 `graph`, `why`, `deps`, `rdeps`, `cycles`; G3 (docs/06, `check --stop-hook`); G4 | G2 is optional (ADR 0005); transitive `deps`/`rdeps` |

Clarified during M4 (ADR 0008): `layers` peers listed together are independent of
each other; TYPE_CHECKING imports are drawn but not checked by default; a baseline
records imports, not line numbers.

Clarified during M5 (ADR 0009): the queries run on the filtered model, not on grimp;
`why` prefers direct imports over a chain; `deps` leaves out third-party packages
unless asked.

M6 (2026-09-17): TypeScript through the compiler API (ADR 0010); accepted on storygenerator.

M9 (2026-09-22): a package publishes a contract its siblings are checked against
(C14, ADR 0013); the model JSON is schema 4, carrying the resolved target of an
import so TypeScript can say which component a cross-package import reaches.

M10 (2026-09-22): archview says what it is not checking (C15, ADR 0014), closing three
issues that all reported the same failure: a rule that reads as enforced but is not.
`type_checking_imports` now defaults to `"include"`, a breaking change landed while
v0.4.0 is untagged; setting it where it cannot take effect is a `ConfigError`.
`[archview.externals]` gets a `partial_externals` notice when it covers a package for
one component and not a neighbour reaching the same package, and an opt-in closed mode
(`externals_undeclared = "error"`) that fails an undeclared reacher outright. A
`source_roots` entry that contributes no modules to the package gets an
`empty_source_root` notice.

M7 (2026-09-20): rules can name a package outside the project (C12, ADR 0011);
`[archview.externals]`, `from = "*"`, a viewer overlay for the failing edge, and
`archview init --externals`. This repo's own rules gain a live outside rule (`model`
must not reach `grimp`).

M8 (2026-09-20): workspace mode (C13, ADR 0012). A `[archview.workspace]` table
federates several packages' own `Project`s rather than merging them into one `Model`;
a cross-package import is an M7 outside edge whose name joins one of a sibling's
aliases (its top-level module name; its `package.json` name, scoped or not; a
TypeScript `../` import resolved back to a package directory). `check`, `graph` and
`cycles` run over the whole workspace by default and drill into one package with
`--package`; the viewer's top level is the packages.
