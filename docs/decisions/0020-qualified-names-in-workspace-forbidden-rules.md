# 20. Qualified names in a workspace's `forbidden` rules

Date: 2026-10-10 (0.6.0)

## Status

Accepted. Fixes GitHub issue #19. Builds on ADR 0013 (a package's public surface) and
ADR 0018 (qualified names in a single package).

## Context

In workspace mode `allowed` takes qualified targets (`plugin = ["core.ports"]`), but
`[[archview.workspace.forbidden]]` matched packages only. A rule with
`to = "core.model"` never matched the pair `(plugin, core)`, so it never fired, and
`check` said `ok` with no notice. ADR 0018 fixed the same gap in a single package and
left this one open.

While fixing it, a second gap showed up. For a TypeScript member, `cross_edges`
recorded the component an import reaches as `core/index.ts`, with the package's own
separator, while every rule helper splits a qualified name on the dot. `owner` cut
`core/other.ts` to `core/other`, which is no package, so `public` never checked a
TypeScript import: one of an unpublished file passed. A qualified grant could not
narrow a TypeScript sibling either.

## Decision

- **A reached component is spelled the way rules spell it.** `cross_edges` joins the
  component to its package with a dot in both languages: `core.ports`, and in
  TypeScript `core.index.ts` for a file or `core.ports` for a directory. The view
  still draws a published component under its node id, `core/index.ts`.

- **A `forbidden` rule with a qualified side is checked import by import.** `from` is
  matched against the component of the importing module, and `to` against the
  component the import reaches, with `rules/qualified.py`'s `admitted`. A plain side
  still matches the package, and `*` matches every package. The problem names the part
  the rule names (`FORBIDDEN plugin -> core.model`). Each import goes to the first rule
  it breaks, and an import a qualified rule caught is left out of the package-level
  `allowed` check and the public-surface check, so it is reported once, as a single
  package reports it. It still counts toward cycles between packages. An import whose
  component could not be placed cannot break a qualified `to`; it already gets an
  `unplaced_import` notice.

- **A qualified name that places nowhere is a `ConfigError`.** In a workspace a
  qualified name is a package, a dot, and one of its components, a child of the
  package's root, the names `public` uses. A name in `allowed` or `forbidden` whose
  package is not a member, or whose component that package does not have, stops the
  check with exit 2, naming the key and listing the components the package has. This
  is ADR 0018's rule for a single package.

- **A plain `forbidden` name that is no package gets a notice.** The rules between
  packages see only imports between them, so `to = "requests"` there can never fire.
  It gets an `unknown_component` notice instead of nothing.

## Consequences

A workspace rule that named a part and never fired now fires. A TypeScript member's
`public` list is now enforced, so a workspace that imports an unpublished TypeScript
file starts failing with `PRIVATE`. That was the documented behaviour all along. A
qualified grant or rule that names a missing component, which used to fail with
misleading violations or pass silently, now stops the check with exit 2.

Qualified names in a workspace stay one level deep (`core.model`, not
`core.model.sub`), as ADR 0013 defined them, while a single package's may name any
module below a component (ADR 0018).
