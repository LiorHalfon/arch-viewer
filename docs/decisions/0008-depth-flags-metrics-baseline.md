# 8. Depth: import flags, abstractness, metrics, rule sugar, baseline, overlay

Date: 2026-09-16 (M4)

## Status

Accepted. Implements what ADR 0002 deferred.

## Context

M4 covers requirements A4–A5, A9–A10, C7–C9 and V7–V12. Most of them leave
definitions open, such as what counts as "abstract", whose fan-in counts, and what
a baseline records. The choices below are the ones the code relies on.

## Decision

### Model (schema 2)

- **One `ast` pass per file** (`extract/facts.py`) sets `type_checking` (inside
  `if TYPE_CHECKING:` / `if typing.TYPE_CHECKING:`, not the `else`) and `lazy`
  (inside a function or lambda; class bodies run at import, so they are not lazy)
  on each import, matched by the statement's first line.
- **Abstract module**: defines at least one class that subclasses `Protocol` or `ABC`
  (including `typing.Protocol[T]`), uses `metaclass=ABCMeta`, or has an
  `@abstractmethod`. A package is drawn abstract only if *all* its modules are;
  its abstractness `A` is the ratio.
- **Dynamic imports** (`importlib.import_module`, `import_module`, `__import__`) are
  model `warnings`, with the target when it is a string literal. Stdlib targets are
  dropped.
- **Third-party packages** become `kind: "external"` nodes (squashed by grimp,
  `parent: null`, no file). Stdlib is dropped (`sys.stdlib_module_names`). Nothing
  under a project root ever owns them, so views, components and the checker
  ignore them unless a view asks for `externals`.

### Metrics

- `Ca`/`Ce` count **distinct modules** on the other side of the node's boundary,
  not import statements (`fan_in`/`fan_out` stay import counts). In a view the
  boundary is the siblings under the root; in `check`/`metrics` it is the
  component. Imports of third-party packages do not count towards `Ce`.
- A node with no dependencies at all has `I` undefined and zone `isolated`,
  not "pain".
- The viewer colours zones on packages only: almost every leaf module is "concrete
  and depended upon", and colouring all of them would bury the signal.

### Rules

- `type_checking_imports = "ignore"` (default) drops TYPE_CHECKING imports before
  anything is checked, `init` included. The viewer still draws them, dotted,
  and edge counts include them.
- `layers = [top, [peer, peer], bottom]` forbids importing any layer above, and
  peers in the same list may not import each other. `independent = [[a, b, c]]`
  forbids imports between the members. Both expand into `forbidden` pairs
  (`Config.all_forbidden`), and the problem's `rule` names where they came from.
- `[metrics] fail_on_zones = ["pain"]` (with `threshold` and `ignore`) turns
  component zones into problems. Without it, metrics are reported, never failing.
- **Baseline** (`archview-baseline.json` next to the rules, or `baseline = "path"`):
  fingerprints per import for rule problems (`kind, components, importer, imported`),
  per component set for cycles, zones and undeclared components. New imports behind
  a known violation fail. A cycle stays known while its members are a subset of a
  recorded cycle, so it fails again once it grows. Entries that no longer occur
  produce a warning that asks for `--update-baseline`. Line numbers are left out
  so moving code does not break the baseline.

### Viewer

- **Violations overlay**: the server marks each import behind a failing rule
  problem. An edge is a violation if any import behind it is one, at any depth,
  so drilling into a component still shows which sub-package breaks the rule.
- **Legend**: green = abstract; hollow triangle = edge to an abstraction
  (every import lands on an abstract module); dotted = type checking only;
  red = cycle; orange dashed = breaks a rule; dashed box = third-party.
- **Focus**: shift/right-click a box for its metrics, neighbours, "what it reaches"
  and "what reaches it" (transitive, within the current view).
- **Export**: SVG/PNG are rendered in the browser from the view's DOT, so they use
  the DOT's own light colours. Mermaid and DOT come from `/api/export` and
  `archview graph --mermaid|--dot`.
- **Watch**: `serve --watch` polls file mtimes once a second (no new dependency),
  and the page polls `/api/project` for a new `generation`. The last good analysis
  is kept if reanalysis fails.

## Consequences

- The model JSON is schema 2. Readers of schema 1 must update.
- **Not done in M4:** collapsing or expanding packages in place (part of V10).
  Graphviz redraws the whole layout, so this waits for the ELK/React Flow step
  (ADR 0007). GitHub Actions annotations (C5, V2) are not built either.
