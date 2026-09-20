# M7 + M8 — Outside rules and workspace mode: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a dependency rule name a package outside the project (GitHub issue #1), then build workspace mode on top of it so several packages are checked and drawn as one architecture (issue #2).

**Architecture:** The model already carries external nodes with file and line on every import; only the rules layer discards them, in two places. M7 (Tasks 1–8) stops discarding them and adds an opt-in `[archview.externals]` allow-list. M8 (Tasks 9–16) adds a federation: a `Workspace` of N `Project`s, where a cross-package edge is an M7 outside edge whose target belongs to a sibling's aliases. No model merging, so Python's `.` ids and TypeScript's `/` ids never collide.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `ruff`, grimp, networkx, TypeScript compiler API via Node.

**Specs:**
- `docs/superpowers/specs/2026-09-20-outside-rules-design.md` (M7, Tasks 1–8)
- `docs/superpowers/specs/2026-09-20-workspace-design.md` (M8, Tasks 9–16)

## Global Constraints

- Python 3.12+; type hints in modern style (`str | None`); `from __future__ import annotations` at the top of every module, as every existing module has.
- Run `uv run pytest && uv run ruff check && uv run ruff format --check .` before every commit. All three must pass.
- **Deterministic output (N1).** Sort by name wherever there is a tie. Same source → byte-identical JSON.
- **`tests/test_self_check.py` asserts `report.warnings == ()`** on this repo. Any new warning kind that fires here breaks the suite.
- **Backwards compatibility is non-negotiable.** A repo with no `[archview.externals]` and no `[archview.workspace]` must produce byte-identical output to today. Several tasks add a regression test for this.
- Never edit `archview.toml` to make a check pass — except Task 8, which deliberately adds a rule that is already true.
- Small functions; the repo targets cyclomatic complexity ≤ 5 where practical.
- Commit messages: imperative mood, no `feat:`/`fix:` prefixes (match the existing log, e.g. "Fix the seven findings from the M6 whole-branch review"). End every commit message with:

```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW
```

- Golden files: regenerate with `UPDATE_GOLDEN=1 uv run pytest`, then **read the diff** before committing. An unexplained golden change is a bug.

## File Structure

**M7 — modified:**

| File | Responsibility after this plan |
|---|---|
| `src/archview/rules/components.py` | `ComponentMap` gains `outside()`; `of()` unchanged |
| `src/archview/rules/check.py` | `Edges` record; `component_edges()` classifies; `_outside_problems()`; `"outside"` kind |
| `src/archview/rules/config.py` | `externals` in `TOP_KEYS`; `_externals` parser; stdlib rejection |
| `src/archview/rules/init.py` | updated for the `Edges` return type; `--externals` inference |
| `src/archview/render/check.py` | `OUTSIDE` label; `from`/`to` in `_problem_dict` for `outside` |
| `src/archview/model/view.py` | `build_view(..., keep=frozenset())` |
| `src/archview/cli.py` | `init --externals`; computes `keep` for `graph` |
| `archview.toml` | a live dogfood rule |

**M7 — created:** `tests/test_rules_externals.py`.

**M8 — created:**

| File | Responsibility |
|---|---|
| `src/archview/workspace.py` | `Package`, `Workspace`, `open_workspace`, `_owner`, `cross_edges`, `check_workspace`, `workspace_view` |
| `src/archview/render/workspace.py` | text and JSON for a workspace report |
| `tests/fixtures/workspace/` | `core/` + `plugin/` Python packages and a root rules file |
| `tests/test_workspace.py`, `tests/test_cli_workspace.py` | |

**M8 — modified:** `src/archview/rules/config.py` (workspace table), `src/archview/cli.py`, `src/archview/server/workspace.py` → renamed `src/archview/server/state.py`, `src/archview/server/app.py`, `src/archview/ui/`, `archview.toml` (the new `workspace` component).

---

## Task 1: `ComponentMap.outside()`

**Files:**
- Modify: `src/archview/rules/components.py:25-47`
- Test: `tests/test_rules_externals.py` (create)

**Interfaces:**
- Consumes: `ComponentMap(project, sep, explicit, ignored)` as it exists today.
- Produces: `ComponentMap.outside(module: str) -> str | None` — the module's own id when it is outside the project, else `None`; `None` for anything in `ignored`.

Note `outside()` cannot consult the model (`ComponentMap` has no access to it), so "outside the project" means "not under the project package", which is exactly what `_default()` already computes. Task 2 intersects the result with the model's external nodes.

- [ ] **Step 1: Write the failing test**

```python
"""Rules that name a package outside the project (issue #1)."""

from __future__ import annotations

from archview.rules.components import ComponentMap


def test_outside_names_a_module_that_is_not_under_the_project():
    components = ComponentMap("shop", ".", {})
    assert components.outside("openai") == "openai"
    assert components.outside("openai.types") == "openai"


def test_outside_is_none_inside_the_project():
    components = ComponentMap("shop", ".", {})
    assert components.outside("shop.api") is None
    assert components.outside("shop") is None


def test_outside_respects_ignored():
    components = ComponentMap("shop", ".", {}, frozenset({"openai"}))
    assert components.outside("openai") is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_rules_externals.py -v`
Expected: FAIL, `AttributeError: 'ComponentMap' object has no attribute 'outside'`

- [ ] **Step 3: Implement**

In `src/archview/rules/components.py`, after `of()`:

```python
    def outside(self, module: str) -> str | None:
        """The outside package `module` belongs to, or None if it is inside the project.

        Squashed to the top-level name, as the extractors squash external nodes.
        """
        if module == self.project or within(module, self.project, self.sep):
            return None
        name = module.split(self.sep)[0]
        return None if name in self.ignored else name
```

Update the module docstring's first paragraph to mention that a module outside the project belongs to no component but has an outside name.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_rules_externals.py -v && uv run ruff check && uv run ruff format --check .`
Expected: 3 passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/archview/rules/components.py tests/test_rules_externals.py
git commit -m "Add ComponentMap.outside for modules beyond the project

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 2: `Edges` — classify internal and outside edges in one pass

**Files:**
- Modify: `src/archview/rules/check.py:63-84` (`component_edges`), `:114-137` (`check`), `:138-160` (`component_metrics`), `:158` (`_unused`), `:200` (`_rule_problems`), `:284` (`_cycle_problems`)
- Modify: `src/archview/rules/init.py` (the other caller)
- Test: `tests/test_rules_externals.py`

**Interfaces:**
- Consumes: `ComponentMap.outside()` from Task 1.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class Edges:
    internal: dict[Pair, list[Import]]   # (component, component)
    outside: dict[Pair, list[Import]]    # (component, outside name)
    exceptions_used: set[int]

def component_edges(model: Model, components: ComponentMap, config: Config | None = None) -> Edges
```

This is a **pure refactor plus one new field**. `Edges.internal` must equal today's first return value exactly, so every existing test keeps passing unchanged. Only imports whose target is an `external` node in the model land in `Edges.outside` — a module that is merely unresolvable is not an outside dependency.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rules_externals.py`:

```python
from archview.model.graph import Import, Model, Node
from archview.rules.check import component_edges
from archview.rules.config import Config, Exemption


def model_with_external() -> Model:
    """shop.llm imports openai; shop.api imports shop.llm."""
    nodes = (
        Node("shop", None, "package"),
        Node("shop.api", "shop", "module", "shop/api.py"),
        Node("shop.llm", "shop", "module", "shop/llm.py"),
        Node("openai", None, "external"),
    )
    imports = (
        Import("shop.api", "shop.llm", "shop/api.py", 1, "import shop.llm"),
        Import("shop.llm", "openai", "shop/llm.py", 2, "import openai"),
    )
    return Model(project="shop", nodes=nodes, imports=imports)


def test_outside_edges_are_kept_apart_from_internal_ones():
    m = model_with_external()
    edges = component_edges(m, ComponentMap("shop", ".", {}), Config())
    assert list(edges.internal) == [("api", "llm")]
    assert list(edges.outside) == [("llm", "openai")]
    assert edges.outside[("llm", "openai")][0].line == 2


def test_an_exception_exempts_an_outside_edge():
    m = model_with_external()
    config = Config(exceptions=(Exemption("shop.llm", "openai", "the one adapter"),))
    edges = component_edges(m, ComponentMap("shop", ".", {}), config)
    assert edges.outside == {}
    assert edges.exceptions_used == {0}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_rules_externals.py -v`
Expected: FAIL, `AttributeError: 'tuple' object has no attribute 'internal'`

- [ ] **Step 3: Implement**

In `src/archview/rules/check.py`, replace `component_edges` with:

```python
@dataclass(frozen=True, slots=True)
class Edges:
    """Imports grouped by the pair they connect, split by whether the target is inside."""

    internal: dict[Pair, list[Import]]
    outside: dict[Pair, list[Import]]
    exceptions_used: set[int]


def component_edges(
    model: Model, components: ComponentMap, config: Config | None = None
) -> Edges:
    """Imports grouped by the components they connect, minus exempted ones.

    `outside` holds the imports whose target is an external node; `exceptions_used`
    holds the indexes of the exceptions that exempted something, so unused ones
    can be reported.
    """
    exemptions = config.exceptions if config else ()
    external = {n.id for n in model.nodes if n.kind == "external"}
    internal: dict[Pair, list[Import]] = defaultdict(list)
    outside: dict[Pair, list[Import]] = defaultdict(list)
    used: set[int] = set()
    for imp in model.imports:
        pair = _pair(imp, components, external)
        if pair is None:
            continue
        hit = _exemption(imp, exemptions, model.separator)
        if hit is not None:
            used.add(hit)
            continue
        bucket = outside if imp.imported in external else internal
        bucket[pair].append(imp)
    return Edges(dict(sorted(internal.items())), dict(sorted(outside.items())), used)


def _pair(imp: Import, components: ComponentMap, external: set[str]) -> Pair | None:
    """(source component, target) for an import the rules care about, else None."""
    source = components.of(imp.importer)
    if source is None:
        return None
    if imp.imported in external:
        target = components.outside(imp.imported)
        return None if target is None else (source, target)
    target = components.of(imp.imported)
    return None if target is None or target == source else (source, target)
```

Add `Edges` to the module's imports of `dataclass` if not already present (`check.py` imports `dataclass` already).

Then update every caller inside `check.py` to use `edges.internal`:

- In `check()`: `edges = component_edges(model, components, config)` stays; pass `edges.internal` to `component_metrics`, `_cycle_problems` and `_unused`; pass the whole `edges` to `_rule_problems`; pass `edges.exceptions_used` to `_warnings` in place of `used`.
- In `_rule_problems`, change the signature's first parameter to `edges: Edges` and use `edges.internal` in the two loops. Task 4 adds the outside handling.

In `src/archview/rules/init.py`, the call site becomes:

```python
    edges = component_edges(model, components, config)
```

and every later use of the old `edges` variable becomes `edges.internal`; the old `used` variable is dropped (init does not report unused exceptions).

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check .`
Expected: everything passes, including the ~60 existing checker tests, unchanged. If any existing test fails, the refactor changed behaviour — fix the refactor, not the test.

- [ ] **Step 5: Commit**

```bash
git add src/archview/rules/check.py src/archview/rules/init.py tests/test_rules_externals.py
git commit -m "Classify outside edges instead of dropping them

component_edges now returns an Edges record splitting internal from
outside edges in one pass, so module-level exceptions apply to both.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 3: `[archview.externals]` config parsing

**Files:**
- Modify: `src/archview/rules/config.py` — `Config` dataclass (`:51`), `TOP_KEYS` (`:100`), `parse_config` (`:152`), a new `_externals` parser next to `_allowed` (`:260`)
- Test: `tests/test_rules_config.py`

**Interfaces:**
- Produces: `Config.externals: dict[str, tuple[str, ...] | str] | None = None`, parsed by `_externals(value, where) -> dict[str, tuple[str, ...] | str] | None`. Same shape as `Config.allowed`: a list of names, or the `ALL` sentinel `"all"`. `None` means the table is absent.

Stdlib rejection lives here because it is a parse-time property of the name.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rules_config.py` (match the file's existing style of writing a toml into `tmp_path`):

```python
def test_externals_table_is_parsed(tmp_path):
    config = written(tmp_path, """
        [archview]
        package = "shop"
        [archview.externals]
        ports = []
        llm = ["openai"]
        tools = "all"
    """)
    assert config.externals == {"ports": (), "llm": ("openai",), "tools": "all"}


def test_no_externals_table_means_none(tmp_path):
    config = written(tmp_path, '[archview]\npackage = "shop"\n')
    assert config.externals is None


def test_a_stdlib_target_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="stdlib"):
        written(tmp_path, """
            [archview]
            package = "shop"
            [archview.externals]
            llm = ["subprocess"]
        """)


def test_a_stdlib_forbidden_target_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="stdlib"):
        written(tmp_path, """
            [archview]
            package = "shop"
            [[archview.forbidden]]
            from = "domain"
            to = "os"
        """)
```

Read the top of `tests/test_rules_config.py` first and reuse its existing helper for writing a config file; if it has none, write one named `written(tmp_path, text)` that does `textwrap.dedent`, writes `archview.toml` and returns `load_config(path)`.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_rules_config.py -v -k "externals or stdlib"`
Expected: FAIL — unknown key `externals`, then `AttributeError` on `config.externals`.

- [ ] **Step 3: Implement**

In `src/archview/rules/config.py`:

```python
import sys

STDLIB = sys.stdlib_module_names | {"__future__"}
```

Add `externals: dict[str, tuple[str, ...] | str] | None = None` to `Config`, directly after `allowed`. Add `"externals"` to `TOP_KEYS`. In `parse_config`, after the `allowed=` line:

```python
        externals=_externals(table.get("externals"), f"{where}.externals"),
```

and the parser, next to `_allowed`:

```python
def _externals(value: Any, where: str) -> dict[str, tuple[str, ...] | str] | None:
    """Like `allowed`, but the targets are packages outside the project."""
    table = _allowed(value, where)
    if table is not None:
        for component, targets in table.items():
            if targets != ALL:
                for name in targets:
                    _reject_stdlib(name, f"{where}.{component}")
    return table


def _reject_stdlib(name: str, where: str) -> None:
    if name.split(".")[0] in STDLIB:
        raise ConfigError(
            f"[{where}] names {name!r}, a stdlib module: stdlib imports are not "
            "analysed, so the rule could never fire"
        )
```

In `_forbidden`, reject a stdlib `to` the same way:

```python
def _forbidden(value: Any, where: str) -> tuple[Forbidden, ...]:
    items = _tables(value, where, {"from", "to"})
    for item in items:
        _reject_stdlib(item["to"], where)
    return tuple(Forbidden(i["from"], i["to"]) for i in items)
```

Note `_allowed`'s error message mentions components; `_externals` reuses it, so also give `_externals` its own message by catching nothing — instead, copy the two-line type guard from `_allowed` into `_externals` with the wording "component = [packages outside the project it may import]". Keep the rest delegating.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_rules_config.py -v && uv run pytest && uv run ruff check`
Expected: all pass. Confirm no existing test used a stdlib name in a `forbidden.to`.

- [ ] **Step 5: Commit**

```bash
git add src/archview/rules/config.py tests/test_rules_config.py
git commit -m "Parse [archview.externals] and reject stdlib targets

A rule naming a stdlib module could never fire, because the Python
extractor filters stdlib out; a silent no-op in a rules file is worse
than an error.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 4: The `outside` problem and forbidden outside edges

**Files:**
- Modify: `src/archview/rules/check.py` — `ProblemKind` (`:21`), `_rule_problems` (`:200`), a new `_outside` producer
- Test: `tests/test_rules_externals.py`

**Interfaces:**
- Consumes: `Edges` (Task 2), `Config.externals` (Task 3).
- Produces: `ProblemKind` gains `"outside"`. `Problem(kind="outside", rule=f"{table}.externals.{component}", components=(component, outside_name), ...)`.

Rules, restated from the spec so the implementer does not have to open it:

- `from = "*"` in a `forbidden` rule matches **every** component.
- A `forbidden` rule whose target is an outside name produces `kind="forbidden"`, **not** a new kind.
- `forbidden` wins over the `externals` allow-list, as it wins over `allowed`.
- A component absent from `[archview.externals]` is **unconstrained** — no `undeclared` analogue.
- An outside name must never produce an `undeclared` problem.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rules_externals.py`:

```python
from archview.rules.check import check


def kinds(report):
    return sorted((p.kind, p.components) for p in report.problems)


def test_an_externals_allow_list_fails_an_undeclared_outside_import():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"llm": ()})
    report = check(model_with_external(), config)
    assert ("outside", ("llm", "openai")) in kinds(report)


def test_a_declared_outside_import_passes():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"llm": ("openai",)})
    assert check(model_with_external(), config).problems == ()


def test_all_lets_a_component_reach_anything_outside():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"llm": "all"})
    assert check(model_with_external(), config).problems == ()


def test_a_component_absent_from_the_externals_table_is_unconstrained():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"api": ()})
    assert check(model_with_external(), config).problems == ()


def test_an_outside_name_never_becomes_an_undeclared_component():
    config = Config(allowed={"api": ["llm"], "llm": []})
    report = check(model_with_external(), config)
    assert "openai" not in report.components
    assert not [p for p in report.problems if p.kind == "undeclared"]


def test_forbidden_reaches_an_outside_package():
    config = Config(
        allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("llm", "openai"),)
    )
    report = check(model_with_external(), config)
    assert ("forbidden", ("llm", "openai")) in kinds(report)


def test_forbidden_from_a_star_matches_every_component():
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("*", "openai"),))
    report = check(model_with_external(), config)
    assert ("forbidden", ("llm", "openai")) in kinds(report)


def test_forbidden_beats_the_externals_allow_list():
    config = Config(
        allowed={"api": ["llm"], "llm": []},
        externals={"llm": ("openai",)},
        forbidden=(Forbidden("llm", "openai"),),
    )
    assert [p.kind for p in check(model_with_external(), config).problems] == ["forbidden"]
```

Import `Forbidden` from `archview.rules.config` at the top of the file.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_rules_externals.py -v`
Expected: the eight new tests fail; the Task 1–2 tests still pass.

- [ ] **Step 3: Implement**

In `check.py`, widen the kind:

```python
ProblemKind = Literal["not_allowed", "forbidden", "undeclared", "cycle", "zone", "outside"]
```

Rework `_rule_problems` to take `Edges` and handle both buckets. `"*"` expands against `present`:

```python
def _rule_problems(
    edges: Edges, present: tuple[str, ...], config: Config, table: str
) -> list[Problem]:
    forbidden = _forbidden_pairs(config, present)
    allowed = config.allowed
    fails = config.fail_on_violations
    problems: list[Problem] = []
    if allowed is not None:
        for component in present:
            if component not in allowed:
                outgoing = [
                    i for (s, _), imps in edges.internal.items() if s == component for i in imps
                ]
                problems.append(_undeclared(component, outgoing, table, fails))
    for (source, target), imports in edges.internal.items():
        if (source, target) in forbidden:
            origin = forbidden[(source, target)].origin
            problems.append(_forbidden(source, target, imports, f"{table}.{origin}", fails))
        elif allowed is not None and source in allowed and not _may(allowed, source, target):
            problems.append(_not_allowed(source, target, imports, allowed, table, fails))
    problems += _outside_problems(edges.outside, forbidden, config, table)
    return sorted(problems, key=lambda p: (p.components, p.kind))


def _forbidden_pairs(config: Config, present: tuple[str, ...]) -> dict[Pair, Forbidden]:
    """`forbidden` rules keyed by pair, with `from = "*"` expanded to every component."""
    pairs: dict[Pair, Forbidden] = {}
    for f in config.all_forbidden():
        sources = present if f.source == ALL_COMPONENTS else (f.source,)
        for source in sources:
            pairs.setdefault((source, f.target), f)
    return pairs


def _outside_problems(
    outside: dict[Pair, list[Import]], forbidden: dict[Pair, Forbidden], config: Config, table: str
) -> list[Problem]:
    externals = config.externals
    fails = config.fail_on_violations
    problems = []
    for (source, target), imports in outside.items():
        if (source, target) in forbidden:
            origin = forbidden[(source, target)].origin
            problems.append(_forbidden(source, target, imports, f"{table}.{origin}", fails))
        elif externals is not None and source in externals and not _may(externals, source, target):
            problems.append(_outside(source, target, imports, externals, table, fails))
    return problems


def _outside(
    source: str, target: str, imports: list[Import], externals: dict, table: str, fails: bool
) -> Problem:
    may = ", ".join(externals[source]) or "nothing outside the project"
    return Problem(
        kind="outside",
        rule=f"{table}.externals.{source}",
        components=(source, target),
        count=len(imports),
        imports=tuple(imports),
        hint=(
            f"{source} may reach {may}. Declare {target} in [{table}.externals].{source}, "
            f"or define the interface {source} needs inside {source} and let another "
            "component depend on the package."
        ),
        fails=fails,
    )
```

Add `ALL_COMPONENTS = "*"` to `rules/config.py` next to `ALL`, export it, and import it in `check.py`. Note `ALL` is the string `"all"` and `ALL_COMPONENTS` is `"*"` — they are different sentinels for different things; do not merge them.

In `check()`, pass `edges` (not `edges.internal`) to `_rule_problems`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check .`
Expected: all pass, existing checker tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/archview/rules/check.py src/archview/rules/config.py tests/test_rules_externals.py
git commit -m "Check outside edges against forbidden and [archview.externals]

An externals allow-list is opt-in per component: a component absent from
the table is unconstrained, so the table can be adopted one component at
a time. forbidden wins over it, as it wins over allowed.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 5: Warnings for dead outside rules; `from` must be a component

**Files:**
- Modify: `src/archview/rules/check.py:313-371` (`_warnings`), `src/archview/rules/config.py` (`_forbidden`)
- Test: `tests/test_rules_externals.py`

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: no new warning *kind* — reuses `unknown_component`, so `_dedupe` and the renderers need no change.

Two behaviours:
1. `_warnings` must know about outside names, or a `forbidden` rule naming `openai` would warn "which has no modules" even when it is live. The set of known names becomes `present` ∪ the model's external node ids ∪ `{"*"}`.
2. `_warnings` must check `config.externals` keys the way it checks `config.allowed` keys.
3. An outside name in `forbidden.from` is a `ConfigError` — nothing archview can see imports out of a third-party package. This cannot be decided at parse time (the model is not loaded yet), so it is checked in `_warnings`' place: `check()` raises before producing a report. Put it in `check()` directly, right after `present` is computed.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from archview.rules.config import ConfigError


def test_a_live_outside_rule_warns_about_nothing():
    config = Config(
        allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("llm", "openai"),)
    )
    report = check(model_with_external(), config)
    assert [w for w in report.warnings if w.kind == "unknown_component"] == []


def test_a_dead_outside_rule_warns():
    config = Config(
        allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("llm", "anthropic"),)
    )
    report = check(model_with_external(), config)
    assert any("anthropic" in w.message for w in report.warnings)


def test_an_externals_key_that_is_not_a_component_warns():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"nope": ()})
    report = check(model_with_external(), config)
    assert any("nope" in w.message for w in report.warnings)


def test_an_outside_name_on_the_from_side_is_an_error():
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("openai", "llm"),))
    with pytest.raises(ConfigError, match="openai"):
        check(model_with_external(), config)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_rules_externals.py -v -k "warn or from_side"`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `check.py`, give `_warnings` the external names. Its signature gains nothing — it already receives `model`, so compute inside:

```python
    external = {n.id for n in model.nodes if n.kind == "external"}
    known = set(present) | external | {ALL_COMPONENTS}
```

replacing wherever `known` is built today (read the existing line first; it is built from `present`). Then add, next to the `config.allowed` loop:

```python
    for component, targets in sorted((config.externals or {}).items()):
        if component not in present:
            warnings.append(
                Notice(
                    "unknown_component",
                    f"[{table}.externals.{component}] names {component!r}, which has no modules",
                )
            )
        for name in [] if targets == ALL else targets:
            if name not in external:
                warnings.append(
                    Notice(
                        "unknown_component",
                        f"[{table}.externals.{component}] names {name!r}, "
                        "which nothing imports",
                    )
                )
```

In `check()`, after `present = present_components(model, components)`:

```python
    _reject_outside_sources(model, components, config)
```

```python
def _reject_outside_sources(model: Model, components: ComponentMap, config: Config) -> None:
    """`from` always names a component: nothing we can see imports out of a package."""
    external = {n.id for n in model.nodes if n.kind == "external"}
    for f in config.all_forbidden():
        if f.source in external:
            raise ConfigError(
                f"[{config.table}.{f.origin}] has from = {f.source!r}, a package outside "
                "the project; `from` must name a component"
            )
```

Import `ConfigError` in `check.py` from `archview.rules.config`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check`
Expected: all pass, `tests/test_self_check.py` included — this repo's `archview.toml` has no outside rules yet, so its warning set is unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/archview/rules/check.py tests/test_rules_externals.py
git commit -m "Warn about dead outside rules; reject an outside name in from

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 6: Render the `outside` problem

**Files:**
- Modify: `src/archview/render/check.py:14` (`LABELS`), `:36` (`_problem_dict`)
- Test: `tests/test_cli_check.py`

**Interfaces:**
- Consumes: `Problem(kind="outside", components=(source, target))`.
- Produces: text label `OUTSIDE`; JSON with `from`/`to` alongside `components`.

- [ ] **Step 1: Write the failing test**

Read `tests/test_cli_check.py`'s `repo` fixture first and follow its shape. Add:

```python
def test_an_outside_violation_is_reported_with_file_and_line(repo, capsys):
    (repo / "archview.toml").write_text(
        '[archview]\npackage = "shop"\n'
        "[archview.allowed]\n" + ALLOWED + "\n"
        "[archview.externals]\nllm = []\n"
    )
    assert main(["check", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "OUTSIDE" in out
    assert "llm -> openai" in out
    assert ".py:" in out


def test_an_outside_violation_in_json(repo, capsys):
    ...  # same setup, then:
    assert main(["check", str(repo), "--format", "json"]) == 1
    data = json.loads(capsys.readouterr().out)
    problem = [p for p in data["problems"] if p["kind"] == "outside"][0]
    assert problem["from"] == "llm"
    assert problem["to"] == "openai"
    assert problem["rule"] == "archview.externals.llm"
    assert problem["imports"][0]["line"] > 0
```

The existing `repo` fixture may not import a third-party package. If it does not, extend the fixture to add a module that does (`import openai`), and check whether any existing assertion counts modules or components — update those in the same commit if so.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_cli_check.py -v -k outside`
Expected: FAIL — `KeyError: 'outside'` in `LABELS`, or a missing `from` key.

- [ ] **Step 3: Implement**

In `render/check.py`, add `"outside": "OUTSIDE"` to `LABELS`, and include `"outside"` wherever `_problem_dict` decides to emit `from`/`to` (today: `{"not_allowed", "forbidden"}` — make it a module-level constant `PAIRS = ("not_allowed", "forbidden", "outside")` and use it in both the dict and the text renderer's "A -> B" line).

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check`
Expected: all pass. If `tests/golden/sample-check.json` changed, read the diff — it should only change if you extended the fixture.

- [ ] **Step 5: Commit**

```bash
git add src/archview/render/check.py tests/ 
git commit -m "Render the outside problem in text and JSON

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 7: The viewer shows a violating outside edge without `--externals`

**Files:**
- Modify: `src/archview/model/view.py:90` (`build_view`), `src/archview/cli.py:91-121` (`_graph`)
- Test: `tests/test_view.py` (or wherever `build_view` is tested — find it), `tests/test_cli.py`

**Interfaces:**
- Produces: `build_view(model, root, externals=False, threshold=DEFAULT_THRESHOLD, keep=frozenset()) -> View`, where `keep` is a frozenset of outside names to include even when `externals` is False.
- `keep` is a plain frozenset of strings, so `model` gains no dependency on `rules` — the repo's own `archview.toml` forbids it.

- [ ] **Step 1: Write the failing test**

```python
def test_keep_pulls_a_named_external_into_a_view_without_externals():
    m = model_with_external()  # reuse the helper; import it or rebuild it here
    view = build_view(m, "shop", externals=False, keep=frozenset({"openai"}))
    assert "openai" in [n.id for n in view.nodes]
    assert ("shop.llm", "openai") in [(e.source, e.target) for e in view.edges]


def test_keep_does_not_pull_in_other_externals():
    m = model_with_external()
    view = build_view(m, "shop", externals=False, keep=frozenset({"anthropic"}))
    assert "openai" not in [n.id for n in view.nodes]
```

Note `build_view`'s children are nodes whose `parent == root`, so at root `"shop"` the children are `shop.api` and `shop.llm`; the external is added alongside. Verify the edge's endpoints against how `_grouped_imports` names them before asserting.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest -v -k keep`
Expected: FAIL, unexpected keyword argument `keep`.

- [ ] **Step 3: Implement**

In `model/view.py`:

```python
def build_view(
    model: Model,
    root: str,
    externals: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
    keep: frozenset[str] = frozenset(),
) -> View:
    """The children of `root` and the counted edges between them; with `externals`,
    the third-party packages the subtree imports become boxes too, and `keep` names
    outside packages to show even without `externals` (a rule broken by reaching one)."""
    by_id = {n.id: n for n in model.nodes}
    internal = frozenset(n.id for n in model.nodes if n.parent == root and n.kind != "external")
    found = _externals(model, root)
    shown = found if externals else (found & keep)
    children = internal | frozenset(shown)
```

and leave the rest of the function as it is.

In `cli.py`'s `_graph`, the report is already computed for the overlay. Pass its outside targets through:

```python
    failing = failing_imports(report)
    keep = frozenset(
        p.components[1] for p in report.problems if p.fails and p.kind in ("outside", "forbidden")
    )
    view = build_view(project.model, root, args.externals, keep=keep)
```

Only names that are actually external survive the `found & keep` intersection, so a `forbidden` problem between two internal components contributes nothing. Read `_graph` before editing — the report is fetched inside a `try` today because a repo may have no rules file; keep that behaviour, with `keep = frozenset()` when there is no report.

Apply the same in `src/archview/server/` wherever `build_view` is called for the viewer, so the browser shows it too.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run archview check`
Expected: all pass, and `archview check` on this repo still passes (the `model` component must not have gained a dependency).

- [ ] **Step 5: Commit**

```bash
git add src/archview/model/view.py src/archview/cli.py src/archview/server/ tests/
git commit -m "Show an outside package in the view when a rule breaks on it

A violation you have to switch a flag on to see is a violation you miss.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 8: `init --externals`, dogfood rule, docs and ADR — M7 closes

**Files:**
- Modify: `src/archview/rules/init.py`, `src/archview/cli.py` (the `init` subparser, `:238`), `archview.toml`, `docs/02-requirements.md`, `docs/05-approach-and-roadmap.md`, `docs/06-using-archview-in-a-repo.md:70-105`
- Create: `docs/decisions/0011-rules-for-outside-imports.md`
- Test: `tests/test_rules_check.py` (init output), `tests/test_self_check.py` (unchanged, must pass)

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: `infer_rules(model, config, externals: bool = False) -> str`.

- [ ] **Step 1: Write the failing test**

```python
def test_init_writes_no_externals_table_by_default():
    assert "[archview.externals]" not in infer_rules(model_with_external(), Config())


def test_init_externals_writes_the_table_from_todays_imports():
    text = infer_rules(model_with_external(), Config(), externals=True)
    assert "[archview.externals]" in text
    assert 'llm = ["openai"]' in text
    assert "api = []" in text
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_rules_check.py -v -k externals`
Expected: FAIL, unexpected keyword argument.

- [ ] **Step 3: Implement**

Add the `externals` parameter to `infer_rules`; when true, emit a `[archview.externals]` table from `edges.outside`, one line per present component (empty list when it reaches nothing outside), sorted by name, in the same style as the `[archview.allowed]` table it already writes. Add `--externals` to the `init` subparser in `cli.py` and pass it through.

Then the dogfood rule. Append to this repo's `archview.toml`:

```toml
[[archview.forbidden]]
from = "model"
to = "grimp"
```

Run `uv run archview check` — it must pass and emit no warnings (`extract` imports grimp, `model` does not, so the rule is live and unbroken). If it warns, stop and work out why before continuing; `tests/test_self_check.py` asserts zero warnings.

Write `docs/decisions/0011-rules-for-outside-imports.md` in the style of `0006-checker-semantics.md` (Date / Status / Context / Decision / Consequences). The decisions to record, with the reasoning from the spec:
- an outside name; no first-party/third-party distinction until workspace mode
- `from = "*"` for every component, and why the bare project name could not mean it
- the `[archview.externals]` asymmetry: no `undeclared` analogue, and why
- stdlib rejected at parse time rather than silently never firing
- a violating outside edge is drawn without `--externals`
- `forbidden` keeps its kind; only the allow-list gets the new `outside` kind

Update `docs/06-using-archview-in-a-repo.md`'s schema section with the two new shapes, `docs/02-requirements.md` with a C12 row for outside rules and an M7 row in the status table, and `docs/05-approach-and-roadmap.md`'s milestone table with M7.

- [ ] **Step 4: Verify everything**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`
Expected: all pass. Then sanity-check the feature by hand:

```bash
uv run archview check --format json | python -c "import json,sys; print(json.load(sys.stdin)['ok'])"
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "M7: init --externals, a dogfood rule, ADR 0011 and docs

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 9: The workspace fixture and `[archview.workspace]` config

**Files:**
- Create: `tests/fixtures/workspace/` — `archview.toml`, `core/archview.toml`, `core/src/core/{__init__,model,ports}.py`, `plugin/src/plugin/{__init__,adapter}.py`
- Modify: `src/archview/rules/config.py` — `WorkspaceRules` dataclass, `Config.workspace`, `TOP_KEYS`, `parse_config`
- Test: `tests/test_rules_config.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True, slots=True)
class WorkspaceRules:
    packages: tuple[str, ...] = ()
    fail_on_violations: bool = True
    fail_on_cycles: bool = True
    allowed: dict[str, tuple[str, ...] | str] | None = None
    forbidden: tuple[Forbidden, ...] = ()
    exceptions: tuple[Exemption, ...] = ()
    baseline: str | None = None

# Config gains:  workspace: WorkspaceRules | None = None
```

`None` means no workspace table, which must keep every existing code path identical.

The fixture, deliberately small and Python-only so it needs no Node:

- `core/src/core/model.py` — no imports
- `core/src/core/ports.py` — `from core.model import Thing`
- `plugin/src/plugin/adapter.py` — `from core.ports import Port` **and** `import openai` (so it exercises M7 too)
- `core/archview.toml` — `package = "core"`, `source_roots = ["src"]`, an `[archview.allowed]` table that passes
- `plugin/` has **no** rules file, to exercise "a package without its own rules file"
- root `archview.toml`:

```toml
[archview.workspace]
packages = ["core", "plugin"]

[archview.workspace.allowed]
core = []
plugin = ["core"]
```

- [ ] **Step 1: Write the failing test**

```python
def test_workspace_table_is_parsed(tmp_path):
    config = written(tmp_path, """
        [archview.workspace]
        packages = ["core", "plugin"]
        [archview.workspace.allowed]
        core = []
        plugin = ["core"]
    """)
    assert config.workspace.packages == ("core", "plugin")
    assert config.workspace.allowed == {"core": (), "plugin": ("core",)}
    assert config.workspace.fail_on_cycles is True


def test_no_workspace_table_means_none(tmp_path):
    assert written(tmp_path, '[archview]\npackage = "shop"\n').workspace is None


def test_an_unknown_workspace_key_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="packagess"):
        written(tmp_path, '[archview.workspace]\npackagess = []\n')
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_rules_config.py -v -k workspace`
Expected: FAIL — unknown key `workspace`.

- [ ] **Step 3: Implement**

Add `WorkspaceRules` to `config.py`, `"workspace"` to `TOP_KEYS`, `workspace=_workspace(table.get("workspace"), f"{where}.workspace")` to `parse_config`, and:

```python
WORKSPACE_KEYS = {
    "packages", "fail_on_violations", "fail_on_cycles",
    "allowed", "forbidden", "exceptions", "baseline",
}


def _workspace(value: Any, where: str) -> WorkspaceRules | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError(f"[{where}] must be a table")
    _known_keys(value, WORKSPACE_KEYS, where)
    return WorkspaceRules(
        packages=_str_list(value, "packages", where),
        fail_on_violations=_bool(value, "fail_on_violations", where),
        fail_on_cycles=_bool(value, "fail_on_cycles", where),
        allowed=_allowed(value.get("allowed"), f"{where}.allowed"),
        forbidden=_forbidden(value.get("forbidden", []), f"{where}.forbidden"),
        exceptions=_exceptions(value.get("exceptions", []), f"{where}.exceptions"),
        baseline=_optional_str(value, "baseline", where),
    )
```

Check `_bool`'s signature before using it — it reads a key out of a table with a default; confirm the default for `fail_on_*` is `True`.

Then create the fixture files listed above.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check`
Expected: all pass. The new fixture is inert so far — confirm no test discovers `tests/fixtures/workspace/` as a test module (`__init__.py` files inside `src/` are fine).

- [ ] **Step 5: Commit**

```bash
git add src/archview/rules/config.py tests/
git commit -m "Parse [archview.workspace] and add a two-package fixture

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 10: `open_workspace` and the alias join

**Files:**
- Create: `src/archview/workspace.py`
- Modify: `archview.toml` (the new `workspace` component and what it may import)
- Test: `tests/test_workspace.py` (create)

**Interfaces:**
- Consumes: `open_project`, `Project` (`archview.project`); `Config`, `WorkspaceRules` (`archview.rules.config`).
- Produces:

```python
@dataclass(frozen=True, slots=True)
class Package:
    name: str
    path: Path                     # absolute
    aliases: frozenset[str]
    project: Project
    has_rules: bool

@dataclass(frozen=True, slots=True)
class Workspace:
    name: str
    root: Path
    packages: tuple[Package, ...]
    config: Config

def open_workspace(root: Path, config_path: Path | None = None) -> Workspace
def _owner(outside: str, importer: Package, packages: tuple[Package, ...]) -> str | None
```

`archview.toml` must gain, in `[archview.allowed]`:

```toml
workspace = ["extract", "model", "project", "rules"]
```

and `cli` and `server` gain `"workspace"` in their lists. Do this in the same commit, or `archview check` fails.

- [ ] **Step 1: Write the failing test**

```python
"""Workspace mode: several packages checked and drawn as one architecture (issue #2)."""

from __future__ import annotations

from pathlib import Path

from archview.workspace import open_workspace

FIXTURE = Path(__file__).parent / "fixtures" / "workspace"


def test_open_workspace_finds_every_listed_package():
    ws = open_workspace(FIXTURE)
    assert [p.name for p in ws.packages] == ["core", "plugin"]
    assert ws.name == "workspace"


def test_a_package_knows_whether_it_has_its_own_rules():
    ws = open_workspace(FIXTURE)
    by_name = {p.name: p for p in ws.packages}
    assert by_name["core"].has_rules is True
    assert by_name["plugin"].has_rules is False


def test_a_python_package_is_aliased_by_its_top_level_module():
    ws = open_workspace(FIXTURE)
    by_name = {p.name: p for p in ws.packages}
    assert "core" in by_name["core"].aliases


def test_owner_attributes_an_outside_name_to_a_sibling():
    from archview.workspace import _owner

    ws = open_workspace(FIXTURE)
    by_name = {p.name: p for p in ws.packages}
    assert _owner("core", by_name["plugin"], ws.packages) == "core"
    assert _owner("openai", by_name["plugin"], ws.packages) is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_workspace.py -v`
Expected: FAIL, `ModuleNotFoundError: archview.workspace`.

- [ ] **Step 3: Implement**

Create `src/archview/workspace.py`. `open_workspace`:

1. Resolve `root`; find the rules file with `find_config` unless `config_path` is given; `load_config` it.
2. `ConfigError` if `config.workspace is None` — "no `[archview.workspace]` table in <path>".
3. For each entry in `config.workspace.packages`: resolve it against the rules file's directory, error if it is not a directory, `open_project(path)`.
4. `Package.name = project.package`; `has_rules = project.config_path is not None`.
5. `ConfigError` naming both paths if two packages resolve to the same name.
6. Sort packages by name; `Workspace.name = config.package or root.name`.

`aliases(project) -> frozenset[str]`:
- always `project.package`
- for TypeScript, also the `name` from `<path>/package.json` when it exists, both with and without the `@scope/` prefix. Read it with `json.loads`, and ignore a missing or malformed file rather than failing the run.

`_owner(outside, importer, packages)`:
- if `outside` starts with `"../"`: resolve it against `importer.path` and return the name of the package whose `path` is a parent of the result (use `Path.resolve()` then `is_relative_to`); else `None`.
- else return the name of the first package (sorted) whose `aliases` contain `outside`, or `None`.

Keep each of these functions small; the repo targets complexity ≤ 5.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run archview check`
Expected: all pass. `archview check` catches a missing `[archview.allowed].workspace` entry — if it fails with `undeclared`, add the entry as described above.

- [ ] **Step 5: Commit**

```bash
git add src/archview/workspace.py archview.toml tests/test_workspace.py
git commit -m "Open a workspace of packages and attribute outside names to siblings

A cross-package import is an outside edge whose target is a sibling's
alias: the Python top-level module, the npm name, or a relative path.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 11: Cross-package edges and the workspace check

**Files:**
- Modify: `src/archview/workspace.py`
- Test: `tests/test_workspace.py`

**Interfaces:**
- Consumes: `Edges` and `check` (`archview.rules.check`), `component_edges`, `component_map`, `apply_baseline`, `Report`, `Problem`.
- Produces:

```python
def cross_edges(ws: Workspace) -> dict[tuple[str, str], list[Import]]
def check_workspace(ws: Workspace) -> WorkspaceReport

@dataclass(frozen=True, slots=True)
class WorkspaceReport:
    name: str
    packages: tuple[tuple[str, Report], ...]   # (package name, its own report)
    between: Report                            # the cross-package rules
    @property
    def failed(self) -> bool
```

`between` is an ordinary `Report` whose `project` is the workspace name and whose `components` are the package names, so every existing renderer works on it.

Restated from the spec:
- A package's own check runs **only when `has_rules`**.
- **`undeclared` does apply** at workspace level: a package missing from `[archview.workspace.allowed]` is a problem.
- Workspace `exceptions` are module-level, matched against the importing module and the outside name.
- Cycles between packages fail when `fail_on_cycles`.

- [ ] **Step 1: Write the failing test**

```python
from archview.workspace import check_workspace


def test_the_fixture_workspace_passes():
    report = check_workspace(open_workspace(FIXTURE))
    assert not report.failed


def test_a_package_without_rules_is_not_checked_inside():
    report = check_workspace(open_workspace(FIXTURE))
    assert [name for name, _ in report.packages] == ["core"]


def test_a_cross_package_import_that_is_not_allowed_fails(tmp_path):
    ws = workspace_with(tmp_path, allowed={"core": (), "plugin": ()})
    report = check_workspace(ws)
    assert not_allowed(report.between) == [("plugin", "core")]
    assert report.failed


def test_a_package_missing_from_the_workspace_allow_list_is_undeclared(tmp_path):
    ws = workspace_with(tmp_path, allowed={"core": ()})
    report = check_workspace(ws)
    assert [p.kind for p in report.between.problems if p.components == ("plugin",)] == [
        "undeclared"
    ]


def test_a_workspace_exception_exempts_a_cross_package_import(tmp_path):
    ws = workspace_with(
        tmp_path,
        allowed={"core": (), "plugin": ()},
        exceptions=[{"importer": "plugin.adapter", "imported": "core", "reason": "the port"}],
    )
    assert not check_workspace(ws).failed


def test_a_third_party_import_is_not_a_cross_package_edge(tmp_path):
    """plugin imports openai, which is nobody's sibling."""
    ws = workspace_with(tmp_path, allowed={"core": (), "plugin": ("core",)})
    assert "openai" not in {t for _, t in cross_edges(ws)}
```

Write a `workspace_with(tmp_path, **workspace_table)` helper that copies `FIXTURE` into `tmp_path` with `shutil.copytree` and rewrites the root `archview.toml` from the given table, so each test varies one thing. Write it at the top of the file and use it in every test that needs a variant.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_workspace.py -v`
Expected: FAIL, `cannot import name 'check_workspace'`.

- [ ] **Step 3: Implement**

`cross_edges(ws)`: for each package, build its `ComponentMap` and `Edges` via `component_edges(p.project.model, component_map(p.project.config, ...), p.project.config)`, then for every `(component, outside)` pair in `edges.outside`, ask `_owner`; when it answers a sibling name, group the imports under `(p.name, sibling)`. Skip `(name, name)`. Return sorted.

`check_workspace(ws)`: run each package's `project_report` where `has_rules`; build `between` by reusing the existing problem producers. The cleanest way to get `undeclared`, `not_allowed`, `forbidden` and `cycle` for free is to call the existing `_rule_problems` and `_cycle_problems` with an `Edges(internal=cross, outside={}, exceptions_used=set())` and a synthetic `Config` carrying the workspace's `allowed`/`forbidden`/`fail_on_*` and `table="archview.workspace"`. Apply the workspace `exceptions` while building `cross_edges`, with the same `_exemption` helper. If `_rule_problems` and `_cycle_problems` are private, either import them directly (same package, acceptable) or promote them; do not copy their bodies.

Apply the workspace baseline when `config.workspace.baseline` is set, with `apply_baseline`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run archview check`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/archview/workspace.py tests/test_workspace.py
git commit -m "Check the rules between packages in a workspace

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 12: Render a workspace report; `archview check` at the root

**Files:**
- Create: `src/archview/render/workspace.py`
- Modify: `src/archview/cli.py:123-168` (`_check`), `src/archview/project.py` (let `SeveralPackages` stand down at a workspace root)
- Test: `tests/test_cli_workspace.py` (create)

**Interfaces:**
- Consumes: `WorkspaceReport`; `report_to_dict`, `report_to_text` (`archview.render.check`).
- Produces:

```python
def workspace_to_text(report: WorkspaceReport, color: bool) -> str
def workspace_to_dict(report: WorkspaceReport) -> dict
```

JSON envelope, exactly:

```json
{"workspace": "<name>", "ok": true,
 "packages": [{"package": "core", "...": "report_to_dict fields"}],
 "between":  {"...": "report_to_dict fields"}}
```

i.e. each entry is `{"package": name, **report_to_dict(report)}`.

- [ ] **Step 1: Write the failing test**

```python
def test_check_at_a_workspace_root_checks_every_package(capsys):
    assert main(["check", str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert "core" in out
    assert "between packages" in out


def test_check_at_a_workspace_root_fails_on_a_cross_package_violation(tmp_path, capsys):
    root = workspace_dir(tmp_path, allowed={"core": (), "plugin": ()})
    assert main(["check", str(root)]) == 1
    assert "plugin -> core" in capsys.readouterr().out


def test_the_json_envelope(tmp_path, capsys):
    root = workspace_dir(tmp_path, allowed={"core": (), "plugin": ()})
    assert main(["check", str(root), "--format", "json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["workspace"] == root.name
    assert data["ok"] is False
    assert [p["package"] for p in data["packages"]] == ["core"]
    assert data["between"]["problems"][0]["from"] == "plugin"


def test_a_repo_without_a_workspace_table_is_unchanged(repo, capsys):
    """The existing single-package output must not move."""
    assert main(["check", str(repo), "--format", "json"]) in (0, 1)
    data = json.loads(capsys.readouterr().out)
    assert "workspace" not in data
    assert "packages" not in data


def test_a_workspace_root_does_not_ask_you_to_pick_a_package(tmp_path, capsys):
    root = workspace_dir(tmp_path)
    assert main(["check", str(root)]) == 0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_cli_workspace.py -v`
Expected: FAIL — `check` at the fixture root either errors with `SeveralPackages` or analyses one package.

- [ ] **Step 3: Implement**

Write `render/workspace.py`. Text format, matching the spec:

```
core            ok
plugin          1 problem
  VIOLATION ...
between packages  1 problem
  VIOLATION plugin -> core (1 import) not allowed by [archview.workspace.allowed].plugin
    plugin/src/plugin/adapter.py:1  from core.ports import Port
2 problems. exit 1
```

Reuse `report_to_text` for the body of each section rather than reimplementing it; write only the headers and the total. Check how `report_to_text` emits its own total line and suppress or adapt it so there is one total for the run, not one per package.

In `cli._check`, branch early: load the config at `args.path`; if it has a `workspace` table and no `--package` was given, run `check_workspace` and render with the workspace renderers. Otherwise the existing path, untouched. Exit `1 if report.failed else 0`.

`--update-baseline` at a workspace root updates the workspace baseline and each package baseline that is configured; `--stop-hook` keeps its existing semantics over the combined result.

In `project.py`, nothing needs to change if `_check` branches before `open_project` — verify that, and only touch `project.py` if it does not.

Add `"workspace"` to `render`'s allowed list in `archview.toml` if `render/workspace.py` imports it (it imports the `WorkspaceReport` type, so it will).

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run archview check`
Expected: all pass, including the "unchanged for a single package" regression test.

- [ ] **Step 5: Commit**

```bash
git add src/archview/render/workspace.py src/archview/cli.py archview.toml tests/test_cli_workspace.py
git commit -m "archview check at a workspace root: one run, one exit code

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 13: `workspace_view` and `archview graph` at the root

**Files:**
- Modify: `src/archview/workspace.py`, `src/archview/cli.py` (`_graph`, `_cycles`)
- Test: `tests/test_workspace.py`, `tests/test_cli_workspace.py`

**Interfaces:**
- Produces: `workspace_view(ws: Workspace, threshold: float = DEFAULT_THRESHOLD) -> View` — the **existing** `View` type, so `to_dot`, `to_mermaid`, `view_to_dict` and the UI renderer all work unchanged.

Per the spec: `ViewNode(id=name, name=name, kind="package", module_count=<the package's module count>, layer, in_cycle, fan_in, fan_out)`, `zone="isolated"`, other metric fields at their defaults. Abstractness is not computed across packages.

- [ ] **Step 1: Write the failing test**

```python
def test_the_workspace_view_is_the_packages_and_their_edges():
    view = workspace_view(open_workspace(FIXTURE))
    assert [n.id for n in view.nodes] == ["core", "plugin"]
    assert [(e.source, e.target, e.count) for e in view.edges] == [("plugin", "core", 1)]


def test_the_workspace_view_layers_the_packages():
    view = workspace_view(open_workspace(FIXTURE))
    layers = {n.id: n.layer for n in view.nodes}
    assert layers["plugin"] < layers["core"] or layers["core"] < layers["plugin"]


def test_a_package_node_counts_its_modules():
    view = workspace_view(open_workspace(FIXTURE))
    assert {n.id: n.module_count for n in view.nodes}["core"] == 3
```

and in `tests/test_cli_workspace.py`:

```python
def test_graph_at_a_workspace_root_shows_the_packages(capsys):
    assert main(["graph", str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert "plugin" in out and "core" in out


def test_graph_with_a_package_drills_in(capsys):
    assert main(["graph", str(FIXTURE), "--package", "core"]) == 0
    assert "ports" in capsys.readouterr().out
```

Check `test_a_package_node_counts_its_modules`'s expected number against the fixture you built in Task 9 before asserting it.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_workspace.py -v -k view`
Expected: FAIL, `cannot import name 'workspace_view'`.

- [ ] **Step 3: Implement**

`workspace_view` mirrors `build_view`'s shape: children are the package names, `counts` come from `cross_edges`, then `components`, `assign_layers` and `find_cycles` from `archview.model` exactly as `build_view` uses them. Build the `ViewEdge`s with `in_cycle` from the condensation, `abstract=False`, `type_checking=all(i.type_checking for i in imports)`.

In `cli._graph` and `cli._cycles`, branch on a workspace table the same way `_check` does in Task 12: at a workspace root with no `--package`, use `workspace_view` / the cross-package cycles; otherwise today's path. Factor the "is this a workspace root, and did the user not pick a package" test into one helper in `cli.py` used by all three commands.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run archview check` and by hand:

```bash
uv run archview graph tests/fixtures/workspace --format dot
uv run archview graph tests/fixtures/workspace --format mermaid
```

Expected: valid DOT and Mermaid with two nodes and one edge.

- [ ] **Step 5: Commit**

```bash
git add src/archview/workspace.py src/archview/cli.py tests/
git commit -m "The workspace view: packages as nodes, their imports as edges

It returns the existing View, so DOT, Mermaid, the violations overlay
and the UI renderer work on it unchanged.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 14: Rename the viewer's `Workspace` to `ViewerState`

**Files:**
- Rename: `src/archview/server/workspace.py` → `src/archview/server/state.py`
- Modify: `src/archview/server/app.py`, `src/archview/cli.py:302` (`_serve`), any test importing it

**Interfaces:**
- Produces: `class ViewerState` with exactly today's methods and behaviour.

This is a **pure rename**, no behaviour change, done as its own commit so the next task's diff is readable. The existing class means "the one project the viewer is looking at" and would otherwise collide with the workspace concept.

- [ ] **Step 1: Find every reference**

Run: `grep -rn "Workspace\|server.workspace\|server import workspace" src tests`
Write the list down; every one must be updated.

- [ ] **Step 2: Rename**

```bash
git mv src/archview/server/workspace.py src/archview/server/state.py
```

Rename the class to `ViewerState`, update its docstring to say what it is ("the project the viewer is looking at, with its cached views"), and update every import and use found in Step 1.

- [ ] **Step 3: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run archview check`
Expected: all pass, with no test changes beyond the renamed import.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Rename the viewer's Workspace to ViewerState

It means the project the viewer is looking at, which collides with the
workspace of packages. Pure rename.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 15: The viewer opens a workspace

**Files:**
- Modify: `src/archview/server/state.py`, `src/archview/server/app.py`, `src/archview/ui/` (the drill-down and breadcrumb), `src/archview/cli.py` (`_serve`)
- Test: `tests/test_server.py` (find the existing server tests and follow them)

**Interfaces:**
- `ViewerState` accepts a workspace root and holds either one `Project` or a `Workspace`.
- `/api/view` gains `package=`. With a workspace and no `package`, it returns `workspace_view`; with `package=X&root=Y` it returns that package's view. Existing single-package behaviour is unchanged when there is no workspace table.
- `/api/source` gains `package=`.
- `--watch` watches every package directory.

- [ ] **Step 1: Write the failing test**

Read the existing server tests first; they likely use FastAPI's `TestClient`. Follow that shape:

```python
def test_the_api_returns_the_workspace_view_at_the_top():
    client = client_for(FIXTURE)
    data = client.get("/api/view").json()
    assert sorted(n["id"] for n in data["nodes"]) == ["core", "plugin"]


def test_the_api_drills_into_a_package():
    client = client_for(FIXTURE)
    data = client.get("/api/view", params={"package": "core", "root": "core"}).json()
    assert "core.ports" in [n["id"] for n in data["nodes"]]


def test_the_api_reads_a_source_file_from_a_package():
    client = client_for(FIXTURE)
    body = client.get("/api/source", params={"package": "core", "module": "core.ports"}).json()
    assert "Port" in body["source"]


def test_a_single_package_repo_still_works(repo):
    client = client_for(repo)
    assert client.get("/api/view").json()["nodes"]
```

Check the actual response shape (`nodes`, `source`) against the existing tests before asserting on keys.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_server.py -v -k workspace`
Expected: FAIL.

- [ ] **Step 3: Implement**

`ViewerState` gains a `workspace: Workspace | None`. On `reload()`, if the config at the root has a workspace table, `open_workspace`; else `open_project` as today. The view cache key gains the package name.

In the UI, the breadcrumb becomes workspace → package → component → module: the client already keeps a breadcrumb stack with scroll positions, so add the package as one more level and carry `package` in the fetch. Clicking a package node at the top level opens that package's own view at its root. Read `src/archview/ui/` before changing it and follow the existing drill-down code rather than inventing a second mechanism.

`--watch`: watch every `Package.path` instead of the single repo.

- [ ] **Step 4: Verify, including by eye**

Run: `uv run pytest && uv run ruff check && uv run archview check`, then:

```bash
uv run archview serve tests/fixtures/workspace --no-open --port 8899
```

and fetch `/api/view` and `/api/view?package=core&root=core` with `curl` to confirm both shapes. If browser automation is available, open the page, click from the workspace level into `core` and back, and screenshot it; otherwise say plainly in the PR that the UI was verified through the API only.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "The viewer's top level is the packages, drilling into each

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 16: TypeScript in a workspace, docs, ADR — M8 closes

**Files:**
- Modify: `tests/fixtures/workspace/` (a TypeScript package), `tests/test_workspace.py`
- Create: `docs/decisions/0012-workspace-mode.md`
- Modify: `docs/02-requirements.md`, `docs/05-approach-and-roadmap.md`, `docs/06-using-archview-in-a-repo.md`, `AGENTS.md`, `pyproject.toml` (version)

**Interfaces:** consumes everything above.

- [ ] **Step 1: Write the failing TypeScript test**

Add a `web/` package to the fixture: a `package.json` with `"name": "@fixture/web"`, a `tsconfig.json`, and one source file importing a sibling by relative path. Reuse `tests/fixtures/ts-sample/node_modules/typescript` by pointing the new package's analysis at it, or symlink `node_modules`; check how `tests/typescript_support.py` gates the existing TypeScript tests and use the same `@requires_typescript` mark.

```python
@requires_typescript
def test_a_typescript_package_joins_the_workspace():
    ws = open_workspace(TS_WORKSPACE)
    assert "web" in [p.name for p in ws.packages]


@requires_typescript
def test_a_relative_import_is_attributed_to_the_sibling_package():
    ws = open_workspace(TS_WORKSPACE)
    assert ("web", "core") in cross_edges(ws)
```

If wiring `node_modules` for a second fixture proves fiddly, keep the TypeScript workspace fixture as a second directory beside the Python one rather than contorting the first — but do not skip the test. The npm-name and relative-path alias paths are the only untested part of `_owner`.

- [ ] **Step 2: Run it and watch it fail, then implement**

Run: `uv run pytest tests/test_workspace.py -v -k typescript`
Fix whatever `_owner` or `aliases` gets wrong for TypeScript. This is the step most likely to surface a real bug: the extractor classifies `../`-prefixed resolutions as external, and the alias join has to resolve them back to a package directory.

- [ ] **Step 3: Docs and the ADR**

Write `docs/decisions/0012-workspace-mode.md` in the style of `0006` and `0010`. Record:
- federation over a merged model, and why (one `separator`, one `project` string, colliding ids)
- the alias join, and the three kinds of alias
- `undeclared` applying at workspace level while `[archview.externals]` has no analogue — the universe is closed here and open there
- a listed package without its own rules file is unconstrained inside, and its inner check does not run at all
- the JSON envelope, and that each report keeps its existing shape

Update `docs/02-requirements.md` (a requirement row and the status table), `docs/05-approach-and-roadmap.md` (M7 and M8 rows in the milestone table), `docs/06-using-archview-in-a-repo.md` (a workspace section with the full rules file), and the "State of the repo" paragraph in `AGENTS.md`.

Bump `version` in `pyproject.toml` to `0.3.0` — a minor bump per milestone, and the rules file grew two new tables.

- [ ] **Step 4: Verify the whole branch**

```bash
uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check
uv run archview check tests/fixtures/workspace
uv run archview graph tests/fixtures/workspace
```

Then dogfood against a real workspace:

```bash
git -C ~/git/tiny-tale-backend worktree add /tmp/bespoke prototype/bespoke-story-interview
uv run archview check /tmp/bespoke/prototypes/bespoke-story
```

That repo has `component/` and `server/` and a single-package `archview.toml`; write a workspace table for it **in a scratch file outside that repo** (`--config`), confirm the run is sensible, and record what you saw in the PR body. Remove the worktree afterwards with `git -C ~/git/tiny-tale-backend worktree remove /tmp/bespoke`.

- [ ] **Step 5: Commit and open the PR**

```bash
git add -A
git commit -m "M8: TypeScript in a workspace, ADR 0012, docs and version 0.3.0

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
git push -u origin feat/outside-rules-and-workspace
gh pr create --title "Rules for imports that leave the package, and workspace mode" --body "..."
```

The PR body closes both issues (`Closes #1`, `Closes #2`), summarises the two milestones, lists what was verified and — honestly — what was not. End it with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW
```

---

## Self-review notes

**Spec coverage.** M7: outside names (T1–T2), `[archview.externals]` (T3–T4), `from = "*"` (T4), no `undeclared` for outside names (T4), stdlib rejection (T3), `from` must be a component (T5), dead-rule warnings (T5), rendering (T6), the viewer (T7), `init --externals` and the ADR (T8). `archview why <outside>` already works and is covered by a regression test in T8's verification. M8: config (T9), the federation and aliases (T10), cross-package check (T11), CLI and JSON (T12), the view (T13), the rename (T14), the viewer (T15), TypeScript and docs (T16).

**Known risk.** Task 11 reuses `_rule_problems` and `_cycle_problems` with a synthetic `Config`. If their signatures make that awkward, promote them to take exactly what they need rather than copying their bodies — a second implementation of the allow-list would drift.

**Naming consistency check.** `Edges.internal` / `Edges.outside` / `Edges.exceptions_used` (T2) are used under those names in T4, T11 and T13. `ComponentMap.outside()` (T1) is used in T2. `build_view(..., keep=)` (T7) is used in T13's mirror. `WorkspaceReport.packages` / `.between` (T11) are used in T12. `ViewerState` (T14) is used in T15. `ALL` is `"all"`; `ALL_COMPONENTS` is `"*"`; they are never interchanged.
