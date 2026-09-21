# 13. A package's public surface: where the target comes from, and who owns the contract

Date: 2026-09-22 (M9)

## Status

Accepted. Implements `docs/superpowers/specs/2026-09-20-public-surface-design.md`
(GitHub issue #4). Builds on ADR 0011 (rules for outside imports) and ADR 0012
(workspace mode).

## Context

Workspace rules were keyed by package name, so the finest rule expressible was
"package A may import package B". The rule people actually want is narrower: a core
publishes `ports` and `types` as its plugin contract and keeps its domain private, and
a plugin that reaches the domain undoes the point of having ports. Verified against
v0.3 before designing: with `plugin = ["core"]`, adding `from core.model import Thing`
inside the plugin left `archview check` green.

## Decision

- **The problem was extraction, not rules.** grimp squashes an external import to its
  top-level name, so a package analysed on its own records `plugin.adapter -> core`
  whichever part of `core` the source named. Reading the import line as text does not
  recover it either: `from core import model as m2` names only `core` while reaching
  `core.model`. The rules file was the easy half.

- **A second, narrower query, not a merged model.** For Python, one grimp graph over
  the workspace's packages together resolves cross-package imports exactly. This does
  not reopen ADR 0012's federation decision: no ids are rewritten, no separator is
  shared, no `Model` is combined. Each package keeps its own model, language and view;
  this pass exists only to answer "which part of the sibling did you touch", and only
  `cross_edges` consumes it.

- **TypeScript carries `Import.resolved`, and the model schema goes to 4.** The design
  first claimed a TypeScript relative import already carried its full path as the
  outside name, so no model change was needed. That was wrong, and implementation
  found it: `_external_name` squashes all three forms to the package —
  `../../core/src/index` to `../core`, and an npm name to its package — so TypeScript
  could place no cross-package import at all, not merely the subpath case the design
  named as its one gap. `Import` now carries the path tsc already computed and the
  extractor discarded. Python leaves it null, because a single package's model
  genuinely cannot say more than `imported` already does.

- **A component comes from the owner's own model, not from path arithmetic.** A
  TypeScript node id drops the source root (`src/index.ts` becomes `core/index.ts`), so
  only the extractor that built the ids can map a resolved file back to one.

- **The contract lives with the package that owns it.** `public` sits in the owner's own
  rules file, so adding a sixth plugin needs no new rule anywhere. Listing the contract
  once is the whole reason this beats repeating qualified targets in every sibling's
  grant.

- **An absent `public` key means the whole package is public.** Every workspace that
  existed before this milestone keeps its meaning. An empty list means the package
  publishes nothing, which is why the parser distinguishes absent from empty.

- **Both the root's grant and the owner's `public` must pass.** A qualified grant
  (`core.ports`) narrows further; it never widens. It also grants the package to the
  package-level check, without which that check would deny the very import the grant
  exists to permit.

- **A grant naming a component its owner does not publish is a `ConfigError`.** `public`
  would override it, so it could never usefully fire — the reasoning ADR 0011 used to
  reject a stdlib target rather than let it silently no-op. The deliberate one-off stays
  `[[archview.workspace.exceptions]]`, which already requires a written reason.

- **`public` outside a workspace says so.** In a single-package repo the key does
  nothing, and `check` emits a notice rather than ignoring it.

- **Published components are drawn on the package boundary.** Chosen over a `public:`
  line inside the node and over showing nothing until drill-down, after comparing the
  three as mockups. A legal dependency then visibly terminates at a published component
  and a violation visibly goes past them into the package — the rule is legible without
  reading text. `ViewNode` gains `parent`; `to_dot` and `to_mermaid` nest, and the UI
  renders DOT, so it inherits the nesting.

- **An import that cannot be placed is reported, never passed over.** It is still checked
  at package level; what is missing is only the public-surface check, and silently
  skipping that is the "looks protected but is not" failure this tool exists to prevent.
  These notices also give the cross-package report its first warnings — until now it was
  built with an empty tuple, a gap ADR 0012 recorded.

## Consequences

Agents get a hard stop on reaching another package's private domain, with the file, the
line, and a hint naming what that package does publish — so the contract is learnable
from the report without opening another file.

Known limitations:

- **The Python pass puts sibling source roots on `sys.path` together.** Two workspace
  packages that genuinely cannot coexist there will fail.
- **An import tsc cannot resolve cannot be placed.** A real monorepo maps its siblings
  with tsconfig `paths`, and then every form resolves; without that mapping the import
  is reported as unplaced rather than assumed public.
- **`public` says nothing about a package's internal structure** — that is
  `[archview.allowed]`'s job — and nothing below component level. Symbol-level contracts
  ("`ports` publishes `Port` but not `_PortBase`") remain out of scope, as components are
  the unit everywhere else in this tool.
- **Reading a model JSON written by an older archview now fails** with a clear schema
  error, as it did at every previous bump.
