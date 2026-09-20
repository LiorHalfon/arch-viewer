# M8 — Workspace mode: design

Date: 2026-09-20. Status: approved in brainstorming, pending spec review.

GitHub issue #2. A workspace holds several packages — five Python packages and a React
app, in the driving example — and the architecture lives at two levels: inside each
package, and between the packages. Today that takes one rules file, one `check` run and
one view per package, and nothing checks or draws the edges between them. From the
workspace root, archview asks you to pick one package with `--package`.

Builds on M7 (`2026-09-20-outside-rules-design.md`), which makes a cross-package import
visible as an outside edge. **M8 only has to attribute those edges to sibling packages.**
Read M7 first.

## 1. Structure — a federation, not a merged model

Two shapes were weighed. Merging every package into one `Model` with a synthetic root
would let the view, checker, cycles and viewer work unchanged, but `Model` carries a
single `project` string and a single `separator`, so Python's `.` ids and TypeScript's
`/` ids collide and every node id needs rewriting. The federation keeps each package's
model exactly as it is.

New component `src/archview/workspace.py`, depending on `extract, model, project, rules`.
`cli` and `server` gain a dependency on it. A new top-level component is an
architectural statement, which is what this is; the repo's own `archview.toml` records
it.

```python
@dataclass(frozen=True, slots=True)
class Package:
    name: str                      # the component name at workspace level
    path: Path                     # relative to the workspace root
    aliases: frozenset[str]        # how siblings refer to it
    project: Project | None        # None when the package has no rules file of its own

@dataclass(frozen=True, slots=True)
class Workspace:
    name: str
    root: Path
    packages: tuple[Package, ...]
    config: Config                 # the root rules file
```

### `aliases` — the join

A cross-package edge is an outside edge from M7 whose outside name belongs to a
sibling's `aliases`. A package's aliases are:

- **Python**: the top-level package name (`bespoke_story`), i.e. `Project.package`.
- **TypeScript**: the `name` field from `package.json`, scope included (`@bespoke/core`)
  and with the scope stripped, since `_external_name` squashes npm names scope-aware.
- **TypeScript relative imports**: the extractor classifies `../`-prefixed resolutions
  as external (`extract/typescript.py:120`), so an outside name may be a path such as
  `../component/src/story`. `_owner()` resolves such a name against the importing
  package's directory and matches it to the workspace package whose path contains it.

`_owner(outside_name, importer_package, packages) -> str | None` is the one function
that performs the attribution. An outside name that matches no sibling stays an ordinary
third-party dependency, governed by M7's rules inside that package.

### Naming

`server/workspace.py` currently holds a class named `Workspace` that means "the project
the viewer is looking at". It becomes `server/state.py` with class `ViewerState`.

## 2. Configuration

A workspace table at the root, while each package keeps its own rules file for what is
inside it.

```toml
[archview.workspace]
packages = ["component", "plugins/openai", "plugins/files", "server", "tools", "web"]
fail_on_violations = true            # default true
fail_on_cycles = true                # cycles *between* packages; default true
baseline = "archview-baseline.json"  # optional, for the cross-package rules

[archview.workspace.allowed]         # keyed by package name
bespoke_story  = []
bespoke_openai = ["bespoke_story"]
bespoke_files  = ["bespoke_story"]
bespoke_server = ["bespoke_story", "bespoke_openai", "bespoke_files"]
bespoke_tools  = "all"
web            = []

[[archview.workspace.forbidden]]
[[archview.workspace.exceptions]]
```

- `packages` entries are directory paths relative to the rules file. Each is opened with
  `open_project()`, which finds that package's own `archview.toml` or
  `[tool.archview]`, its own language, and its own source roots.
- `Workspace.name` is the root directory's name, and `[archview].package` at the root
  overrides it. A workspace root has no package of its own, so that key is otherwise
  unused there.
- A `Package.name` is its `Project.package`. Two packages resolving to the same name is
  a `ConfigError` naming both paths, since the workspace rules key on that name.
- `allowed`, `forbidden` and `exceptions` reuse the existing `_allowed`, `_forbidden`
  and `_exceptions` parsers unchanged.
- **`undeclared` does apply at workspace level.** A package missing from
  `[archview.workspace.allowed]` is a problem. A new package in a workspace is exactly
  the architectural decision ADR 0006 says an agent must not make quietly. This is the
  opposite of M7's `[archview.externals]` asymmetry, and deliberately so: there, the
  universe of third-party packages is open and large; here it is closed and declared.
- The example's "the server imports the plugins from one module only" is
  `bespoke_server = ["bespoke_story"]` plus a workspace exception for
  `bespoke_server.wiring → bespoke_openai`.
- The example's "web → the server, over HTTP only" is `web = []`: there is no import
  edge to find, and the rule records that there must not be one.

### A package without its own rules file

Listed in `packages`, no `archview.toml` and no `[tool.archview]`: the workspace rules
still apply to it, and **nothing inside it is checked**. Its inner check does not run at
all — running it would emit a `no_rules` warning and check cycles, which is more than
"unconstrained" should mean. This makes workspace mode adoptable before per-package
rules exist. `Package.project` is still built (the model is needed for the
cross-package edges); it is the *check* that is skipped.

## 3. `check` at the workspace root

1. Open each listed package.
2. Run each package's own `check`, only where it has its own rules file.
3. Build the cross-package edges from every package's outside edges via `_owner()`, and
   check them against the workspace rules.
4. One exit code: 1 if any package report or the cross-package report failed.

A repo with no `[archview.workspace]` table behaves exactly as today, byte for byte.
`SeveralPackages` ("several packages in X; pick one with `--package`") stops firing at a
workspace root.

### Text output

A section per package, then the cross-package section, then one total.

```
bespoke_story   ok
bespoke_server  1 problem
  VIOLATION api -> wiring (2 imports) not allowed by [archview.allowed].api
    ...
between packages  1 problem
  VIOLATION bespoke_story -> openai (1 import) not allowed by [archview.workspace.allowed].bespoke_story
    component/src/bespoke_story/llm.py:4  from openai import OpenAI
2 problems. exit 1
```

### JSON output

Each report keeps exactly today's `report_to_dict` shape, so an agent's existing parser
is reused; only the envelope is new.

```json
{"workspace": "bespoke-story",
 "ok": false,
 "packages": [{"package": "bespoke_story", "project": "bespoke_story", "ok": true, "...": "report fields"}],
 "between":  {"project": "bespoke-story", "ok": false, "...": "report fields"}}
```

The cross-package report's `components` are the package names.

### Baseline

Each package keeps its own baseline, found through its own rules file as today. The
cross-package rules get a baseline at the root when `[archview.workspace].baseline` is
set, applied with the existing `apply_baseline`. `--update-baseline` at the root updates
the workspace baseline and every package baseline that is configured.

## 4. Viewer

`workspace_view(workspace) -> View` builds the top level: packages as nodes,
cross-package import counts as edges, layers via `assign_layers`, cycles via
`find_cycles`. It returns the **existing `View` type**, so DOT, Mermaid, the violations
overlay and the UI renderer all work unchanged.

- `ViewNode`: `id = name`, `kind = "package"`, `module_count` = the package's module
  count, plus `layer`, `in_cycle`, `fan_in`, `fan_out`. Abstractness and zone are not
  computed across packages; `zone = "isolated"` and the metric fields keep their
  defaults, as they do for external nodes today.
- Drill-down gains a package dimension: `/api/view?package=X&root=Y`. With neither, a
  workspace root returns the workspace view. The breadcrumb becomes
  workspace → package → component → module; clicking a package node opens that
  package's own view at its root.
- `/api/source` gains `package=`.
- `--watch` watches every package directory.

## 5. The other commands at a workspace root

| Command | At the root | With `--package X` |
|---|---|---|
| `check` | every package + the cross-package rules | that package alone, as today |
| `graph` | the workspace view | that package, as today |
| `cycles` | cycles between packages | that package, as today |
| `metrics`, `why`, `deps`, `rdeps` | require a package | that package, as today |

`why`/`deps`/`rdeps` keep the name inference they already have (`cli._open`): in a
workspace, the first query name may pick the package.

## 6. Testing

- `tests/fixtures/workspace/` — new: `core/` and `plugin/` (Python, `plugin` imports
  `core`, and one import that breaks the rules), plus a root `archview.toml` with a
  workspace table. Deterministic, no Node needed.
- A TypeScript-in-a-workspace case reusing `tests/fixtures/ts-sample`, gated with the
  existing `@requires_typescript` mark, covering the npm-name and relative-path alias
  paths.
- `tests/test_workspace.py` — attribution (`_owner`), the allow-list, `undeclared` for
  an unlisted package, workspace exceptions, cross-package cycles, a package without its
  own rules file.
- `tests/test_cli_workspace.py` — `check` exit codes and the JSON envelope, `graph` at
  the root, `--package` drilling in, and a regression test that a non-workspace repo's
  output is unchanged.
- `tests/golden/` gains a workspace model/view pair.

**Constraint:** `tests/test_self_check.py` asserts `report.warnings == ()`.

**Dogfooding:** `prototypes/bespoke-story` exists only on the
`prototype/bespoke-story-interview` branch of `~/git/tiny-tale-backend`, and at that
commit has `component` and `server` but none of the plugins the issue describes. It is
checked out into a scratch worktree and used as a real two-package workspace; the
fixture carries the cases it cannot.

## 7. Out of scope

- Multi-repo graphs (requirement section 9).
- Abstractness, the main sequence and zones across packages. The Martin metrics are
  defined over a component's classes; aggregating them across languages is a separate
  question.
- Inferring a workspace table. `archview init` does not write one; the list of packages
  and what may depend on what is the architectural decision the human is making.
- Per-package `--format` differences. One format for the whole run.

## 8. Done when

- One command checks all the packages and the rules between them, with one exit code.
- The viewer's top level is the packages and their edges, and drills into each package,
  Python or TypeScript.
- A repo without a workspace table behaves exactly as before.
