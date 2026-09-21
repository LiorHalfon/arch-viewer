# Recommended approach and roadmap

This is the proposal to start from in Claude Code. It follows Bob's advice (43:52): don't port his Clojure tools, build the equivalent for our stack, using the best existing pieces.

## 1. Architecture of the tool (one core, several faces)

```
archview/
  extract/
    python.py        # grimp -> RawGraph: modules, package tree, imports with file:line, abstract flags
  model/
    graph.py         # language-agnostic: Tree, Edge, View (aggregation for a root), JSON (de)serialisation
    cycles.py        # SCCs, cycle listing, cycle-breaker edges (arch-view style ranking)
    layers.py        # topological layering of the condensation DAG (stable, name-sorted)
    metrics.py       # fan-in/out, I, A, D, zones (dependency-checker formulas)
  rules/
    config.py        # archview.toml / [tool.archview] loading + validation with helpful errors
    check.py         # actual edges vs rules -> Violations (component, count, examples, remedy hint)
    init.py          # infer starter rules from the current graph; baseline support later
  cli.py             # archview serve | check | init | graph | metrics | why | deps | rdeps | cycles
  server/            # tiny local HTTP server: /api/view?root=..., /api/source?module=..., static UI
  ui/                # static web UI (Graphviz-WASM first), no build step for the MVP
```

Rules of the house: `extract` is the only Python-aware package; `model` and `rules` know nothing about Python; `cli`/`server`/`ui` are presentation. The repo commits its own `archview.toml` and `archview check` runs in its CI — the tool must pass its own checker (requirement N8).

## 2. Key technical choices

### Extraction: grimp
`grimp.build_graph(package, include_external_packages=False, exclude_type_checking_imports=<config>, cache_dir=<.archview_cache>)`. Walk `graph.modules`, `find_children`, `find_modules_directly_imported_by`, and `get_import_details` to build our own RawGraph. Abstractness needs a small extra pass over each module's AST (`typing.Protocol`, `abc.ABC`, `ABCMeta`, `@abstractmethod`) — Python's `ast` is enough since we already have file paths. Dynamic imports: a second cheap `ast` pass that flags `importlib.import_module(...)` / `__import__(...)` calls as warnings (or shell out to `ruff analyze graph --detect-string-imports` in a later version).

Requirement to satisfy before trusting it: the fixture package in `tests/fixtures/` covers relative imports, re-exports, function-level imports, `TYPE_CHECKING`, a dynamic import and a cycle, with golden JSON output.

### Model JSON (the interchange format)
Sketch (final schema to be written as a JSON Schema file in the repo):

```json
{
  "schema": 1, "language": "python", "project": "tiny_tale", "generated_at": "...",
  "nodes": [
    {"id": "tiny_tale.services", "parent": "tiny_tale", "kind": "package", "file": null,
     "abstract": false, "module_count": 14},
    {"id": "tiny_tale.services.pricing", "parent": "tiny_tale.services", "kind": "module",
     "file": "src/tiny_tale/services/pricing.py", "abstract": false}
  ],
  "imports": [
    {"importer": "tiny_tale.api.routes", "imported": "tiny_tale.services.pricing",
     "file": "src/tiny_tale/api/routes.py", "line": 12, "text": "from tiny_tale.services import pricing",
     "type_checking": false, "dynamic": false}
  ],
  "warnings": [{"kind": "dynamic_import", "file": "...", "line": 40, "text": "importlib.import_module(name)"}]
}
```

Everything else — views per root, aggregated edges with counts, cycles, layers, metrics, violations — is derived from this and can be cached alongside it. `archview graph --root X --json` returns the derived view for one root (this is what the spike prints today).

### Rules file: `archview.toml` (DC-style, agent-friendly)

```toml
[archview]
package = "tiny_tale"                     # top-level package to analyse
source_roots = ["src"]
exclude = ["**/tests/**", "**/migrations/**"]
type_checking_imports = "ignore"          # or "include"
fail_on_violations = true
fail_on_cycles = true

[archview.allowed]                        # component -> components it may import
api      = ["services", "domain", "config"]
services = ["domain", "infra", "config"]
infra    = ["domain", "config"]
domain   = ["config"]
config   = []
tests    = "all"

[[archview.forbidden]]                    # optional, checked even if implied by allowed
from = "domain"
to = "infra"

[[archview.exceptions]]                   # module-level exemptions, always with a reason
importer = "tiny_tale.services.legacy_export"
imported = "tiny_tale.api.schemas"
reason = "to be removed in TT-123"

[archview.components]                     # optional explicit mapping when sub-packages are not the right unit
# "adapters" = ["tiny_tale.db.*", "tiny_tale.http_clients.*"]
```

Components default to the direct sub-packages of `package`. A component may always depend on itself. `archview init` writes the `allowed` table from the current graph (plus the two fail flags) so adoption is one command; the human then *removes* the edges that should not exist and the agents get failures until the code matches the design — exactly Bob's loop (27:44–28:06).

### Checker output (what an agent reads)

Text:
```
VIOLATION domain -> infra (3 imports) not allowed by [archview.allowed].domain
  src/tiny_tale/domain/pricing.py:4  from tiny_tale.infra.db import Session
  src/tiny_tale/domain/orders.py:9   from tiny_tale.infra.cache import cache
  hint: domain is higher-level than infra; invert the dependency (define a port/Protocol in domain,
        implement it in infra) or move the code that needs infra out of domain.
CYCLE services -> infra -> services (2 edges)
2 problems. exit 1
```
JSON: the same as a list of objects (`kind`, `rule`, `from`, `to`, `count`, `examples[]`, `hint`), stable ordering. No colours, no banners in JSON mode.

### Viewer: Graphviz-WASM first, ELK + React Flow if needed
MVP: `archview serve` starts a local server (stdlib `http.server` or FastAPI — import-linter uses FastAPI + uvicorn) that serves `/api/view?root=` (derived view JSON incl. a ready-made DOT string) and `/api/source?module=`. The static page renders DOT with `@viz-js/viz` (vendored, MIT), wires click handlers on node ids (drill-down = fetch new view), keeps a breadcrumb stack with scroll positions, shows the cycles list under the diagram, and opens source in a side panel (`<pre>` + highlight.js is enough; CodeMirror 6 later). Layering: emit `{rank=same; ...}` per layer and `newrank=true`, colour cyclic edges red, package nodes as UML component shapes (Graphviz `shape=component`).

Upgrade path (V2 interactions: focus, collapse in place, hover popups, metrics badges): React + `@xyflow/react` with elkjs layered layout (`hierarchyHandling=INCLUDE_CHILDREN`, `partitioning` per layer, orthogonal edges) — same `/api` JSON, so the server does not change. Alternative to evaluate in one afternoon: LikeC4's Builder API + `<ReactLikeC4 />` for a ready-made drill-down viewer.

### Agent integration
`archview why A B` (direct imports, else the shortest chain, computed on the model rather than with grimp's `find_shortest_chains` so exclusions apply; ADR 0009), `archview deps M` / `archview rdeps M` (upstream/downstream), `archview cycles`, `archview check --format json`. A documented pre-commit / Claude Code hook (`archview check --stop-hook`). A paragraph for the target repo's `CLAUDE.md`: "Before handing off, run `archview check`; if it fails, restore the dependency direction (invert / interface / split) — never edit `archview.toml` to make it pass without asking." Optional, not scheduled: a small MCP server (`archview mcp`) exposing `get_view`, `check`, `why`, `deps`, built only when an ADR 0005 trigger fires.

## 3. Roadmap (each milestone is a few Claude Code sessions)

| Milestone | Deliverable | Done when |
|---|---|---|
| **M0 — spike** (done, in `spike/`) | grimp → aggregated edges → cycles → layers → JSON/DOT, plus a 30-line allowed-map checker | Runs on import-linter's own package; see `spike/example-importlinter.svg` |
| **M1 — core model + CLI `graph`** | Package skeleton (`uv`, `pyproject`, ruff, pytest), `extract/python.py`, `model/*`, JSON schema, fixture project with golden outputs, `archview graph --root X [--json|--dot]` | Golden tests pass; runs on `tiny-tale-backend` in < 10 s |
| **M2 — checker** | `archview.toml` loader, `check` (text + JSON, exit codes, hints), `init`, exclusions, self-check in CI | `archview init` + `check` pass on `tiny-tale-backend` with the rules kept outside that repo (`--config`); one intentionally removed rule fails the check with `file:line` and exit 1; the CLAUDE.md paragraph is written (`docs/06`). Adopting it inside `tiny-tale-backend` is left to its owner (decided 2026-09-16). Self-check runs in pytest until there is CI |
| **M3 — viewer MVP** | `serve` + static UI: layered boxes, edge counts, drill-down with back, source panel, cycles list | Can navigate `tiny-tale-backend` top → package → file without reading a listing |
| **M4 — depth** | Abstractness + UML arrowheads, metrics + zones, violations overlay, TYPE_CHECKING/dynamic-import handling, SVG/Mermaid export, reanalyze/watch, filters (tests/externals/focus) | Requirements V7–V12, A4–A5, A9–A10, C7–C9 (done 2026-09-16, ADR 0008; V10 collapse-in-place deferred to the ELK/React Flow step) |
| **M5 — agents** (done) | `why`/`deps`/`rdeps`/`cycles`, `check --stop-hook`, the query paragraph for CLAUDE.md (ADR 0009; baseline, JSON and the snippet came with M2/M4; MCP server optional, see ADR 0005) | Claude Code answers "why does X depend on Y" via the CLI; check runs in the hand-off loop |
| **M6 — second language** (done) | TypeScript extractor through the TS compiler API (ADR 0010), same JSON (schema 3) | Viewer/checker work unchanged on storygenerator (done 2026-09-17) |
| **M7 — outside rules** (done) | A rule can name a package outside the project: `[archview.externals]` allow-list, `from = "*"`, stdlib rejected at parse time, `forbidden`/`exceptions` widened, viewer draws a failing outside edge without `--externals`, `init --externals` (ADR 0011) | `archview check` fails a forbidden outside import with its file:line, passes on this repo with a live outside rule (`model` -> `grimp`) in its own `archview.toml` (done 2026-09-20) |
| **M8 — workspace mode** (done) | `[archview.workspace]` federates several packages' own `Project`s (`src/archview/workspace.py`); a cross-package import is attributed to a sibling via M7's outside edges and each package's aliases; `check`/`graph`/`cycles` run over the whole workspace by default and drill into one with `--package`; the viewer's top level is the packages (ADR 0012) | `archview check` at a workspace root checks every package plus the rules between them with one exit code, on Python and TypeScript packages alike; a repo without `[archview.workspace]` is unchanged (done 2026-09-20) |
| **M9 — public surface** (done) | A package declares `public` in its own rules file; a cross-package import is resolved to the component it really reaches (a grimp pass over the sibling packages for Python, `Import.resolved` for TypeScript, model schema 4) and checked against that contract; qualified targets in the workspace tables; published components drawn on the package boundary (ADR 0013) | A plugin reaching the core's private domain fails `archview check` with file and line; a workspace with no `public` anywhere behaves exactly as on v0.3 (done 2026-09-22) |

Suggested order of work inside M1–M3: tests and fixture first (Bob's PROJECT_NOTES process), then the smallest vertical slice that reaches the browser, then iterate — a story or two, look at the result, reorganise (35:46–41:36).

## 4. Risks and how to handle them

- **grimp requires the package to be locatable** (it uses the import system to find files, without executing them). Run the CLI from the project root with `source_roots` on `sys.path`; document the `PYTHONPATH`/`uv run` incantation; test with `src/` layouts.
- **Re-exports hide dependencies** (`from tiny_tale.services import Pricing` where `Pricing` is re-exported from `services.pricing`). Acceptable at component level (edge still lands on the right component); revisit with scip-python only if module-level precision is needed.
- **Big flat packages** (dozens of modules in one directory) make one view too dense. Mitigate with explicit `[archview.components]` mapping and the auto-collapse rule (V14).
- **Layout churn** between runs makes diffs noisy. Deterministic ordering everywhere (N1); Graphviz is deterministic for identical DOT.
- **Scope creep toward call graphs / class diagrams.** Keep out of scope (section 9 of the requirements); point to pyan3/pyreverse.
- **Licensing.** grimp/import-linter BSD, viz.js MIT, ELK EPL-2.0, React Flow MIT, networkx BSD. Avoid GPL renderers (pyreverse/pylint, PlantUML default, Gephi) in the runtime path.
