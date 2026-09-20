# 11. Rules for outside imports: outside names, `[archview.externals]`, stdlib rejection

Date: 2026-09-20 (M7)

## Status

Accepted.

## Context

`docs/superpowers/specs/2026-09-20-outside-rules-design.md` works out how a rule can
name a package outside the project — a PyPI or npm dependency, or, in a workspace, a
sibling package. Until M7, `archview check` dropped every import whose target was
outside the checked package, so none of "the core never imports a vendor SDK" or "only
this component may depend on `requests`" could be written. This ADR records the
decisions the design makes and why.

## Decision

- **An outside name** is any model node with `kind == "external"`: one squashed node
  per top-level third-party package (`model/graph.py`). archview does not distinguish
  a first-party sibling package from a third-party dependency, because it cannot: from
  one package's model alone, an import of `bespoke_openai` and an import of `openai`
  look identical, both nodes with no `file` sitting outside the project tree. That
  distinction needs the list of sibling packages, which only workspace mode (M8)
  supplies. Until then there is exactly one bucket for anything outside the project.

- **`from = "*"` means every component.** The design sketch that started this
  milestone (GitHub issue #1) wrote `from = "bespoke_story"` meaning "the whole
  project". That reading was rejected: the project name is already a component, the
  root module `pkg/__init__.py` named after the project (ADR 0006), so a rule spelled
  that way would silently narrow to one file instead of applying project-wide. Only
  `*` was given the "every component" meaning; the bare project name keeps meaning the
  root module.

- **`[archview.externals]` is asymmetric with `[archview.allowed]`: a component absent
  from the table is unconstrained, with no `undeclared` counterpart.** `[allowed]`
  treats a missing component as a problem (ADR 0006) because the set of components is
  small, closed, and entirely under the project's control — a human decided to add
  each one. The set of third-party packages is neither closed nor under the project's
  control: a new import of a new PyPI package must not need a rules-file edit before
  `check` passes again, or the strict reading would fail every repo the moment the
  table existed. The asymmetry is what lets a team adopt `[externals]` one component
  at a time — constrain `llm` today, leave everything else alone — instead of having
  to enumerate every third-party package every present component already reaches
  before the table can exist at all.

- **A rule naming a stdlib module is rejected at parse time (`ConfigError`), not kept
  as a rule that silently never fires.** The Python extractor filters the standard
  library out of the graph before the model exists (`extract/python.py`), so an edge
  to `queue` or `subprocess` can never appear in `edges.outside`; a rule constraining
  it would sit in the rules file doing nothing, indistinguishable from a working rule
  until someone tried to rely on it. A rule that looks live but is not is worse than a
  startup error, so `_reject_stdlib` (`rules/config.py`) raises as soon as the name is
  read, for both `[archview.externals]` targets and `[[forbidden]]` targets.
  `[[exceptions]]` is not checked: an exception names an import the rules already
  tolerate, and a stdlib import cannot appear there to be exempted in the first place.

- **The stdlib check is gated on *declared* TypeScript — `language = "typescript"` or
  `tsconfig` set — not on `language == "python"`.** Language is frequently
  undeclared: archview auto-detects TypeScript from a root `tsconfig.json` and
  otherwise assumes Python. Gating on `language == "python"` reads as "check stdlib
  only when the repo says Python", but an ordinary Python repo almost never says so —
  it relies on the default — so that reading would silently disable the check for the
  common case. Gating on *not* declared-TypeScript keeps the check on by default and
  turns it off only once the repo has told archview, one way or another, that stdlib
  module names do not mean the Python stdlib here.

  **Residual limitation, accepted as-is:** an auto-detected TypeScript repo — a root
  `tsconfig.json` present, nothing declared in `archview.toml` — whose rules name an
  npm package that collides with a Python stdlib module name (`queue`, `string`, `io`,
  `types` and `array` are real npm packages with these names) still gets a false
  `ConfigError` on that rule, because nothing in the config says "this is TypeScript"
  at the point the rule is parsed. The workaround is to declare `language =
  "typescript"` explicitly. This is a genuine known limitation, not a corner case
  swept under a rug: fixing it would mean running language detection before config
  parsing, which the current load order does not support.

- **A violating outside edge is drawn in the viewer without `--externals`.** Every
  other external node needs `--externals` to appear at all (M4). A violation you need
  a flag to see is one you will miss, so `build_view()` takes a `keep:
  frozenset[str]` of outside names forced into the view regardless of the flag;
  `cli._graph` and the server compute it with `rules.overlay.outside_targets(report)`
  before building the view. `keep` is a frozenset of strings, so `model` still gains
  no dependency on `rules`.

- **`forbidden` keeps its existing `ProblemKind`; only the new allow-list gets a new
  kind, `"outside"`.** A `[[archview.forbidden]]` rule whose target is an outside name
  reports exactly like any other forbidden edge: same `kind: "forbidden"`, same
  `from`/`to` JSON fields. An agent already parsing the report's `forbidden` problems
  catches a forbidden outside import with no change. Only `[archview.externals]`
  violations, which have no equivalent under the pre-M7 rules, get the new kind.

## Consequences

A rule can now say "the core must never import this vendor SDK" or "only this
component may depend on `requests`", enforced with the same file:line evidence as an
internal violation. `archview init --externals` gives repos the same freeze-then-delete
adoption path for `[externals]` that `init` already gives `[allowed]`, off by default
so a plain `init` stays uncluttered by every third-party import already in the code.

The accepted gap is the stdlib/TypeScript collision above; the workaround is one line
(`language = "typescript"`) once it is hit. Workspace mode (M8) can add a further
`ComponentMap` accessor that resolves an outside name to a sibling package's own
components, without changing what `outside()` means for a true third-party package.
