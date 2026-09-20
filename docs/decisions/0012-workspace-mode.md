# 12. Workspace mode: federation, the alias join, and what stays asymmetric with M7

Date: 2026-09-20 (M8)

## Status

Accepted.

## Context

`docs/superpowers/specs/2026-09-20-workspace-design.md` (M8, GitHub issue #2) builds
on M7 (ADR 0011, `2026-09-20-outside-rules-design.md`): once a cross-package import is
visible as an outside edge, workspace mode only has to attribute it to a sibling
package. Before M8, a repo with several packages — five Python packages and a React
app, in the driving example — had one rules file, one `check`, one view per package,
and nothing checked or drew the edges between them. This ADR records the decisions
the design makes and why.

## Decision

- **Federation, not a merged model.** Two shapes were weighed: merge every package
  into one `Model` with a synthetic root, or keep each package's own `Project` and
  join them only at the report/view layer. Merging would let the checker, cycles and
  viewer work unchanged, but `Model` carries a single `project` string and a single
  `separator` (`.` for Python, `/` for TypeScript) — Python's dotted ids and
  TypeScript's slash-separated ids would collide the moment they shared a namespace,
  and every node id would need rewriting to make room for a synthetic root. The
  federation (`src/archview/workspace.py`, a new component depending on
  `extract, model, project, rules`) keeps each package's model exactly as it is;
  `Workspace` is just `Package`s, each with its own `Project`, plus the rules between
  them.

- **The alias join.** A cross-package edge is an M7 outside edge whose outside name
  belongs to a sibling's `aliases`. Three kinds of alias exist, because "how a
  sibling is named" differs by language and by import style:
  1. **Python top-level module name** — `Project.package`, the only name Python
     siblings can be imported by.
  2. **npm `name`, scoped and unscoped** — a TypeScript package's `package.json`
     `name` (`@bespoke/core`), plus that name with its `@scope/` prefix stripped
     (`core`). Both forms are real: a bare unresolvable import (`import x from
     "core"`) is classified external by its literal specifier text, with no
     `node_modules` entry needed, so a workspace member can be reached by either
     spelling depending on how the importing file names it.
  3. **A TypeScript `../` relative import**, resolved back to a package directory.
     The extractor classifies a `../`-prefixed resolution as external
     (`extract/typescript.py:120`) and squashes it to the shortest path that escapes
     the importing repo (`../core`, not `../core/src/index.ts`) — the same squashing
     `_external_name` already does for a `node_modules` import. `_owner_by_path`
     resolves that squashed name against the importing package's own directory and
     matches it to whichever sibling's directory contains the result.

  `_owner(outside_name, importer_package, packages) -> str | None` is the one
  function that performs the attribution, for all three kinds. An outside name that
  matches no sibling stays an ordinary third-party dependency, governed by M7's rules
  inside that one package.

  **A bug the TypeScript case surfaced.** Writing the first end-to-end TypeScript
  test (`tests/fixtures/ts-workspace/`) found that `ComponentMap.outside()` was
  re-splitting an already-squashed external id on the model's separator — correct for
  grimp's Python ids (`openai.types.chat` arrives already squashed to `openai` by
  grimp itself, so the split is a no-op there) but wrong for TypeScript, where `/` is
  also part of a scoped npm name or a `../sibling` outside name: `outside()` was
  cutting `@fixture/core` down to `@fixture` and `../core` down to `..`. Both
  extractors already squash before `outside()` ever runs, so `outside()` now trusts
  the id it is given instead of re-splitting it (`rules/components.py`). This was a
  latent bug in M7's code, invisible until a `/`-structured outside name that was not
  also a dotted Python one existed to expose it.

- **`undeclared` applies at workspace level; `[archview.externals]` has no
  analogue here.** A package missing from `[archview.workspace.allowed]` is a
  problem, exactly as an undeclared component is under `[archview.allowed]`
  (ADR 0006): a new workspace member is an architectural decision an agent must not
  make quietly. This is the mirror image of M7's `[archview.externals]`, where a
  component missing from the table is deliberately unconstrained (ADR 0011) — and the
  difference is deliberate, not an oversight. The set of workspace packages is closed
  and declared by a human in `packages = [...]`; the universe of third-party packages
  is open and effectively unbounded, so treating a missing entry there as a problem
  would fail every repo the day the table appeared. A workspace has no such excuse:
  every member is already named in `packages`, so leaving one out of `allowed` too is
  just an incomplete rules file, not an open-world problem.

- **A listed package without its own rules file is unconstrained inside, and its
  inner check does not run at all.** `Package.project` is still built for it — the
  cross-package edges need its model — but `check_workspace` skips calling `check()`
  on it entirely rather than running it with an empty `Config`. Running it anyway
  would emit a `no_rules` warning ("only cycles are checked") and still check for
  cycles inside that package, which is more than "unconstrained" is supposed to
  mean: the point is to let a workspace be adopted one package's rules file at a
  time, with the packages that have not been given rules yet completely silent, not
  quietly semi-checked.

- **The JSON envelope is new; each report inside it keeps its existing shape.**
  `workspace_to_dict` wraps `report_to_dict`'s own output for every package and for
  the cross-package report unchanged — `{"workspace": ..., "ok": ..., "packages":
  [{"package": name, **report_to_dict(r)}, ...], "between": report_to_dict(between)}`.
  An agent's existing parser for a single project's `check --format json` output
  keeps working on each entry; only the wrapper is new.

- **`WorkspaceReport` lives in `rules/check.py`, not `workspace.py`.** It is pure
  report data — a name, a list of `(package name, Report)` pairs, and a `Report` for
  the rules between them — with nothing in it that references `workspace.py`. Putting
  it there instead would have given `render/workspace.py` (which renders
  `WorkspaceReport` alongside plain `Report`) a dependency on `workspace`, and
  transitively on `extract`, just to describe a shape it already knows how to print.

- **`_owner` lives in `workspace.py`, not as a new `ComponentMap` accessor.** ADR
  0011 flagged this as a plausible extension point ("a further `ComponentMap`
  accessor that resolves an outside name to a sibling package's own components").
  `workspace` already depends on `rules` (`Edges`, `component_edges`,
  `_rule_problems`); teaching `ComponentMap` about `Package.aliases` would reverse
  part of that into a cycle — `rules` would need to know about `workspace`, which
  already needs `rules`. Keeping `_owner` in `workspace.py`, operating on the
  `Package` objects its own caller assembled, keeps the dependency one-directional.

- **The cross-package report never warns about an unused exception or lists an
  unused allowance, and this is not implemented anywhere.** `_check_between` builds
  the `between` `Report` directly - `Edges(internal=cross_edges(ws), outside={},
  exceptions_used=set())` and `Report(ws.name, present, tuple(problems), ())` - so
  `warnings` is hardcoded to `()` and `unused` keeps its default `()`. A single
  project's own `check()` calls `_warnings()` (which reports `unused_exception` from
  `exceptions_used`) and `_unused()` (which lists an `[archview.allowed]` entry no
  import uses); `_check_between` calls neither. Concretely: a stale
  `[[archview.workspace.exceptions]]` entry that exempts nothing produces no warning,
  and an `[archview.workspace.allowed]` entry that permits a package pair nothing
  actually imports is never flagged as tightenable. Both gaps are undocumented
  elsewhere and unimplemented; this ADR just records them next to the nested-package
  limitation below, rather than leaving them to be rediscovered.

- **A known limitation, stated plainly.** `_owner_by_path` resolves a `../` import to
  the first sibling package (sorted by name) whose directory contains the target —
  there is no preference for the deepest or most specific match. A workspace that
  listed one package nested inside another (`packages = ["a", "a/sub"]`) could
  misattribute an import that belongs to `a/sub` to `a` instead, or vice versa
  depending on sort order. No design example nests packages this way, and the driving
  examples (five Python packages plus a React app; `core`/`plugin`) are all siblings,
  not parent and child. This is a latent gap, not a regression, and it is not fixed
  here.

## Consequences

One command checks every package in a workspace and the rules between them, with one
exit code; the viewer's top level is the packages, drilling into each. A repo without
`[archview.workspace]` is unchanged, byte for byte. `metrics`, `why`, `deps` and
`rdeps` do not read `[archview.workspace]` at all yet — they take a package's own
directory as `path`, exactly as before M8 existed. `archview init` still writes no
`[archview.workspace]` table: which packages exist and what may depend on what is the
human's call, the same reasoning that already keeps `init` from writing
`[archview.externals]` by default (ADR 0011).

The nested-package limitation above is real; a repo that needs it should file it
against `_owner_by_path` rather than work around it in the rules file.
