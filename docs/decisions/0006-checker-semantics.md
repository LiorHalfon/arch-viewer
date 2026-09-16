# 6. Checker semantics: components, undeclared components, exceptions, exit codes

Date: 2026-09-16 (M2)

## Status

Accepted.

## Context

`docs/05` sketches `archview.toml` and the checker output but leaves several
behaviours open. Each of them decides whether an agent can slip past the rules
without anyone noticing.

## Decision

- **Components.** By default a component is a direct child of the project package.
  The project's root module (`pkg/__init__.py`) is a component named after the
  project, but only when it imports or is imported. Otherwise every repo would get
  an empty entry for it. Explicit `[components]` patterns are dotted globs (`*` = one
  segment, `**` = any number, and a package pattern covers its subtree; see
  `model/patterns.py`). The most specific pattern wins, then the name (open decision
  5 in the requirements).
- **Undeclared components are problems.** Once an `[allowed]` table exists, a
  component that is missing from it fails the check (`kind: undeclared`). A new
  package is an architectural decision, so the agent that creates it has to ask. It
  cannot quietly pass just because nothing constrains it.
- **`forbidden` wins over `allowed`**, including over `"all"`.
- **Exceptions are exempt from everything**, cycles included. An exception says
  "this import is known and tolerated", so it would be odd for it to still fail as
  part of a cycle. An exception that matches no import is a warning, so dead
  exceptions get removed.
- **Switched-off checks still report.** With `fail_on_cycles = false` the cycles are
  still printed (marked "reported only") but do not change the exit code.
- **Exit codes.** 0 = pass, 1 = failing problems, 2 = the command could not run
  (unreadable or invalid rules, no package, bad arguments). A broken rules file must
  never look like a failed check, or like a passing one.
- **Cycles with more than two members** are written `tangle of 4: a, b, c, d`, not
  `a -> b -> c -> d -> a`. The members of a strongly connected component, sorted by
  name, are not an import path, and printing them as one would be false.
- **The cycle hint names the thinnest edge** (fewest imports, then name). This is
  the cheap cycle-breaker advice that ADR 0003 deferred. It is a hint, not a proof
  that removing that edge makes the graph acyclic.
- **`init`** writes the dependencies that exist today. If there are cycles, it sets
  `fail_on_cycles = false` and lists them in a comment, so a fresh `init` always
  passes (MVP acceptance). `--force` regenerates and keeps `package`,
  `source_roots`, `exclude`, `ignored` and `components`.
- **`[tool.archview]` in `pyproject.toml`** is read when there is no
  `archview.toml`; rule names in the output use whichever table was read.

## Consequences

Agents get a hard stop on new components and on reversed dependencies, and a clear
difference between "your code is wrong" (1) and "the tool could not run" (2). There
is no CI yet, so `tests/test_self_check.py` runs the checker on this repo inside
pytest.
