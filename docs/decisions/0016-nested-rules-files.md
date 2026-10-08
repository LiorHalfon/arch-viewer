# 16. Rules files inside sub-packages

Date: 2026-10-09 (M12)

## Status

Accepted. Implements `docs/superpowers/specs/2026-10-08-nested-rules-design.md`
(GitHub issue #14). Builds on ADR 0006 (checker semantics) and ADR 0012 (workspace
mode).

## Context

Rules can only be written between components, and a component is a direct child of
the project package unless `[archview.components]` says otherwise. That map is flat.
Issue #14's reporter wanted rules between the 12 packages under
`src/webapp/services/` in tiny-tale-backend. It took 27 component patterns, 35
components in all. Fifteen of those patterns existed only to stop the leftover
`webapp` component from producing `CYCLE print_svc -> webapp -> print_svc` on code
with no cycle. A new `services/*` package that nobody added a pattern for joined
`webapp` silently.

## Decision

A file named `archview.toml` in the directory of a package below the project package
holds the rules between that package's children. The root file is unchanged.

- **Schema.** A nested file takes the rule keys: `allowed`, `forbidden`, `layers`,
  `independent`, `exceptions`, `components`, `ignored`, `fail_on_violations`,
  `fail_on_cycles`, `metrics`, `baseline`. Any other key is a `ConfigError` (exit 2)
  naming the file and the key. The scope takes `type_checking_imports` and `exclude`
  from the root. Module patterns use full module names; component names are the short
  child names.
- **Discovery.** After the project opens, archview walks the package directory for
  `archview.toml` files. A file whose directory is a package in the model names a
  scope. Any other file gets an `unchecked_rules_file` notice, so no rules file is
  silently ignored.
- **Checking.** `scoped_model` cuts the model to the modules inside the scope, keeps
  the imports with both ends inside, drops outside names and sets `project` to the
  scope id. The existing `check()` then runs on it with the nested `Config`, so
  violations, forbidden pairs, `undeclared` children, cycles, zones and unused
  allowances behave as at the root. A `forbidden` target that is not a child of the
  scope gets an `unknown_component` notice, since it can never fire there.
- **Report.** `Report.scopes` holds one report per scope, in a flat list sorted by
  scope id. `Report.failed` covers the scopes. The text output adds one section per
  scope, and the JSON output gains an always-present `scopes` array. With no scopes the
  text output is unchanged.
- **Baselines.** Each scope has its own baseline, resolved against its rules file.
  `check --update-baseline` writes one per scope.
- **`init --root X`.** Writes the nested file, inferred from the scoped model and the
  root's inherited keys, so the edges it writes are the edges `check` reads.
- **`serve`.** `failing_imports` includes the scopes' failing imports, the check panel
  lists each scope, and `--watch` follows every nested file.

## Rejected approaches

- **Parent and child components inside `ComponentMap`.** It would reach every
  consumer (metrics, cycles, views, baseline) for the same result the scoped model
  gives by changing none of them.
- **Expanding a nested file into flat `[archview.components]` patterns.** The root
  would still need `webapp`'s other children as components, so the false cycle stays.

## Consequences

A package can be split into rule-bearing sub-packages one at a time, with the parent
still treating it as a single component. Nested files may nest, and a workspace member
may hold them.

Not in this milestone:

- A key that limits which modules outside a scope its components may import. Those
  imports stay under the parent's rules only.
- `archview metrics` for a scope. The scope's metrics are in `check --format json`.
- `[tool.archview]` in a nested `pyproject.toml`, which is never read for rules.

A scope's own `__init__.py`, when it imports or is imported, is a component named after
the scope id, the same way a project's root module is named after the project. It needs
an `allowed` entry like any child.

## Dogfood

`archview init --root src.webapp.services` on a copy of tiny-tale-backend wrote a
13-entry `allowed` table: the 12 child packages and the scope's own `__init__.py`.
`archview check` on the copy exited 0 in 0.26 s, with a `src.webapp.services` section
(`ok`) and no `webapp` cycle. The summary read `ok: src, 9 components and 1 nested
scope, no failing problems`.
