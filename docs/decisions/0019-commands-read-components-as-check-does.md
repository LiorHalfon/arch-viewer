# 19. The commands read components the way `check` does

Date: 2026-10-10 (0.6.0)

## Status

Accepted. Fixes GitHub issues #21, #22, #23, #24 and #25. Amends ADR 0009 (what
`cycles` reports) and ADR 0016 (how a nested file names modules).

## Context

A component refactor of tiny-tale-backend (its PR #573) filed five issues against
0.5.1. Each one is a place where two parts of archview disagreed about what a component
or a name is.

- `check` builds components from `[archview.components]`, and `cycles` builds them from
  the package tree. With the same rules file, `check` failed on `CYCLE root -> services
  -> root` and `cycles` printed `no cycles under shop` (#21).
- A nested file's `allowed` names its children relatively (`services`), but its
  component patterns were matched against full module names. A relative pattern
  matched nothing, and the check then failed with violations against a component
  nobody wrote (#22).
- Splitting `repos` into `repos_interfaces` and `repos_sql` left `repos/__init__.py`, a
  docstring, as a component named `repos`. It failed as undeclared until the rules file
  gained `repos = []`, a rule that exists only to satisfy the tool (#23).
- `cycles --root shop` and `deps shop` took a name relative to the package, and
  `graph --root shop` refused it (#24).
- Each module at a package's root is its own component, so a root used as a junk
  drawer hides a cycle. `wiring.py` imports a child, the child imports `paths.py`, and
  archview reports a DAG where a reader who thinks in directories sees a cycle. The
  refactor found five of these with a script of its own (#25).

## Decision

- **`cycles` reads a level that has a rules file by that file's components.** The
  project level is read by the root file's components when the project has one, and a
  nested scope by its own file's components, on the scoped model. That is
  `component_map`, `present_components` and `component_edges`, the functions `check`
  uses. Every other level is the package tree, as before. A cycle from a rules file
  carries its path (`rules` in the JSON, `in shop (components from archview.toml):` in
  the text), and its members are component names, the names `check` prints. `cycles`
  does not drop the imports `check` would drop through `exceptions` or
  `type_checking_imports = "ignore"`. A query shows the import structure, so it may show
  a cycle the rules tolerate, but never miss one they fail on. `--runtime-only` still
  drops TYPE_CHECKING imports when asked.

- **`graph` stays the package tree.** The viewer draws packages and modules, and
  components are an overlay for the rules. Drawing components in `graph` and `serve` is
  a larger change that no issue asks for. `metrics` already runs `check` and `why`
  works on modules, so neither had the gap.

- **A nested file's module patterns are read below its scope.** In
  `app/shop/archview.toml`, `repos.sql` in `[archview.components]` means
  `app.shop.repos.sql`, and the same holds for `importer` and `imported` in
  `[[archview.exceptions]]`. A pattern that starts with the scope's own name is read
  as written, so files written for 0.5.1 keep working. `Config.scope` records the
  scope, and `ComponentMap` and the exception matcher read a pattern below it at the
  point of use. So `init --root` writes the patterns back as the user wrote them, and a
  pattern that matches nothing is reported as written, with `below app.shop`. The root
  file is unchanged. Its patterns may name an extra source root (`tests.**`), which a
  prefix would break.

- **What is left of a split package is a component only when it imports or is
  imported.** A component is a leftover when every file it owns is a package's
  `__init__` and other components own modules below those packages. Such a component
  is present only when an import touches it, which is the rule the project's own root
  module already follows. Once present, its `UNDECLARED` hint names the package and the
  components that hold its modules. An `allowed` entry that names an untouched leftover
  gets an `unknown_component` notice saying it needs no rule, not "has no modules". A
  package that holds only an `__init__`, with nothing taken from it, is still a
  component, so a new package still needs a human's rule.

- **`graph --root` resolves names as the queries do**, through `resolve`, with the same
  close-match suggestions.

- **`--fold-root-modules` on `cycles` and `graph`.** A package's own modules, its
  `__init__` and the loose modules beside its children, count as one member named after
  the package. In the package tree that is a box whose id is the package itself. At a
  level read by a rules file, the loose root modules join the component named after the
  package, unless an explicit pattern claims them. The flag is a lens and changes no
  rule. A workspace root refuses it, as it refuses `--root`.

## Rejected approaches

- **A `check` warning when a package's root modules sit both above and below its
  children** (#25's second idea). `check` only looks at the levels a rules file
  governs, and three of the five root cycles the refactor found sat inside a component,
  where no rule looks. The flag finds them at every level.
- **A `ConfigError` for a nested pattern that matches nothing** (#22's second idea).
  It points at the mistake but keeps the inconsistency. With patterns read below the
  scope, the relative spelling is no longer a mistake.
- **Prefixing the patterns when the nested file is loaded.** `init --root` would then
  write the user's relative patterns back in full, and the "matches no module" warning
  would name a pattern the user never wrote.
- **Dropping every component that owns only `__init__` files.** A new package with
  only an `__init__` is a new component, and a human decides what it may import, so
  only the remains of a split are left out.

## Consequences

`cycles` output changes on a repo with a rules file. At the project level and in each
nested scope, its members are component names, as in `check`, where they used to be
the full names of child packages. The JSON gains `rules` on every cycle, null for a
package-tree level. Since `cycles` now reads the nested rules files, one it cannot read
stops it with exit 2, as it stops `check`. A rules file that kept a rule for a leftover
`__init__` now gets a notice. No check fails that passed before.

## Dogfood

On tiny-tale-backend's `dev`, `check` gives the same result, plus one notice on
`src/webapp/archview.toml`'s `repos = []`. After removing that rule and writing the
three `repos` patterns relative to `src.webapp`, 0.5.1 reports 8 problems and 17
warnings, and this release passes. `cycles --fold-root-modules` on the commit before
PR #573 finds the five root cycles the refactor's script found: `src.webapp`,
`src.story_generator`, `story_generator.providers`, `story_generator.template_rendered`
and `webapp.services.bespoke`. It finds a sixth in `src.bespoke_story`, whose
`types.py` and `recording.py` sit on either side of `ports`. On the #573 branch it finds
the three the issue says are still there, plus that one.
