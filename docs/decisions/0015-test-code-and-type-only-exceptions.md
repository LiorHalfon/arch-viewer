# 15. Test code under the rules, and type-only exceptions

Date: 2026-09-22 (M11)

## Status

Accepted. Implements `docs/superpowers/specs/2026-09-22-test-code-and-type-only-exceptions-design.md`
(GitHub issues #8, #10). Builds on ADR 0006 (checker semantics) and ADR 0014 (M10's
`empty_source_root` warning).

## Context

M10 (ADR 0014) closed three silences, among them a `source_roots` entry that
contributed nothing and a type-only import checked or not depending on a default
nobody chose. It made both say so; it did not make either work the way the
reporters actually wanted. Issue #10's reporter needs a rule that can reach a test
file: `component/tests/test_live.py` legitimately wires the real vendor, and there
was no way to say "no test may import a plugin, except this one" — they fell back
to a ruff `TID251` `per-file-ignores` entry, the duplication issue #1 removed.
Issue #8's reporter needs an exception narrower than "any import": once M10 flipped
`type_checking_imports` to `"include"`, the exception they had to write to keep a
type-only prop shape legal was wide enough to also legalise the value import it was
never meant to permit, and its `reason` became a comment asking humans not to use
what it permits.

## Decision

### Test code under the rules (issue #10)

- **`source_roots` means what it says, rather than an opt-in `test_roots` key.** No
  new syntax: `[archview.allowed]`, `[[archview.forbidden]]` and
  `[[archview.exceptions]]` all work on the result unchanged, and `--hide-tests`
  already exists for the production-only picture. A `test_roots` key would only be a
  second way to say the same thing.

- **The mechanism, and why it had to be this one.** `build_model` builds one package
  through grimp, and `ComponentMap._default` returns `None` for any module not under
  `package` — so a module outside it is an *outside name*, indistinguishable from a
  third-party dependency. Naively "letting roots contribute" without changing that
  would make `tests` look like a PyPI package: present in the graph, absent from the
  component map, nameable by nothing. The fix instead builds the grimp graph over the
  analysed package plus every other top-level package found under a configured root
  — `grimp.build_graph(package, *extras)` — the same multi-package call
  `extract/siblings.py` already proved for sibling packages in M9. `_is_internal` and
  `ComponentMap` now take the set of internal roots rather than one name, so a module
  under an extra root is internal from the start and never mistaken for an outside
  name in the first place.

- **Only packages count, not loose modules.** grimp graphs packages; a bare `.py`
  sitting directly under a configured root has nothing to name. `_packages` only
  admits a directory that itself holds `.py` files, exactly as it already did for
  the project's own package - and, given an explicit root, without `find_packages`'
  own `SKIP_DIRS`/dotfile filtering. That bypass is *why* the mechanism works at
  all, not an accident of it: that same filtering is exactly what keeps `tests/`
  invisible under zero-config discovery (`SKIP_DIRS` names `tests`, `test` and
  `testing` outright), so making an explicit root contribute `tests/` requires not
  applying it there. The bypass is not scoped to `tests/` - it reaches any other
  directory holding `.py` files under that root just as readily (`docs/06` covers
  the two ways to narrow it back down).

- **Each extra root package is one component, named after itself** — `tests.test_live`
  belongs to component `tests` — consistent with ADR 0006's treatment of the
  project's own root module as a component named after the project.

- **Which spelling to use, and that the issue used the other one.** `["src", "."]`
  works: `tests/` is a package rooted at the repo, so it contributes — component
  `tests`, module `tests.test_live`. `["src", "tests"]` contributes nothing, because
  a package `tests/` with an `__init__.py` is rooted at the *repo*, not at `tests/`:
  the repo is what makes `tests` importable, and `"tests"` as a configured root names
  a directory one level too deep. Issue #10 wrote the second spelling, guessed
  wrong, and got silence for an afternoon. M10 made that spelling warn
  (`empty_source_root`); this milestone keeps it warning rather than quietly
  accepting both spellings, so `docs/06` says plainly which one to use instead of
  archview guessing on the reporter's behalf.

### Type-only exceptions (issue #8)

- **`kind` over a per-exception `type_checking_imports`.** The issue offered the
  latter as an alternative spelling. `kind` is a property of the import being
  exempted — this one edge, when it is type-only — not a re-configuration of the
  checker for one rule; a per-exception `type_checking_imports` would read as
  toggling the checker's own default locally, for reasons that have nothing to do
  with the checker's default and everything to do with what this one pair of
  components may share. It also leaves room for a `lazy` kind later without a
  second mechanism — `Exemption` gains one optional field, not one field per future
  distinction.

### A latent bug this milestone surfaced and fixed

Worth recording because it is invisible. grimp locates each top-level package with
`importlib.util.find_spec`, which returns an already-imported module's cached spec
without consulting `sys.path` at all. Any multi-package graph built in a process
that has already imported a same-named module therefore resolves against the wrong
package — silently, with no error. It surfaced here because this project's own test
suite is a package called `tests`, which is also issue #10's own example name:
graphing a fixture repo whose analysed project names a component `tests`, from
inside the pytest process that is itself running the package `tests`, resolves
against the running suite instead of the fixture unless something intervenes.

`extract/siblings.py`'s workspace resolution (M9) had the identical exposure —
`resolve_targets`'s own `grimp.build_graph` call was unguarded — and had it since
that milestone. It is fixed in the same commit as this one. Record that honestly:
it shipped, it was silent, and it was found only because this milestone happened to
collide with it — the fixture workspace's member names (`core`, `plugin`) never
matched an already-imported module, so nothing in CI ever triggered it.

The fix is a guard, not a blanket eviction. `_unimported` evicts a cached
`sys.modules` entry for a graphed root name only when it resolves somewhere other
than the root about to be graphed, so a package already imported from exactly that
root — this project checking itself, `archview` importing `archview` — is never
touched. An unconditional evict-everything version was tried first and broke
self-check for the opposite reason: it evicted `sys.modules["archview"]` and its
loaded submodules — the running program's own code — for the duration of the very
`grimp.build_graph` call that code was making.

## Consequences

Test code becomes reachable by the same rules vocabulary as production code, and a
type-only import can be exempted without also legalising the value import it was
never meant to permit. Both land in existing tables; nothing about `allowed`,
`forbidden` or `exceptions` changed shape.

Known limitations:

- **A regular package whose `__path__` has several static entries** — via
  `pkgutil.extend_path`, or simply a runtime `__path__.append(...)` in its own
  `__init__.py` (a plugin-system idiom: `spec.submodule_search_locations` *is* the
  same list object as `module.__path__` for a regular package, so a mutation of
  one is a mutation of the other, and reaches grimp too) — does not self-heal from
  a `sys.path` change, and the guard skips eviction if any one entry matches,
  leaving a stale entry for grimp to walk. This is the permissive direction, which
  is the worse one: a stale entry can make the check silently pass against the
  wrong code rather than merely fail to build. It needs a colliding top-level name
  that is itself a manually multi-rooted regular package, a legacy pattern rare
  enough that this was accepted rather than chased further.
- **A namespace package present at more than one location on `sys.path` contributes
  all of them, not just the one under the graphed root.** grimp's own package
  finder returns every entry of `spec.submodule_search_locations`
  (`grimp/adaptors/packagefinder.py`, `determine_package_directories`) and walks
  all of them. A namespace package recalculates `__path__` live from a fresh
  `find_spec` - which is what makes the eviction guard unnecessary for it in the
  first place, unlike the regular-package case above - and that live recalculation
  always finds the *correct* directory; it does nothing to stop a second,
  colliding one elsewhere on `sys.path` from being found and walked too. That is
  inherent to namespace-package semantics (every matching location merges into one
  `__path__`), not a gap this guard could close: there is no single "the"
  `__path__` to compare against one expected root the way a regular package's is.
- **Adding a root turns previously invisible modules into components.** An existing
  `[archview.allowed]` table will now fail as `undeclared` until it names them.
  That is the `undeclared` rule working (ADR 0006), and it only affects a repo that
  explicitly listed such a root — which until M10 did nothing at all and since M10
  has been warning about it. `open_project` computes `extra` from the sibling
  packages `_packages` found only when `config.source_roots` is non-empty
  (`project.py`); a repo with no `source_roots` at all graphs exactly as it did
  before this milestone, even one where `find_packages` happens to resolve to
  several top-level packages - the shape `--package` exists for (Finding 1,
  differential review, fixed the same milestone it shipped in).
- **`_unimported`'s eviction mutates process-global `sys.modules`, live, while
  `serve --watch` is running.** `watch()` calls `reload()` - hence `build_model`,
  hence `resolve_targets`/`_unimported` - from a background daemon thread, while
  FastAPI dispatches its own sync routes on a thread pool; both share this one
  process's `sys.modules`. A project package whose top-level name collides with an
  installed dependency (`rich`, `click`, `yaml`, …) could be evicted during that
  window if a sync route happens to import that name while a reanalysis is
  resolving cross-package imports. This is a different shape of exposure than
  `_importable`'s pre-existing `sys.path` mutation, not merely a smaller one:
  `sys.path` only affects names not yet cached, while eviction targets precisely
  the names the process already holds.
