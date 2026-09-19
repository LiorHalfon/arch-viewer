# M7 — Rules for imports that leave the package: design

Date: 2026-09-20. Status: approved in brainstorming, pending spec review.

GitHub issue #1. In a workspace where a core package has plugins, the boundaries that
matter most cross the package line: the core never imports a vendor SDK, a plugin never
imports another plugin, the server reaches the plugins from one module only. None of
these can be written as rules today, because `archview check` drops every import whose
target is outside the checked package.

This milestone makes a rule able to name a package outside the project. It is also the
foundation for workspace mode (issue #2, M8): once cross-package imports are visible as
outside edges, workspace mode only has to attribute them to sibling packages.

## 1. What already works

The data is present end to end; only the rules layer discards it.

- `model/graph.py:12` — `Kind = Literal["package", "module", "external"]`. Externals are
  first-class nodes, one squashed node per top-level third-party package,
  `parent=None`, `file=None`.
- Imports to externals carry `file`, `line` and `text` like any other `Import`.
- `model/query.py` — `resolve()` accepts external names; `rdeps <external>` and
  `deps X --externals` already work. `archview why archview grimp` already prints the
  edge, so issue #1's second acceptance criterion is met before this milestone starts.
- `render/dot.py:31`, `render/mermaid.py:25` already style external nodes.

Two places drop the edges:

- `rules/components.py:42-47` — `ComponentMap._default()` returns `None` for any module
  not under the project.
- `rules/check.py:76` — `component_edges()` skips a pair when either side is `None`.

## 2. Vocabulary

An **outside name** is a node the model already carries with `kind == "external"`: a
PyPI or npm package, or a sibling workspace package, which from one package's model
looks exactly like third-party code. Rules may name an outside name wherever they name
a component.

archview deliberately does **not** distinguish a first-party sibling from a third-party
dependency. It cannot do so from one package's model alone. That distinction arrives
with workspace mode, which supplies the list of sibling packages.

## 3. Semantics

### `ComponentMap` stays internal

`ComponentMap.of()` keeps returning `None` for outside modules. Existing rules must not
change meaning: if `of()` started returning `"openai"`, then the edge
`("llm", "openai")` would be checked against `[archview.allowed].llm` and every repo
with a third-party dependency would fail. A separate accessor is added:

```python
def outside(self, module: str) -> str | None:
    """The outside name a module belongs to, or None if it is inside the project."""
```

It returns the module's own id when the model marks it external, honouring `ignored`
the same way `of()` does.

### One classifying pass

`component_edges()` becomes a single pass that returns a record rather than a tuple of
two:

```python
@dataclass(frozen=True, slots=True)
class Edges:
    internal: dict[Pair, list[Import]]    # (component, component), as today
    outside: dict[Pair, list[Import]]     # (component, outside name)
    exceptions_used: set[int]
```

One pass means `[[archview.exceptions]]` is applied to both kinds with no duplicated
bookkeeping, so module-level exemptions start working on external edges for free.
`rules/init.py` is the other caller and is updated for the new return type.

### The project name means the root module, not the project

Issue #1 writes `from = "bespoke_story"` intending "the whole project". Today the
project name is already a component: the root module `pkg/__init__.py` (ADR 0006). A
rule spelled that way would silently narrow to one file.

**`from = "*"` means every component.** The bare project name keeps meaning the root
module. This is the one place the issue's sketch is not adopted verbatim.

### `undeclared` does not apply to outside names

A component missing from `[archview.allowed]` is a problem (ADR 0006), but an outside
name is not a component and must never trigger it. This holds without new code:
`present_components()` (`rules/check.py:95`) counts only nodes with a `file`, and
externals have none. A test pins the behaviour so a later refactor cannot lose it.

### A rule that can never fire

- A rule naming something absent from the model stays an `unknown_component` **warning**,
  as today. It flags a dead rule without failing the build.
- A rule naming a **stdlib** module is a parse-time `ConfigError`. The Python extractor
  filters stdlib out entirely (`extract/python.py:20`), so such a rule could never fire,
  and a silent no-op in a rules file is worse than an error. The message says stdlib
  imports are not analysed. Checked against `sys.stdlib_module_names` for Python only;
  TypeScript builtins are not checked, since `node:`-prefixed and bare builtin
  specifiers are already dropped by the extractor as `drop` targets.

### Unchanged

Metrics (externals are already excluded from Ce by `view.internal_out`), cycles
(externals have no outgoing edges, so they cannot be in one), `why`, `deps`, `rdeps`.

## 4. Configuration

Two additions to `TOP_KEYS` in `rules/config.py`.

### `forbidden` and `exceptions` widen

The existing tables gain the ability to name an outside name on either side. No new
syntax.

```toml
[[archview.forbidden]]
from = "*"                  # every component
to   = "openai"

[[archview.forbidden]]
from = "bespoke_server"
to   = "bespoke_openai"

[[archview.exceptions]]
importer = "bespoke_server.wiring"
imported = "bespoke_openai"
reason   = "the composition root builds the plugins from the settings"
```

Resolution order for a name in `from`/`to`: a known component wins; otherwise an outside
name present in the model; otherwise the `unknown_component` warning. Components and
outside names cannot collide in practice, because a component is always a child of the
project package and an outside name never is.

`from` always names a component (or `"*"`); an outside name there is a `ConfigError`,
since nothing archview can see imports *out of* a third-party package. `to = "*"` is
not supported: "this component may reach nothing outside the project" is
`[archview.externals].<component> = []`, which reports a better problem.

### `[archview.externals]` — new, opt-in

```toml
[archview.externals]
ports     = []              # may reach nothing outside the project
interview = ["pydantic"]
tools     = "all"           # explicit escape hatch
```

Parsed by `_externals`, mirroring `_allowed` (list of names, or the `"all"` sentinel);
keyed by component name.

**A component absent from the table is unconstrained.** There is no `undeclared`
analogue here. This breaks symmetry with `[archview.allowed]` on purpose: it makes the
table adoptable one component at a time, where the stricter reading would fail every
repo the moment the table appeared. The asymmetry is the point and is documented in the
ADR.

## 5. Output

New `ProblemKind = "outside"` for an `[archview.externals]` violation, rule name
`archview.externals.<component>`, label `OUTSIDE` in `render/check.py:14`. The hint
points at the two real remedies: declare the dependency, or route it through a port
owned by the component.

A `forbidden` rule with an outside target needs **no** new kind. It stays
`kind: "forbidden"` with the existing `from`/`to` JSON fields, so an agent already
parsing the report needs no change.

`_problem_dict` emits `from`/`to` for `outside` as it does for `not_allowed` and
`forbidden`.

## 6. Viewer

Issue #1's third acceptance criterion is that the viewer shows the forbidden edge.
Externals appear in a view today only when `--externals` is on, so a violation could be
missed by default.

`build_view()` gains `keep: frozenset[str]` — outside names forced into the view even
when `externals=False`. `cli._graph` and the server compute it from
`failing_imports(report)` before building the view, so an external node that is the
target of a failing rule is drawn, in red, like any other violation; every other
external still needs `--externals`.

Layering holds: `keep` is a frozenset of strings, so `model` gains no dependency on
`rules`.

## 7. Testing

- `tests/test_rules_externals.py` — new, over `tests/builders.py`: forbidden with an
  outside target, `from = "*"`, exceptions exempting an outside edge, the
  `[archview.externals]` allow-list including `"all"` and the empty list, an outside
  name never producing `undeclared`, the stdlib `ConfigError`, the `unknown_component`
  warning for a dead outside rule.
- `tests/builders.py` gains a way to mark a node external. Today it derives the whole
  tree from import pairs and everything is internal.
- The `sample` fixture already contains `import grimp`, so golden coverage comes free;
  `tests/golden/sample-check.json` is regenerated only if a rule is added to
  `tests/golden/sample-archview.toml`.
- `tests/test_cli_check.py` gains an end-to-end case with an outside violation, and a
  `--format json` case pinning the `outside` problem shape.
- `tests/test_golden.py` gains a view built with a non-empty `keep`.

**Constraint:** `tests/test_self_check.py` asserts `report.warnings == ()`. Any new
warning that fires on this repo breaks the suite.

**Dogfooding:** the repo's own `archview.toml` gains a live outside rule — `model` must
not reach `grimp` — so the feature is exercised by `test_self_check.py` against real
code, not only by fixtures. The rule is true today (`extract` imports grimp, `model`
does not) and encodes a real constraint: the language-agnostic model must not learn
about a Python-specific extractor library.

## 8. Out of scope

- **Stdlib rules.** Decided: rejected at parse time. A `stdlib = "include"` setting can
  follow if someone asks for "domain never imports `subprocess`".
- **Distinguishing first-party siblings from third-party.** Workspace mode (M8).
- **Inferring an externals table.** `archview init` writes no `[archview.externals]` by
  default; `archview init --externals` emits one from today's imports, for people who
  want the freeze-then-delete loop that `[archview.allowed]` already offers.

## 9. Done when

- A rule can name a package outside the project, and the check reports a breaking import
  with its file and line, like any other problem.
- `archview why <component> <outside name>` explains the edge. *(Already true; covered
  by a regression test.)*
- The viewer shows a forbidden outside edge without `--externals`.
- `archview check` passes on this repo with a live outside rule in its own
  `archview.toml`.
