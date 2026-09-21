# M11 — Test code under the rules, and type-only exceptions: design

Date: 2026-09-22. Status: approved in brainstorming, pending spec review.

The second halves of GitHub issues #8 and #10. M10 closed the silences those issues
reported; these two are the genuine feature asks left behind, and both are about saying
something the rules file currently cannot express.

## 1. Test code under the rules (issue #10)

### The problem

With `package` scoping, nothing outside `src/<pkg>/` can be a component, so no rule can
reach a test file. Verified before designing: `source_roots = ["src", "tests"]` on a
package laid out as `src/<pkg>/` beside `tests/` reports exactly what `["src"]` reports.
M10 made that say so; it did not make it work.

That matters because tests break boundaries for real reasons, and it would be good to
say which ones are allowed. The reporter's case: a core package must never import a
plugin, and its rules enforce that — but `component/tests/test_live.py` legitimately
wires the real vendor, and is invisible to the check. They could neither enforce "no
test may import a plugin except this one" nor state the exemption in archview, and fell
back to a ruff `TID251` `per-file-ignores` entry — the duplication issue #1 removed.

### The decision

**Shape 1: `source_roots` means what it says.** A root outside `package` contributes
components, named by their path. `tests/test_live.py` becomes component `tests`, module
`tests.test_live`.

Chosen over an opt-in `test_roots` key because it needs no new syntax: `[archview.allowed]`,
`[[archview.forbidden]]` and `[[archview.exceptions]]` all work on the result unchanged,
and `--hide-tests` already exists to keep tests out of the production picture.

### What this changes

- A module under a configured source root but outside `package` gets an id rooted at its
  path relative to that root, exactly as a module under `src` is today.
- Its component is the first segment, exactly as inside the package.
- `present_components` therefore gains these components, so **`[archview.allowed]` will
  demand they be declared** — which is the `undeclared` rule working, but it means a repo
  that adds `tests` to `source_roots` must then say what tests may import. That is the
  point; it is also a real adoption cost, so §4 covers it.
- `--hide-tests` keeps working: `model/filter.py`'s `TEST_NAMES` already recognises these
  names, and now has something to filter.

### The mechanism, and what it rules out

Reading the code settled a question the first draft left open, and narrowed the feature.

`build_model` builds **one** package through grimp, and `ComponentMap._default` returns
`None` for any module not under `package` — so a module outside it is an *outside name*,
i.e. indistinguishable from a third-party dependency. Simply "letting roots contribute"
would make `tests` look like a PyPI package.

The mechanism is the one M9 already proved for sibling packages: **build the grimp graph
over the analysed package plus every other top-level package found under a configured
root.** `grimp.build_graph(package, *extras)` resolves them together, exactly as
`extract/siblings.py` does across a workspace.

- `open_project` finds, per configured root, the top-level packages under it — the scan
  `_packages` already performs.
- The analysed one stays `Model.project`; the others are **extra internal roots**.
- `_is_internal` and `ComponentMap` take the set of internal roots rather than one name.
- **Each extra root package is one component, named after itself.** `tests.test_live`
  belongs to component `tests`, exactly as the project's own root module is a component
  named after the project (ADR 0006).

**Only packages count, not loose modules.** A directory with an `__init__.py` (or a
namespace package) under a configured root becomes a component; a bare `.py` file sitting
directly in a root does not, because grimp graphs packages and there is nothing to name.

That rules out one spelling, and the ruling out is the useful part:

| `source_roots` | result |
|---|---|
| `["src", "."]` | `tests/` is a package rooted at the repo, so it contributes; component `tests`, modules `tests.test_live` |
| `["src", "tests"]` | contributes nothing, and M10's `empty_source_root` notice keeps firing |

Issue #10 wrote the second. It is the wrong spelling and always was: a package `tests/`
with an `__init__.py` is rooted at the *repo*, not at `tests/`. Verified against M10's
behaviour while writing this — the notice fires for it today, correctly, and this
milestone does not silence it. The documentation must say which spelling to use, because
the reporter guessed the other one and got silence for an afternoon.

### What this does not change

`package` still determines what the project *is*. A root outside it contributes
components but never renames the project, and the root node stays the package.

## 2. Type-only exceptions (issue #8)

### The problem

M10 flipped `type_checking_imports` to `"include"`, so type-only edges are now checked.
That immediately creates a need the rules file cannot express. The reporter's design says
`screens -> ui`, and type-only imports from `api` are fine: a screen may name the shape
of a prop it receives but must never call the API itself.

`[[archview.exceptions]]` cannot scope to type-only, so the exception they had to write is
wider than the rule they meant, and its `reason` is a comment asking humans not to use it
for what it permits — which is the thing archview exists to stop needing.

### The decision

`[[archview.exceptions]]` gains an optional `kind`:

```toml
[[archview.exceptions]]
importer = "web/screens"
imported = "web/api"
kind     = "type_only"
reason   = "a screen may name the shape of a prop it receives, never call the API"
```

- Absent `kind` means any import, which is today's behaviour and keeps every existing
  rules file working.
- `kind = "type_only"` exempts **only** imports whose `type_checking` flag is set. A
  value import matching the same importer/imported pair is **not** exempted and fails.
- Any other value is a `ConfigError`, so a typo cannot silently widen an exception.

`Exemption` gains `kind: str | None = None`; `_exemption` gains the one condition. Both
the package-level and workspace-level exception paths use `_exemption`, so this works at
both levels from one change.

### Why not a per-exception `type_checking_imports`

The issue offered that as an alternative spelling. `kind` is narrower and reads as what
it is — a property of the import being exempted, not a re-configuration of the checker
for one rule. It also leaves room for other kinds later (`lazy` is the obvious one) without
a second mechanism.

## 3. Interaction between the two

A type-only exception can name a test component, and a test component can appear in
`allowed`. Nothing special is needed: both features land in existing vocabulary.

## 4. Adoption

Adding a root outside `package` to `source_roots` turns previously invisible modules into
components, and with an `[archview.allowed]` table present, an undeclared component
fails. That is a hard stop appearing on an upgrade for anyone who already had a
non-contributing entry — which M10 now warns about, so they have been told.

This is acceptable because it only affects a repo that **explicitly listed** a root
outside its package, and until M10 that entry did nothing at all. A repo that never did
so is unaffected.

`archview init --force` regenerates the allowed table including the new components, which
is the documented path.

## 5. Testing

- `source_roots = ["src", "."]` with `tests/` a package beside `src/<pkg>/`: `tests`
  becomes a component, `tests.test_live` a module, a rule on it is enforced, and M10's
  `empty_source_root` notice stops firing for `"."`.
- `source_roots = ["src", "tests"]`: still contributes nothing and still warns. Pin that,
  because it is the spelling the issue used and the documentation now steers away from.
- A loose `.py` directly under a configured root contributes nothing — pinned, since it is
  the boundary of what "only packages count" means.
- The reporter's exact case: "no test may import a plugin, except this one" expressed as
  a `forbidden` rule plus a module-level exception.
- `--hide-tests` still removes them.
- A type-only exception exempts a type-only import and **does not** exempt a value import
  between the same pair — that negative case is the whole point of the feature.
- An unknown `kind` is a `ConfigError`.
- A type-only exception at workspace level, since `_exemption` is shared.
- `tests/test_self_check.py` asserts zero warnings on this repo. archview's own
  `archview.toml` sets no `source_roots`, so §1 does not affect it.

## 6. Out of scope

- Any change to what `--hide-tests` means, or to `TEST_NAMES`.
- Loose modules directly under a source root becoming components.
- Inferring which roots are test roots. The user lists them.
- `kind` values beyond `type_only`. `lazy` is the obvious next one and can follow when
  someone needs it.

## 7. Done when

- A `tests/` directory beside `src/` contributes components that rules can name, and the
  reporter's "no test may import a plugin except this one" is expressible in archview
  alone, with no ruff `per-file-ignores`.
- An exception can be scoped to type-only imports, and a value import between the same
  pair still fails.
- Issues #8 and #10 are closed.
