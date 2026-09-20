# M9 — A package's public surface: design

Date: 2026-09-20. Status: approved in brainstorming, pending spec review.

GitHub issue #4. In workspace mode `[archview.workspace.allowed]` is keyed by package
name, so the finest rule expressible is "package A may import package B". The rule the
issue actually wants is narrower: the core publishes `ports` and `types` as its plugin
contract and keeps `interview`, `desk`, `cover` and `report` private, and a plugin that
reaches the domain undoes the point of having ports.

Verified against v0.3 before designing: with `plugin = ["core"]`, an added
`from core.model import Thing` inside the plugin leaves `archview check` green.

Builds on M8 (`2026-09-20-workspace-design.md`). Read it first.

## 1. The real problem is extraction, not rules

The distinction is destroyed before the checker ever runs. grimp squashes every external
import to its top-level name, so a package's own model records the same edge either way:

```
plugin.adapter -> 'core'   text='from core.ports import Port'
plugin.adapter -> 'core'   text='from core.model import Thing'
```

Only the raw `text` differs, and text is not a resolution. `from core import model as m2`
imports the same module while naming only `core`, so any scan of the import line misses
it. Recovering the target is therefore the milestone; the rules file is the easy half.

## 2. Where the precision comes from

### Python — a workspace resolution pass

For the cross-package attribution step only, build one grimp graph over the workspace's
Python packages together, with their source roots on `sys.path`. Confirmed by experiment:

```
plugin.adapter -> core.model    line 17: from core.model import Thing
plugin.adapter -> core.model    line 19: from core import model as m2
plugin.adapter -> core.ports    line  8: from core.ports import Port
plugin.adapter -> openai        line  9: from openai import OpenAI
```

Exact, including the aliased re-export shape. The per-package federation is untouched:
each package keeps its own `Project`, model, language and view. This pass exists solely
to answer "which part of the sibling did you touch", and its output is consumed only by
`cross_edges`.

**This is not a return to the merged model M8 rejected.** No ids are rewritten, no
separator is shared, no `Model` is combined. It is a second, narrower query over the same
source, run once per workspace check.

### TypeScript — mostly already there

- **Relative import** (`../../core/src/index`): the outside name *is* the resolved path,
  so the component falls out of resolving it against the sibling's source root. No
  extractor change.
- **Bare npm name** (`@fixture/core`): resolves to the package's entry point, which is its
  public surface by construction. Always legal.
- **npm subpath** (`@fixture/core/internal`): `_external_name` squashes it to the package
  name, and the subpath is lost. This is the one gap (section 7).

### What this does not change

`Import` gains no field, and the model JSON stays at **schema 3**. The resolution lives
at the workspace layer, where the sibling packages are known, rather than in a model that
is deliberately per-package.

## 3. The rules surface

```toml
# component/archview.toml — the contract lives with the package that owns it
[archview]
package = "bespoke_story"
public  = ["ports", "types"]

# root archview.toml — unchanged in shape
[archview.workspace.allowed]
bespoke_openai = ["bespoke_story"]           # ports and types only
bespoke_server = ["bespoke_story.ports"]     # qualified: narrows further

[[archview.workspace.forbidden]]
from = "*"
to   = "bespoke_story.desk"
```

- `public` lists **component names**, the same vocabulary as `[archview.allowed]` keys —
  direct children of the package, or whatever `[archview.components]` defines. Not dotted
  module paths.
- **Absent `public` means the whole package is public.** Every workspace that exists today
  keeps its current meaning.
- An import must satisfy **both** the root's grant and the owner's `public`.
- Qualified names (`package.component`) work in `[archview.workspace.allowed]` and
  `[[archview.workspace.forbidden]]`. That is issue #4's shapes 1 and 2; `public` is
  shape 3.

### When the two disagree

A qualified grant naming a component the owner does not publish is a **`ConfigError`**
at load time, naming the owner's `public` list. Such a rule could never usefully fire —
`public` would override it — and ADR 0011 already rejected stdlib rules on exactly that
reasoning: a rule that looks live but is not is worse than an error.

The deliberate one-off stays `[[archview.workspace.exceptions]]`, which already requires
a written reason. That keeps one owner for the contract and one documented escape hatch.

### Outside a workspace

`public` in a single-package repo parses and does nothing. `check` emits a `Notice`
saying so rather than ignoring it silently.

## 4. Checker semantics

New `ProblemKind = "private"`.

| field | value |
|---|---|
| `kind` | `"private"` |
| `rule` | `f"{owner.config.table}.public"` — the target package's own table, so a `pyproject.toml`-based package reports `tool.archview.public`. Which package is meant is unambiguous from `components[1]` |
| `components` | `(source package, "target.component")` |
| `hint` | names what the target package publishes, so an agent learns the contract without opening another file |

`forbidden` still wins over everything, including a qualified `allowed`. Cycles, metrics
and every single-package path are untouched.

An import whose component cannot be resolved (section 7) is still checked at package
level and raises a `Notice` naming its file and line. The case we cannot place is
reported, never silently passed.

## 5. The viewer

Chosen from three mocked alternatives: **published components become boxes on the package
boundary**, so a legal dependency visibly terminates at a port and a violation visibly
bypasses one. The picture carries the architecture rather than a label.

- `ViewNode` gains `parent: str | None`. A public component is a node with
  `kind = "package"` (it is a sub-package, and the renderers already style that kind) whose
  `parent` is its package, and whose `id` is the qualified `package.component`. This is the
  **view** JSON, not the model schema.
- `to_dot` nests any node with a parent in a `subgraph cluster_<package>`; `to_mermaid`
  uses its `subgraph` block. The UI renders DOT through Graphviz-WASM, so it inherits the
  nesting without a UI change.
- A cross-package edge whose target is **public** lands on that component's node. One
  whose target is **private** lands on the package node itself and is drawn as a
  violation — which is precisely the "bypasses the ports" reading.
- A package with no `public` declaration draws exactly as it does today.

## 6. Testing

- The workspace fixture's `core` gains a private component and a `public` list; `plugin`
  reaches the private one. That is the issue's shape, end to end.
- The Python resolution pass is tested directly, including `from core import model as m2`
  — the case that justifies the whole approach over a text scan.
- TypeScript: a relative import into a sibling's private component must fail; a bare npm
  name must pass; an npm subpath must raise the `Notice` from section 7.
- Backwards compatibility: no `public` anywhere means byte-identical output. The existing
  regression test reuses its golden file, as M8's does.
- `tests/test_self_check.py` asserts zero warnings on this repo, which is not a workspace.

## 7. Known limitations

- **TypeScript npm subpath imports into a sibling cannot be placed.** `@fixture/core/internal`
  squashes to `@fixture/core`, so `public` cannot be enforced for it. Reported as a
  `Notice`, not silently allowed. Fixing it means carrying the resolved specifier on
  `Import` and bumping the model schema; deferred until someone hits it.
- **The Python pass puts sibling source roots on `sys.path` together.** Two workspace
  packages that genuinely cannot coexist there will fail; the error names both rather
  than surfacing as a confusing resolution miss.
- **`public` constrains only cross-package imports.** It says nothing about what the
  package's own modules may import from each other — that is `[archview.allowed]`'s job.

## 8. Out of scope

- Symbol-level contracts ("`ports` publishes `Port` but not `_PortBase`"). Components are
  the unit, as everywhere else in this tool.
- Inferring `public` in `archview init`. What a package publishes is the architectural
  decision a human is making.
- Re-export resolution inside a package (requirements open decision 3) — unchanged.

## 9. Done when

- A plugin importing the core's private domain fails `archview check`, with the file and
  line, in the workspace from issue #4.
- `public` is declared once by the package that owns it and every sibling is checked
  against it; adding a sixth plugin needs no new rule.
- Qualified targets work in the workspace `allowed` and `forbidden` tables.
- The workspace view draws published components on the package boundary, and a violating
  edge visibly bypasses them.
- A workspace with no `public` anywhere behaves exactly as it does on v0.3.
