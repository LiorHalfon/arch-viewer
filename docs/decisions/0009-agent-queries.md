# 9. Agent queries: `why`, `deps`, `rdeps`, `cycles`, and the Stop hook

Date: 2026-09-16 (M5)

## Status

Accepted. Changes the `why` line in `docs/05` §2 ("grimp `find_shortest_chains`").

## Context

After M4 the only part of M5 left is requirement G1: the query commands an agent
uses to look at the structure before it fixes a dependency. `check --format json`,
the baseline, the CLAUDE.md paragraph and the hook already exist. `docs/05` leaves
open what the queries answer at package level, what they print and how they exit.
The hook in `docs/06` also turned out to be able to trap an agent: it blocks on
every non-zero exit and ignores `stop_hook_active`.

## Decision

### The queries work on the model, not on grimp

The code is in `model/query.py` and works on `Model.imports`, not on grimp's
graph. The reasons: `model` has to stay language-agnostic (N8; TypeScript comes in
M6), and grimp's graph has not been through `exclude`, `--hide-tests` or
`--runtime-only`. A chain through excluded code would contradict `check` and the
viewer.

### Names

A name is a full dotted name (`archview.rules.check`), a name relative to the
project package (`rules.check`), or an external package (`networkx`). An unknown
name is a usage error (exit 2) with close matches suggested. A package stands for
its whole subtree.

### `why A B`

1. **Direct imports** from A's subtree into B's subtree, with `file:line`. This is
   what an agent needs to fix a violation.
2. Only if there are none: **the shortest chain** of imports from a module in A to
   a module in B. No intermediate module may be in A or B (as in grimp), otherwise
   chains would be trivially short and say nothing. Neighbours are visited in name
   order, and the first import behind a module pair is the one with the lowest
   `file:line`, so the answer is deterministic (N1).

It is a usage error when A and B overlap (one contains the other).

### `deps M` / `rdeps M`

The direct dependencies (or dependents) of M's subtree, not counting imports inside
it. Each other end is shortened to M's depth, so a module lists modules and a
top-level package lists sibling packages. The concrete imports are listed under
each entry. Third-party packages appear in `deps` only with `--externals`, as in
`graph`. Externals keep their own name, and `rdeps` of an external lists the
importing modules, since shortening to depth 1 would only give the project. There
is no `--transitive` yet: the viewer's "what it reaches" still lives in the UI. If an agent needs transitive
answers, that logic moves into `model/` first.

### `cycles`

Every level, not just one view. For each package with a cycle among its children
(the same levels as `tangled_packages`), the command prints one **real cycle path**:
the shortest cycle through the member with the smallest name, with the imports
behind each step. With more than two members, the members the path misses are
listed too, with the other edges among the members (`others`) and their imports.
Pointing to `why` for those would be wrong: a tangle is computed from edges between
packages, so two members can be in one tangle without any module-level chain of
imports between them. `describe_cycle` stays as it is for `check` and `init`. `--root`
limits the command to one subtree.

### Output, flags and exit codes

- `--format text|json` on every query, like `check` and `metrics`. `graph` gets
  `--format text|json|dot|mermaid` as well, and keeps `--json`, `--dot` and
  `--mermaid` as aliases.
- `--hide-tests` and `--runtime-only` (leave out TYPE_CHECKING imports) on every
  query. In the text output, TYPE_CHECKING and lazy imports are marked.
- Imports are listed in `file:line` order.
- `why` exits 0 when it finds a dependency and 1 when there is none. `deps`,
  `rdeps` and `cycles` exit 0 (an empty answer is still an answer). Every command
  exits 2 when it cannot run.

### The Stop hook: `archview check --stop-hook`

Claude Code's Stop hook blocks the stop when the command exits 2 and gives the
agent its stderr. `--stop-hook` turns `check` into a well-behaved hook:

- when stdin says `stop_hook_active` is true (the agent was already sent back once),
  it exits 0 without checking, so an agent that cannot fix a problem (for example
  one that needs a rule change only a human may make) is not trapped;
- when the check fails, it writes the text report to stderr and exits 2;
- when the check cannot run (no rules, a broken rules file), it warns on stderr and
  exits 0, because a broken setup should not block every stop.

The documented command guards against a missing install:
`command -v archview >/dev/null || exit 0; archview check --stop-hook`.

### Not in M5

- Turning on grimp's cache. A cold `graph` on `tiny-tale-backend` (707 files) takes
  0.25s, so ADR 0005's trigger has not fired.
- Keeping deleted `allowed` entries when `archview init --force` regenerates the
  rules. That is a separate change.

## Consequences

Agents get ground truth for "why does X depend on Y", "who uses X" and "what is in
this cycle" from the same filtered model that `check` and the viewer use. The
queries add no new component, so `archview.toml` does not change.
