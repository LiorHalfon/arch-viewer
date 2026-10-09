# 18. Qualified names in a single package's rules

Date: 2026-10-10 (0.5.1)

## Status

Accepted. Fixes GitHub issue #17. Builds on ADR 0013 (a workspace's qualified grant)
and ADR 0016 (rules files inside sub-packages).

## Context

Since ADR 0016 a nested rules file sees only the imports between its own children,
and imports that leave the scope are left to the root. The root sees each top-level
package as one component. So "the plugin may import only the core's `ports` and
`types`" belonged to neither file. The docs allowed a qualified grant
(`server = ["core.ports"]`) only in workspace mode. In a single package, 0.5.0 warned
that `bespoke_story.ports` "has no modules" and then failed every import into
`bespoke_story`, including the ones the grant was written to allow. A qualified
`forbidden` target was worse: it never matched a component pair, so it printed `ok`
with no notice at all.

## Decision

- **A qualified name is `component.part`.** The part is a module path below the
  component, written with dots, and covers that module's whole subtree. It may appear
  in an `allowed` value and on either side of a `forbidden` rule (and so in `layers`
  and `independent`, which expand to `forbidden`). `allowed` keys and
  `[archview.externals]` keys still name whole components.

- **One meaning in both modes, in one module.** `rules/qualified.py` holds what a
  qualified grant means: a grant that names parts of `X` admits only imports into
  those parts; a plain `X` beside them adds nothing; an import of `X`'s own root is
  outside every part; a check of whole components or packages sees the grant as `X`.
  Workspace mode and single-package mode both call it. The only difference is where
  the reached name comes from: a workspace places each cross-package import itself
  (ADR 0013), and a single package uses the imported module's path below the project.

- **Placing a name is a load-time duty, and failing to is a `ConfigError`.** Before
  checking, every dotted name in `allowed` and `forbidden` that is not itself a
  component must start with a component and name a module or package that this
  component owns. Otherwise `check` exits 2, naming the file, the key and the name.
  This is ADR 0011's rule for stdlib targets applied to parts: a rule that cannot fire
  must not look like one that holds.

- **Python reads every dotted name as qualified; TypeScript only one that starts with
  a component.** grimp squashes an outside Python import to its top-level package, so a
  dotted outside name could never match. An npm package can have a dot in its name
  (`chart.js`), so in TypeScript a dotted name whose first segment is no component stays
  an outside name, as before.

- **A dotted name that is a component stays a component.** A nested scope's own root
  module is a component named after the full scope id (`"src.webapp.services"`); the
  project name, `[archview.components]` keys and `allowed` keys are never read as
  qualified.

- **A violation names the part it reached.** An import into `core.desk` under a grant
  of `core.ports` reports `plugin -> core.desk`, cut to the component and one part,
  the same depth a workspace reports. The hint lists the parts that are allowed.

## Rejected approaches

- **A key in the nested file for imports that leave its scope.** The nested file in
  the plugin would have to name modules of a package outside it, which is the root's
  view, and the core's nested file would have to name every importer. The root already
  sees both ends.
- **Expanding a qualified grant into `[archview.components]` patterns.** That changes
  what the core is to the cycle check, the metrics and the view, to express one grant.

## Consequences

A plugin's reach into its core can be written in the root file with no workspace.
A rules file that used a dotted name in these places and got a warning, or nothing,
now gets exit 2 if the name cannot be placed. That includes a dotted outside name in
Python (`to = "openai.types"`), which never fired.

Not in this release: `[archview.externals]` keyed by a part of a component, so that
only some of a package's modules may import a vendor SDK. A qualified `forbidden.from`
covers the deny form of it (`from = "plugin.models"`, `to = "openai"`); the allow-list
form needs its own design (GitHub issue #18). Workspace `forbidden` rules still match
packages only, so a qualified `to` there never fires and says nothing (GitHub issue #19).
