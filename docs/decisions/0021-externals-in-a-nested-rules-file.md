# 21. What a sub-package's children may import from outside the project

Date: 2026-10-10 (0.6.0)

## Status

Accepted. Fixes GitHub issue #18. Amends ADR 0016, which kept `externals` and
`externals_undeclared` out of nested rules files.

## Context

tiny-tale-backend's `bespoke_openai` plugin wants one rule: only `language` and
`images` may import `openai`. The root's `[archview.externals]` is keyed by whole
components, so it can only say what `bespoke_openai` as a whole may import. 0.5.1 could
express the deny form, one `[[archview.forbidden]]` per part and package (tiny-tale has
four), but a module added to the plugin later is unconstrained.

Issue #18 offered two spellings. Keys in the root that name a part
(`"bespoke_openai.language" = ["openai"]`) need a part's key to override its
component's key, and a new answer for closed mode, the `partial_externals` notice, and
the names in the report and the baseline. The other spelling is `externals` in the
plugin's own rules file, keyed by its children, and tiny-tale already has that file.

## Decision

- **A nested rules file may hold `[archview.externals]` and `externals_undeclared`.**
  The keys are the scope's children, as in its `allowed`. Both keys leave the
  root-only list.

- **A scope sees what its children import from outside the project.** `scoped_model`
  keeps the imports that leave the project from inside the scope, with the outside
  packages they reach. Imports into the rest of the project are still dropped; the
  rules above the scope check those. `check()` then runs unchanged on the scope, so
  `OUTSIDE`, closed mode's `UNDECLARED EXTERNALS`, the `partial_externals` notice, the
  stdlib check and the scope's own baseline all work on the children with no new code.

- **Narrow, never widen.** An import has to pass every rules file that covers it. The
  root judges the component as a whole and the nested file judges the child, so a
  nested file can only take away what the root allows. tiny-tale's case reads: the
  root allows `openai` for `bespoke_openai`, or leaves it unconstrained, and the
  plugin's file allows it for `language` and `images` only.

- **`[[archview.forbidden]]` in a nested file may name a package outside the project.**
  It fires like one in the root. The "can never fire" notice, which used to cover any
  target that is not a child of the scope, now covers only a target that names a module
  in the rest of the project. A package that nothing imports yet is the ban working, as
  at the root (issue #5).

- **`init --root X --externals`** writes the nested file's `[archview.externals]` from
  today's imports, as `init --externals` does at the root.

- **A root `externals` key that names a part of a component is a `ConfigError`.** It
  would never fire, and the error says to give the component a rules file of its own.
  Before, it got a "has no modules" notice. This is ADR 0018's rule for parts that
  cannot be placed.

- **The viewer keeps a scope's failing outside package in view**, as it does for the
  root's (`outside_targets` reads the scopes).

## Rejected approaches

- **Part keys in the root's `[archview.externals]`.** The same rule in one file, but
  a part's key has to override its component's key to say "only these may". Then a
  part can widen what its component allows, and every question the issue lists needs a
  new rule. The nested file answers them with the checker as it is.

## Consequences

tiny-tale's four deny rules for `bespoke_openai` become one table in
`src/bespoke_openai/archview.toml`, and with `externals_undeclared = "error"` a new
module in the plugin fails until someone declares what it imports. On a snapshot of
tiny-tale's `dev`, the table that `init --root bespoke_openai --externals` wrote passes,
an `openai` import added to `models.py` fails as
`OUTSIDE models -> openai not allowed by [archview.externals.models]`, and a new
`billing.py` that imports `httpx` fails as undeclared.

A nested file that already had a `forbidden` rule naming a package outside the project
used to get a notice, and the rule now fires. Nested files without `externals` or
such a rule report exactly what they did before.
