# 14. Say what is not checked: the include default, closed externals, empty roots

Date: 2026-09-22 (M10)

## Status

Accepted. Implements `docs/superpowers/specs/2026-09-22-say-what-is-not-checked-design.md`
(GitHub issues #5, #8, #10). Builds on ADR 0011 (rules for outside imports).

## Context

GitHub issues #5, #8 and #10 report the same failure in three places. The reporter's
phrasing, used twice: *a person writes the line, sees green, and believes it took.*

Three silences, all reproduced before designing:

- `[archview.externals]` reads as a fence and is an opt-in allow-list. A component
  not named in it is unconstrained, so a declaration that looks like a ban protects
  one component and nothing else.
- `type_checking_imports` defaulted to `"ignore"`, so layer, workspace and forbidden
  rules were checked against runtime imports only — and setting the key in a
  workspace root's bare `[archview]` table did nothing at all, verified: with
  `type_checking_imports = "include"` there, a type-only cross-package import still
  passed.
- `source_roots = ["src", "tests"]` reported exactly what `["src"]` reported —
  verified: same components, no warning.

The common fix is not a feature. It is that archview must say what it is not
checking.

## Decision

- **The default flips to `"include"`.** A type-only import is a dependency: it is a
  reason a file cannot be understood without the other one, and it becomes a runtime
  import the moment someone needs a value instead of a name. The surprise should run
  towards "archview checked more than I expected", never the other way. This is
  breaking for any repo whose rules pass only because type-only edges were invisible
  — archview itself has zero type-only imports, so its own check is unaffected, but
  `sample` (1 of 10 imports) and `ts-sample` (4 of 18) both move, which is the flip
  working. It lands now, while v0.4.0 is on `main` and untagged, because it is free
  today and costs every adopter an upgrade surprise later.

- **A key that cannot take effect is an error.** `type_checking_imports` in a
  workspace root's bare `[archview]` table used to be accepted and silently ignored —
  each package is checked with its own config, never the root's. It is now a
  `ConfigError` naming where the key belongs: the package's own rules file. This is
  the same remedy ADR 0011 chose for a rule naming a stdlib target and ADR 0013 for a
  grant naming a component its owner does not publish — a key that cannot take effect
  fails loudly rather than reading as applied.

- **The `partial_externals` notice is scoped to packages the table already names.**
  At check time, for each package named anywhere in `[archview.externals]`, archview
  finds the components that import that package and are not themselves keys. If any
  exist, it emits one notice per *package* — not per (key, package) pair — naming
  every key that grants it:

  ```
  [archview.externals] allows openai for llm, but checkout also imports it and is
  unconstrained. Only components named in [archview.externals] are checked.
  ```

  Scoping to named packages is what keeps this quiet: a repo with thirty third-party
  dependencies and two constrained components gets at most two lines, not thirty. A
  component that *is* a key but omits the package is already constrained and fails
  properly; that is not this notice's business.

- **`externals_undeclared` defaults open while `type_checking_imports` flips.** These
  look like the same shape of decision and are not. `type_checking_imports` used to
  default to a value that made rules quietly half-enforced — every existing repo was
  already exposed, whether or not it knew. Flipping it is fixing a dangerous default.
  `externals_undeclared = "error"` is an adoption ramp: the default stays `"allow"`
  so a repo can constrain `llm` today and leave everything else alone, exactly as
  `[archview.externals]` itself was designed to be adopted one component at a time
  (ADR 0011). A team closes the table when it decides adoption is done, not because
  archview decided for it. Any value other than `"error"` is a `ConfigError`, so a
  typo cannot read as "off".

- **`undeclared_externals` does not suppress when a `forbidden` rule covers the same
  edge.** `forbidden` already wins over the `outside` problem an undeclared *edge*
  produces (ADR 0011) — but that is two edge-level claims restating one fact: the
  import is not allowed, whether because it was never on the allow-list or because it
  is explicitly banned, and printing both would say the same thing twice. Whether a
  component is declared in `[archview.externals]` at all is a different,
  component-level claim: the table is either complete or it is not, and one target
  being separately banned does not make the table complete. A component that reaches
  outside the project without being a key still gets `undeclared_externals` even when
  one of its outside imports is also `forbidden`.

- **The empty-source-root notice is answered per language.** A `source_roots` entry
  that contributes no modules to the package emits a notice naming it. The check
  cannot be string-matching against the model's file paths, because the model does
  not record which configured root produced each file — `Node.file` is just a path.
  Python answers this from `Project.source_root`: `_packages`/`_choose` already pick
  exactly one winning root per package, so comparing each configured root's resolved
  path against the winner's resolved path is exact, and a single configured root can
  never be empty by construction (`_choose` would have raised first). TypeScript asks
  the model directly instead, because `Project.source_root` there is `project.repo`,
  not the configured root — but a TypeScript `Node.file` carries the configured root
  as a literal prefix by construction, so checking whether any node's file starts
  with a (normalised) root answers the same question truthfully for that language.

  **This took three fix rounds, and it is worth recording why.** The first design put
  the check in the wrong layer: string-prefix matching against `Node.file`, inside
  `check()`. That cannot answer "which configured root produced this file", because
  the model never records it — and it showed immediately: `build_model` resolves a
  `"."` root away before it ever reaches `Node.file`, so the very root that built the
  model read as contributing nothing. The first fix patched that symptom directly —
  treat a root spelled `"."` or `""` as always non-empty — which introduced the
  opposite bug: a `"."` root that genuinely contributed nothing would now silently
  pass, unconditionally, which is the exact failure this milestone exists to close.
  The second fix moved the check to `project.py` and compared resolved paths against
  `Project.source_root`, which is exact for Python — but it also carried a `len(roots)
  <= 1` guard whose own comment admitted `Project.source_root` is `project.repo`,
  not the configured root, for TypeScript. That guard made the notice never fire for
  a single-root TypeScript project regardless of whether that root was right, hiding
  the language's real bug behind a root *count* instead of answering the question.
  Only the third round separated the two languages and gave each its own truthful
  answer. Nothing about the difficulty was exotic; it was three rounds of not yet
  asking the question a layer already knew the answer to.

## Consequences

Agents get a hard stop, or at minimum a visible note, at every place a person could
write a rule, see green, and be wrong about what it covers.

Limitations, stated plainly:

- **The `partial_externals` notice sees only what the graph contains.** A package
  named in `[archview.externals]` that nothing currently imports produces no notice
  at all — the table can still be wrong (granting access to a package no one uses
  yet, say) in a way archview cannot see, because there is no edge to compare against.
- **`Project.source_root` still does not carry the configured root for TypeScript.**
  That is why the empty-source-root check has a separate TypeScript branch at all,
  and it is a real asymmetry between the two languages' `Project`, not just this
  notice's concern. Fixing `Project.source_root` itself is separate work.
