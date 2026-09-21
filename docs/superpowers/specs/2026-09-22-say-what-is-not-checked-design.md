# M10 — Say what you are not checking: design

Date: 2026-09-22. Status: approved in brainstorming, pending spec review.

GitHub issues #5, #8 and #10, which report the same failure three times in three
places. The reporter's phrasing, used twice: *a person writes the line, sees green,
and believes it took.*

Three silences, all reproduced before designing:

- `[archview.externals]` reads as a fence and is an opt-in allow-list. A component not
  named in it is unconstrained, so a declaration that looks like a ban protects one
  component and nothing else. Three reviewers missed it in sequence; the one that
  caught it did so by planting an import, not by reading the table.
- `type_checking_imports` defaults to `"ignore"`, so layer, workspace and forbidden
  rules are checked against runtime imports only. A six-package workspace ran for a day
  on rules enforcing about half of what its owners believed. Worse, setting the key in a
  workspace root's bare `[archview]` table does nothing at all — verified: with
  `type_checking_imports = "include"` there, a type-only cross-package import still
  passed.
- `source_roots = ["src", "tests"]` reports exactly what `["src"]` reports — verified:
  same components, no warning.

The common fix is not a feature. It is that archview must say what it is not checking.

## 1. The default flips

`type_checking_imports` defaults to **`"include"`**.

A type-only import is a dependency: it is a reason this file cannot be understood
without that one, and it becomes a runtime import the moment someone needs a value.
The surprise should run towards "archview checked more than I expected", never
towards "archview checked less".

This is a breaking change for any repo whose rules pass only because type-only edges
were invisible. It is free **now**, while v0.4.0 is on `main` and untagged, and costs
every adopter an upgrade surprise later. That timing is the reason it is in this
milestone rather than a later one.

Measured before deciding: archview itself has **zero** type-only imports, so its own
check is unaffected. The fixtures are not — `sample` has 1 of 10, `ts-sample` 4 of 18 —
so test expectations and golden files move, which is the flip working.

## 2. The key stops being a no-op where it does nothing

`type_checking_imports` in a workspace root's bare `[archview]` table is accepted and
ignored today. It becomes a **`ConfigError`** naming where it belongs: each package's
own rules file.

This is the same class as the silences above, and the same remedy ADR 0011 chose for a
stdlib target and ADR 0013 for an unpublished grant — a key that cannot take effect
fails loudly rather than reading as applied.

The workspace table already rejects unknown keys, so only the root's `[archview]` table
needs this.

## 3. `[archview.externals]` says when it is doing less than it looks

At check time, for each package named anywhere in `[archview.externals]`: find the
components that import that package and are **not themselves keys** of the table. If
any exist, emit a `Notice`:

```
note: [archview.externals].wiring allows bespoke_files, but book_service also imports
      it and is unconstrained. Only components named in [archview.externals] are checked.
```

**Why this scopes cleanly.** It fires only for packages actually named in the table, so
a repo with thirty third-party dependencies and two constrained components gets at most
two lines, not thirty. A component that *is* a key but omits the package is already
constrained and fails properly — it is not this note's business.

Kind: `partial_externals`. Deterministic: components sorted by name, packages sorted by
name, one notice per (component key, package) pair that is under-covering.

## 4. An opt-in closed mode

`externals_undeclared = "error"` beside the table (the reporter's name; it reads well).
When set, every component that imports anything outside the project must be a key in
`[archview.externals]`, exactly as `[archview.allowed]` requires a component to be
declared. A component that is not produces a problem of kind `undeclared_externals`.

The default stays open, so adoption is unchanged: a repo finishing its adoption closes
the door deliberately. This is the inverse of §1 — there the default was dangerous and
changes; here the default is a deliberate adoption ramp and stays.

Any value other than `"error"` is a `ConfigError`, so a typo cannot read as "off".

## 5. A source root that contributes nothing says so

A `source_roots` entry that yields no modules emits a `Notice` naming the entry:

```
note: source root 'tests' contributed no modules to package 'bespoke_files'; only code
      under the package is analysed
```

Kind: `empty_source_root`. Issue #10's larger half — letting a root outside `package`
contribute components at all — is **M11**, not this milestone. The note is worth having
regardless of how that lands, because it turns an afternoon of confusion into a line of
output.

## 6. Docs

`docs/06-using-archview-in-a-repo.md` contrasts `[archview.allowed]` and
`[archview.externals]` side by side: a component missing from `allowed` **fails**, a
component missing from `externals` is **unconstrained**. They are adjacent in every
config file and opposite in behaviour, and the current sentence is accurate but easy to
read past.

## 7. Testing

- The default flip: a test that a repo with a type-only edge and no explicit setting now
  reports it, and that `type_checking_imports = "ignore"` restores the old behaviour.
- The rejected key: a workspace root's `[archview]` table with the key is a `ConfigError`
  naming a package's own rules file.
- The partial-externals note: one component constrained, another importing the same
  package unconstrained; and the negative case, where every importer is a key, emits
  nothing.
- Closed mode: a component reaching outside with no entry fails; with an entry passes;
  a bad value is a `ConfigError`.
- The empty source root note, and its negative case.
- **`tests/test_self_check.py` asserts zero warnings on this repo.** Three new notice
  kinds land in this milestone; if any fires on archview itself, that is a real finding
  about archview's own rules, not a reason to weaken the assertion.

## 8. Out of scope

- Letting a root outside `package` contribute components (issue #10's second half) — M11.
- Scoping an exception to type-only imports (issue #8's second half) — M11.
- Any change to what `--hide-tests` means.

## 9. Done when

- `type_checking_imports` defaults to `"include"`, and setting it where it cannot take
  effect is an error.
- A `[archview.externals]` table that covers one component and not its neighbours says
  so, by name.
- `externals_undeclared = "error"` closes the table.
- A `source_roots` entry that contributes nothing says so.
- Issues #5 and #8's first halves are closed; #10's first half is closed.
