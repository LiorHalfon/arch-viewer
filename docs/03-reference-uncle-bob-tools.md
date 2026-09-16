# Reference design — Uncle Bob's actual tools

The two tools Bob describes in the video are public. They are Clojure-only, have no LICENSE file (so: read for ideas, do not copy code), and Bob's own advice (43:52) is to point your agents at them and build your own. This document captures what they do so the Python version can start from a proven design rather than from scratch.

Both were cloned and read on 2026-08-30.

| Tool | Repo | Language | Last commit seen | Size |
|---|---|---|---|---|
| Architecture viewer | https://github.com/unclebob/arch-view | Clojure + Quil (Processing) desktop window | 2026-03-20 | ~3.2k lines + specs |
| Dependency checker | https://github.com/unclebob/dependency-checker | Clojure CLI (also runs under Babashka) | 2026-06-17 | small |
| Real-world usage | https://github.com/unclebob/empire-2025 (`dependency-checker.edn`, `deps.edn` aliases `:check-dependencies`, `:arch-view`) | Clojure game, ~760 files | 2026-06-19 | — |
| Agent orchestration | https://github.com/unclebob/swarm-forge (`six-pack` branch: `swarmforge/roles/architect.prompt`, `constitution/articles/engineering.prompt`) | Clojure/Babashka + tmux | active | — |

## 1. arch-view (the viewer)

### What it computes

1. **Dependency discovery.** Scans source files under configured source paths (default `src`), reads each file's `ns` form, extracts `:require` dependencies between *project* namespaces (externals ignored), and builds a namespace → namespace graph. It also records the source file per namespace and marks namespaces that define polymorphism (`defprotocol`, `defmulti`, `definterface`) as **abstract**.
2. **Hierarchy.** Namespaces are dotted (`empire.game.loop.round-setup`), so the tree is implicit: every prefix is a "high-level namespace" (a package, in Python terms) and leaves are files. Dependencies between children of the current root are aggregated from their subtrees.
3. **Layers.** Before ranking, cycles are identified and the offending edges are removed so the remaining graph is acyclic; a topological ordering assigns vertical levels. Namespaces at the same level are peers placed side by side. The removed cyclic edges are still drawn as indicators. (`layout/layers.clj` does an exact minimum-feedback-arc search for small graphs — up to 8 nodes / 12 edges — and a heuristic beyond that.)
4. **Edge classification.** Each edge is `:direct` or `:abstract` (target namespace is abstract), which drives the UML arrowhead style (open arrow vs. closed triangle).
5. **Components (optional guidance).** A `dependency-checker.edn` can supply `:component-rules` (regex → component) so modules can be colored/grouped by component; actual dependencies always take priority over the guidance.

### What the user sees (from the README's visual legend and the sample image)

- Vertical, top-to-bottom layout: high-level namespaces on top, leaf source modules at the bottom.
- High-level namespaces are rectangles with two small "nubs" on the left (the UML component icon); light blue, or **green if the subtree contains an abstract module**. Leaf modules are plain rectangles with a thick black border.
- Instead of drawing every arrow, each box has a **small triangle on its top edge for incoming dependencies and on its bottom edge for outgoing** ones. Triangles are black, or **red when any dependency in that direction is part of a cycle**. Names turn red when the subtree contains a cycle.
- **Hovering a triangle opens a popup listing the dependency paths** (scrollable), with cycle entries in red.
- When the current view contains cycles they are **listed at the bottom in `a->b->c->a` form**.
- Navigation: click a non-leaf name to **drill down** (that namespace becomes the new root); click a leaf to **open its source in a code window**; a `Back: <name>` toolbar button restores the previous root *and scroll position*; a `Reanalyze` button rescans the project and redraws the current view; the window is resizable with scrollbars.
- CLI: `--project-path`, `--in-edn <file>` (load a previously exported model), `--out <file>` (export EDN), `--no-gui` (headless export). Headless export is how agents consume it.

### Exported model shape (`examples/three-components.edn`)

```clojure
{:graph {:nodes #{"demo.app.api" "demo.app.service" "demo.app.port"}
         :edges #{{:from "demo.app.api" :to "demo.app.service"} ...}}
 :layout {:layers [{:index 0 :modules [...]} {:index 1 :modules [...]}]
          :module->layer {"demo.app.api" 1 ...}}
 :module->component {"demo.app.api" :api ...}
 :classified-edges #{{:from ... :to ... :type :direct} {:from ... :to ... :type :abstract}}}
```

This is a good template for the JSON schema of the Python tool: raw graph, computed layout, component assignment, classified edges — separable, so a UI can consume the model without re-analysing.

### Engineering notes from `PROJECT_NOTES.md` (how he had the agents build it)

- Goal statement: produce a high-level architecture diagram of a software project; rendering technology chosen deliberately up front (Quil, not HTML).
- A read-only real project (empire-2025) was the fixture from day one.
- BDD/TDD workflow with Given/When/Then scenarios, real step definitions, functions with cyclomatic complexity ≤ 5, coverage in the high 90s, mutation testing on request, and an explicit instruction to keep the implementation small in tokens so it does not strain the agents' context windows.
- Backlog: MVP = scaffold → load guidance → build actual graph → merge → layered layout → render → UML arrowheads → one-command run → verification. V2 = better extraction accuracy, cycle diagnostics, edge routing, interaction (toggles, focus, pan/zoom), guidance-vs-actual diff view, deterministic export for CI.

## 2. dependency-checker (the deterministic rules tool)

### The spec file (`dependency-checker.edn`)

```clojure
{:allowed-dependencies
 {:ui     [:game :player :state :config]
  :game   [:player :state :config]
  :player [:state :config]
  :state  [:config]
  :config []
  :test-infra :all}          ; :all = may depend on anything
 :forbidden-dependencies [[:ui :state]]          ; explicit forbidden edges (also map form {:from :ui :to :state})
 :allowed-exceptions [{:from-ns "sample.player.production" :to-ns "sample.computer.production"}] ; exact namespace-level exemptions
 :ignored-components [:spec-runner]              ; excluded from metrics, edges, violations, cycles
 :healthy-threshold 0.3                          ; distance-from-main-sequence tolerance
 :fail-on-violations true
 :fail-on-cycles true}
```

The real one in empire-2025 is just the allowed map plus the two fail flags — ten components, one line each. That is the "tight little specification file" from the video.

### Semantics

- **Components are not configured manually**: a component is the *second namespace segment* under the source path (`sample_app/ui/view.clj` → component `:ui`). Every dependency from descendant namespaces rolls up to the component. (Python equivalent: the direct sub-packages of the root package.)
- Any component-to-component dependency not in the allowed list is a **violation**; self-dependencies are always allowed; `:forbidden-dependencies` and `:allowed-exceptions` refine it.
- Cycles between components are reported and can fail the run.
- Edges are derived statically from `ns :require/:use/:import`, direct `(require ...)`, and dynamic lookups (`requiring-resolve`, `resolve`, `ns-resolve`, `find-ns`, `the-ns`) — dynamic lookups are emitted as **warnings**, not silently ignored.
- **Abstractness** counts only real indirection (`defprotocol`, `defmulti`); marking something abstract in config does not count.

### Metrics (Bob's own package metrics, from *Clean Architecture* ch. 14 / his 1994 paper)

Per component: fan-in (Ca), fan-out (Ce), instability `I = Ce / (Ca + Ce)`, abstractness `A = abstract / total`, distance from the main sequence `D = |A + I − 1|`, and a zone: **healthy** when `A + I` is within the threshold of 1.0, **pain** when `A + I < 1 − threshold` (concrete and stable — hard to change), **useless** when `A + I > 1 + threshold` (abstract and unstable). Terminal output colours the zone with intensity proportional to distance.

### CLI behaviour worth copying

- `--init` / `--force-init` **infer a starter `:allowed-dependencies` from the observed dependencies** and add the fail flags — the fastest way to adopt the checker on an existing code base.
- `--format edn` for machine-readable output; `--no-color`; `--no-edges` to omit the edge listing; exit code 1 on violations/cycles when the fail flags are set (that is what puts the agent in the fix-it loop).
- Legacy config keys produce an error with a hint to regenerate — the config format is allowed to evolve.

### How it is wired into a project (empire-2025 `deps.edn`)

```clojure
:check-dependencies {:extra-deps {io.github.unclebob/dependency-checker {:git/url "..." :git/sha "..."}}
                     :main-opts ["-m" "dependency-checker.core"]}
:arch-view          {:extra-deps {io.github.unclebob/arch-view {:git/url "..." :git/sha "..."}}
                     :main-opts ["-m" "arch-view.core" "--project-path" "."]}
```

Plus a tiny runner namespace so `clj -M:check-dependencies` works from the project root. The Python equivalent is a dev dependency in `pyproject.toml` and two commands: `archview` and `archview check`.

## 3. The architect role in swarm-forge (what the checker is enforcing *for*)

`swarmforge/roles/architect.prompt` (six-pack branch) is the closest thing to a written statement of the rules the tools serve. Paraphrased:

- Partition code into modules with clear boundaries; isolate high-level modules (far from IO) from low-level modules (near IO); **dependencies point from low-level toward high-level**.
- Identify and correct dependency-direction violations, import cycles, framework leakage, low-level data-shape leakage, and accidental public APIs.
- Define narrow interfaces owned by high-level modules so IO-near adapters depend inward; keep application policy isolated from UI, filesystem, database, network, framework, and device details.
- Add lightweight automated architecture checks when practical: dependency-direction checks, forbidden-import checks, import-cycle checks, adapter-boundary checks.
- Review phases: UI/core separation → dependency rule → information hiding/encapsulation → local code quality.

`constitution/articles/engineering.prompt` shows the pattern for the *other* deterministic tools (CRAP, mutation, DRY per language): agents install the latest version from GitHub at startup, run tools one at a time, never substitute home-grown proxies. The Python arch-viewer should be installable and runnable the same way (`uv tool install` / `uvx`), and its checker should be something an agent prompt can simply require to pass.

## 4. Gaps in Bob's tools that the Python version can improve on

- Desktop-only viewer (Quil window); no web UI, no shareable/static export of a view beyond EDN. A browser UI is a better fit for Claude Code workflows and for sharing in PRs.
- Viewer and checker are two separate code bases with two slightly different notions of "component"; a single analysis core feeding both avoids drift.
- No source-level "why" navigation from the checker output (the viewer has the hover popup; the checker prints component edges). Violations should carry `file:line`.
- No baseline/known-violations mechanism for adopting the checker on legacy code (dependency-cruiser and deptrac have one).
- Components are fixed to "second namespace segment"; a Python project sometimes needs explicit grouping (e.g. `src/app/api`, `src/app/services` vs a flat `src/app/*.py`).
- No agent-facing query interface (e.g. "why does A depend on B?", "what would break if I move X?"); MCP/CLI queries are a natural addition.
