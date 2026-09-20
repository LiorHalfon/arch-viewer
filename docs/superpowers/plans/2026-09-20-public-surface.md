# M9 — A package's public surface: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a package declare which of its components are public, and enforce that across a workspace, so a plugin cannot reach the core's private domain (GitHub issue #4).

**Architecture:** The distinction is destroyed at extraction — grimp squashes every external import to its top-level name — so the work is recovering the target, not writing a rule. For Python a workspace-level grimp pass over the sibling packages resolves cross-package imports exactly; for TypeScript the resolved path is already there for relative imports. The per-package federation from M8 is untouched: this is a second, narrower query, consumed only by `cross_edges`.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `ruff`, grimp, networkx, Graphviz-WASM via DOT.

**Spec:** `docs/superpowers/specs/2026-09-20-public-surface-design.md` — read it alongside this plan.

## Global Constraints

- Python 3.12+; `from __future__ import annotations` at the top of every module; modern type hints (`str | None`).
- Before every commit all four must pass: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check .`, `uv run archview check`.
- **Deterministic output (N1):** byte-identical output for identical input; sort by name wherever there is a tie.
- **The model JSON stays at schema 3.** No field is added to `Import`, and no extractor output changes. If you find yourself wanting to bump the schema, stop and report it — the spec chose the workspace-layer route specifically to avoid that.
- **Backwards compatibility is non-negotiable.** A workspace with no `public` anywhere, and any single-package repo, must produce byte-identical output to v0.3. Golden files must not change except where a task says so.
- `tests/test_self_check.py` asserts this repo's own check produces zero warnings.
- Never edit `archview.toml` to make a check pass — fix the code or report it.
- Small functions; the repo targets cyclomatic complexity ≤ 5 where practical.
- Commit messages: imperative mood, no `feat:`/`fix:` prefixes. End every commit message with:

```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW
```

- Golden files: regenerate with `UPDATE_GOLDEN=1 uv run pytest`, then **read the diff** and explain each change. An unexplained golden change is a bug.

## File Structure

| File | Responsibility after this plan |
|---|---|
| `src/archview/extract/siblings.py` | **new** — the Python multi-package resolution pass. Takes plain `{name: source_root}` data, returns resolved targets. Knows nothing about `Workspace`. |
| `src/archview/rules/config.py` | `Config.public`; parsing and validation |
| `src/archview/rules/check.py` | the `private` problem kind; `check(..., in_workspace=)` |
| `src/archview/workspace.py` | `CrossEdges`; component attribution; public/qualified rules; the view's public nodes |
| `src/archview/model/view.py` | `ViewNode.parent` |
| `src/archview/render/dot.py`, `render/mermaid.py` | nest parented nodes in clusters/subgraphs |
| `src/archview/project.py` | `project_report(..., in_workspace=)` |
| `tests/fixtures/workspace/` | a private component in `core`, and a `public` list |

---

## Task 1: `public` in a package's own rules file

**Files:**
- Modify: `src/archview/rules/config.py` — `Config` dataclass, `TOP_KEYS`, `parse_config`
- Modify: `src/archview/rules/check.py` (`check`), `src/archview/project.py` (`project_report`)
- Test: `tests/test_rules_config.py`, `tests/test_rules_check.py`

**Interfaces:**
- Produces: `Config.public: tuple[str, ...] | None = None` — `None` means the table is absent and the whole package is public. An empty list is legal and means the package publishes nothing.
- Produces: `check(model: Model, config: Config, in_workspace: bool = False) -> Report` and `project_report(project: Project, in_workspace: bool = False) -> Report`.

`public` only constrains cross-package imports, so outside a workspace it does nothing. The spec forbids a silent no-op, so `check` emits a `Notice` — but only when it is *not* running as part of a workspace, hence the flag.

- [ ] **Step 1: Write the failing tests**

In `tests/test_rules_config.py`, using the file's existing `written(tmp_path, text)` helper:

```python
def test_public_is_parsed(tmp_path):
    config = written(tmp_path, """
        [archview]
        package = "core"
        public = ["ports", "types"]
    """)
    assert config.public == ("ports", "types")


def test_no_public_key_means_none(tmp_path):
    assert written(tmp_path, '[archview]\npackage = "core"\n').public is None


def test_an_empty_public_list_is_not_none(tmp_path):
    config = written(tmp_path, '[archview]\npackage = "core"\npublic = []\n')
    assert config.public == ()
```

In `tests/test_rules_check.py`, reusing that file's existing model builders:

```python
def test_public_outside_a_workspace_warns_that_it_does_nothing():
    config = Config(allowed={"api": [], "llm": []}, public=("api",))
    report = check(model("shop.api", "shop.llm"), config)
    assert [w.kind for w in report.warnings if w.kind == "public_ignored"] == ["public_ignored"]


def test_public_inside_a_workspace_does_not_warn():
    config = Config(allowed={"api": [], "llm": []}, public=("api",))
    report = check(model("shop.api", "shop.llm"), config, in_workspace=True)
    assert not [w for w in report.warnings if w.kind == "public_ignored"]
```

Read `tests/test_rules_check.py` first and match how it builds a model and a `Config`; the two lines above are illustrative of shape, not of that file's exact helper names.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_rules_config.py tests/test_rules_check.py -v -k "public"`
Expected: FAIL — unknown key `public`, then `AttributeError` / unexpected keyword `in_workspace`.

- [ ] **Step 3: Implement**

In `src/archview/rules/config.py`: add `public: tuple[str, ...] | None = None` to `Config` (immediately after `components`, so related keys sit together), add `"public"` to `TOP_KEYS`, and in `parse_config`:

```python
        public=_optional_str_list(table, "public", where),
```

with:

```python
def _optional_str_list(table: dict[str, Any], key: str, where: str) -> tuple[str, ...] | None:
    """Like `_str_list`, but distinguishes an absent key from an empty list."""
    if key not in table:
        return None
    return _strings(table[key], f"{where}.{key}")
```

In `src/archview/rules/check.py`, widen `check`:

```python
def check(model: Model, config: Config, in_workspace: bool = False) -> Report:
```

and pass `in_workspace` through to `_warnings`, which gains the same parameter and appends:

```python
    if config.public is not None and not in_workspace:
        warnings.append(
            Notice(
                "public_ignored",
                f"[{table}] public only constrains imports from other packages in a "
                "workspace; it has no effect here",
            )
        )
```

In `src/archview/project.py`, widen `project_report(project: Project, in_workspace: bool = False) -> Report` and pass the flag to `check`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`
Expected: all pass. Every existing caller of `check`/`project_report` keeps working through the default.

- [ ] **Step 5: Commit**

```bash
git add src/archview/rules/config.py src/archview/rules/check.py src/archview/project.py tests/
git commit -m "Parse a package's public component list

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 2: the Python sibling-resolution pass

**Files:**
- Create: `src/archview/extract/siblings.py`
- Modify: `archview.toml` (the `workspace` component regains an `extract` allowance — legitimately this time)
- Test: `tests/test_extract_siblings.py` (create)

**Interfaces:**
- Produces:

```python
Where = tuple[str, str, int]          # (importer module, file, line)

def resolve_targets(roots: Mapping[str, Path]) -> dict[Where, str]:
    """Every import between the given Python packages, resolved to its exact target.

    `roots` maps a top-level package name to the source root that makes it importable.
    The key identifies one import line; the value is the module it really reaches,
    e.g. `core.model` where a single-package model would only record `core`.
    """
```

This module takes plain data, not a `Workspace`, so it belongs in `extract/` and stays testable without opening a project. It must never import from `archview.project` or `archview.workspace`.

Verified behaviour this exists to capture (run against a scratch workspace before writing the plan):

```
plugin.adapter -> core.model    line 17: from core.model import Thing
plugin.adapter -> core.model    line 19: from core import model as m2
plugin.adapter -> core.ports    line  8: from core.ports import Port
```

- [ ] **Step 1: Write the failing test**

```python
"""The multi-package pass that recovers what grimp squashes (issue #4)."""

from __future__ import annotations

from pathlib import Path

from archview.extract.siblings import resolve_targets


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def two_packages(tmp_path: Path) -> dict[str, Path]:
    write(tmp_path, "core/src/core/__init__.py", "")
    write(tmp_path, "core/src/core/model.py", "class Thing: ...\n")
    write(tmp_path, "core/src/core/ports.py", "class Port: ...\n")
    write(tmp_path, "plugin/src/plugin/__init__.py", "")
    write(
        tmp_path,
        "plugin/src/plugin/adapter.py",
        "from core.ports import Port\n"
        "from core.model import Thing\n"
        "from core import model as m2\n",
    )
    return {"core": tmp_path / "core" / "src", "plugin": tmp_path / "plugin" / "src"}


def test_a_deep_import_resolves_to_the_exact_module(tmp_path):
    found = resolve_targets(two_packages(tmp_path))
    assert found[("plugin.adapter", "plugin/src/plugin/adapter.py", 1)] == "core.ports"
    assert found[("plugin.adapter", "plugin/src/plugin/adapter.py", 2)] == "core.model"


def test_an_aliased_re_export_resolves_too(tmp_path):
    """`from core import model as m2` names only `core`, but reaches `core.model`.

    This is the case that rules out reading the import line as text.
    """
    found = resolve_targets(two_packages(tmp_path))
    assert found[("plugin.adapter", "plugin/src/plugin/adapter.py", 3)] == "core.model"


def test_a_third_party_import_is_not_reported(tmp_path):
    roots = two_packages(tmp_path)
    write(tmp_path, "plugin/src/plugin/other.py", "import networkx\n")
    found = resolve_targets(roots)
    assert not [t for t in found.values() if t.startswith("networkx")]
```

The file paths in the keys are relative to a common base; confirm how `resolve_targets` reports them and make the assertions match what you implement, keeping them relative and POSIX-style for determinism.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_extract_siblings.py -v`
Expected: FAIL, `ModuleNotFoundError: archview.extract.siblings`

- [ ] **Step 3: Implement**

Create `src/archview/extract/siblings.py`. Reuse `python.py`'s `_importable` pattern — put every source root on `sys.path` for the duration and remove them afterwards. Build one graph:

```python
    graph = grimp.build_graph(*sorted(roots), include_external_packages=True, cache_dir=None)
```

Then, for every module internal to any of the packages, walk `find_modules_directly_imported_by` and `get_import_details`, keeping only targets internal to a *different* package in `roots`. Key each row by `(importer, file, line_number)`.

Two things to get right:

- **Determinism.** Sort the package names before building, and sort the rows before returning.
- **Cleanup on failure.** Use the same `contextmanager` + `finally` shape as `python.py:_importable` so a raised exception cannot leave a stale `sys.path` entry.

If two packages cannot be made importable together, let the error surface with both names in the message rather than swallowing it; Task 4 turns that into a clear `ConfigError`.

Add `extract` back to `workspace`'s list in `archview.toml` — Task 4 introduces the import that makes it real. If `archview check` reports it as an unused allowance until then, that is expected; note it in your report and leave it.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check .`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/archview/extract/siblings.py archview.toml tests/test_extract_siblings.py
git commit -m "Resolve imports between sibling Python packages exactly

grimp squashes an external import to its top-level name, so a single
package's model cannot say which part of a sibling it reached. One graph
over the packages together recovers it, including `from core import model`.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 3: attribute each cross-package import to a component

**Files:**
- Modify: `src/archview/workspace.py` — `cross_edges` and `_outside_imports`
- Test: `tests/test_workspace.py`

**Interfaces:**
- Consumes: `resolve_targets` (Task 2).
- Produces:

```python
@dataclass(frozen=True, slots=True)
class CrossEdges:
    """One pass over the workspace, three views of the same imports."""

    by_package: dict[Pair, list[Import]]     # (source package, target package) — as M8
    by_component: dict[Pair, list[Import]]   # (source package, "target.component")
    unplaced: tuple[Import, ...]             # target package known, component not

def cross_edges(ws: Workspace) -> CrossEdges
```

`by_package` must stay **exactly** what `cross_edges` returned in M8, so the existing package-level rules, the cycle check and `workspace_view` keep working untouched. Update those call sites to read `.by_package`.

Component attribution, by language:

- **Python** — look the import up in `resolve_targets` by `(importer, file, line)`. The component is the first segment of the resolved module below the target package: `core.model` → `model`; a bare `core` → the project-root component, named after the package.
- **TypeScript, relative import** — the outside name is the resolved path (`../../core/src/index`); resolve it against the importing package's directory and map it into the target package's module id, then take its first segment.
- **TypeScript, bare npm name** — the package entry point. Treat as public by construction: attribute it to the package root component, which is always published.
- **TypeScript, npm subpath** — cannot be placed. Goes to `unplaced`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_workspace.py`, using the existing `_prepare_workspace` / `workspace_with` helpers so the shared fixture is never modified:

```python
def test_a_cross_package_import_is_attributed_to_its_component(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core",)})
    (root / "plugin" / "src" / "plugin" / "adapter.py").write_text(
        "from core.ports import Port\nfrom core.model import Thing\n"
    )
    edges = cross_edges(open_workspace(root))
    assert set(edges.by_package) == {("plugin", "core")}
    assert set(edges.by_component) == {("plugin", "core.ports"), ("plugin", "core.model")}
    assert edges.unplaced == ()


def test_an_aliased_re_export_is_attributed_to_the_real_module(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core",)})
    (root / "plugin" / "src" / "plugin" / "adapter.py").write_text(
        "from core import model as m2\n"
    )
    edges = cross_edges(open_workspace(root))
    assert set(edges.by_component) == {("plugin", "core.model")}


def test_by_package_is_unchanged_by_component_attribution(tmp_path):
    """The M8 view of the same edges must not move."""
    ws = open_workspace(_prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core",)}))
    edges = cross_edges(ws)
    assert [(s, t, len(i)) for (s, t), i in edges.by_package.items()] == [("plugin", "core", 1)]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_workspace.py -v -k "attributed or by_package_is_unchanged"`
Expected: FAIL, `AttributeError: 'dict' object has no attribute 'by_package'`

- [ ] **Step 3: Implement**

Add `CrossEdges` to `workspace.py`. Have `cross_edges` build all three views in one pass, calling `resolve_targets` once for the workspace's Python packages (collect `{p.name: p.project.source_root}` for packages whose `model.language == "python"`).

Keep the M8 behaviour intact as you go: `checked_imports` still drops TYPE_CHECKING imports first, the package's own exceptions are still stripped via `replace(project.config, exceptions=())`, and workspace exceptions still apply. Read `_outside_imports`' docstring before touching it — it records why each of those is deliberate.

Update `_check_between`, `workspace_view` and `workspace_cycles` to read `.by_package`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`
Expected: all pass, including every M8 workspace test unmodified.

- [ ] **Step 5: Commit**

```bash
git add src/archview/workspace.py tests/test_workspace.py
git commit -m "Attribute each cross-package import to a component of its target

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 4: enforce `public`, and qualified targets

**Files:**
- Modify: `src/archview/workspace.py` (`_check_between`), `src/archview/rules/check.py` (`ProblemKind`, a `_private` producer)
- Modify: `src/archview/render/check.py` (`LABELS`, `PAIRS`)
- Test: `tests/test_workspace.py`, `tests/test_cli_workspace.py`

**Interfaces:**
- Consumes: `CrossEdges` (Task 3), `Config.public` (Task 1).
- Produces: `ProblemKind` gains `"private"`. A `Problem` with `kind="private"`, `components=(source_package, "target.component")`, `rule=f"{owner.config.table}.public"`.

Semantics, restated from the spec so you need not open it:

- No `public` on the target package → every component is public; nothing changes.
- An import must satisfy **both** the root's `[archview.workspace.allowed]` grant and the owner's `public`.
- A qualified grant (`bespoke_story.ports`) narrows further; it never widens.
- A qualified grant naming a component the owner does not publish is a **`ConfigError`** naming the owner's `public` list.
- `forbidden` wins over everything, and accepts qualified targets.
- An `unplaced` import is checked at package level and raises a `Notice` naming its file and line.

- [ ] **Step 1: Write the failing test**

```python
def test_reaching_a_private_component_fails(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core",)})
    (root / "core" / "archview.toml").write_text(
        '[archview]\npackage = "core"\nsource_roots = ["src"]\npublic = ["ports"]\n'
        "[archview.allowed]\nmodel = []\nports = ["model"]\n"
    )
    (root / "plugin" / "src" / "plugin" / "adapter.py").write_text(
        "from core.model import Thing\n"
    )
    report = check_workspace(open_workspace(root))
    assert [(p.kind, p.components) for p in report.between.problems] == [
        ("private", ("plugin", "core.model"))
    ]
    assert report.failed


def core_rules(root, public: str | None) -> None:
    """Write core's own rules file, optionally declaring a public surface."""
    line = f"public = {public}\n" if public is not None else ""
    (root / "core" / "archview.toml").write_text(
        '[archview]\npackage = "core"\nsource_roots = ["src"]\n' + line +
        "[archview.allowed]\nmodel = []\nports = [\"model\"]\n"
    )


def plugin_imports(root, statement: str) -> None:
    (root / "plugin" / "src" / "plugin" / "adapter.py").write_text(statement + "\n")


def test_reaching_a_public_component_passes(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core",)})
    core_rules(root, '["ports"]')
    plugin_imports(root, "from core.ports import Port")
    assert not check_workspace(open_workspace(root)).failed


def test_a_package_with_no_public_list_publishes_everything(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core",)})
    core_rules(root, None)
    plugin_imports(root, "from core.model import Thing")
    assert not check_workspace(open_workspace(root)).failed


def test_a_qualified_grant_narrows(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core.ports",)})
    core_rules(root, '["ports", "model"]')
    plugin_imports(root, "from core.model import Thing")
    report = check_workspace(open_workspace(root))
    assert [p.kind for p in report.between.problems] == ["not_allowed"]


def test_a_qualified_grant_naming_an_unpublished_component_is_an_error(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core.model",)})
    core_rules(root, '["ports"]')
    plugin_imports(root, "from core.ports import Port")
    with pytest.raises(ConfigError, match="core.model"):
        check_workspace(open_workspace(root))
```

`core_rules` and `plugin_imports` are helpers for this task's tests — put them next to them in the file, and reuse them in Task 5 rather than writing a second pair.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_workspace.py -v -k "private or qualified or publishes_everything"`
Expected: FAIL — no `private` kind exists yet.

- [ ] **Step 3: Implement**

In `rules/check.py` widen the kind:

```python
ProblemKind = Literal[
    "not_allowed", "forbidden", "undeclared", "cycle", "zone", "outside", "private"
]
```

and add a producer beside `_outside`:

```python
def _private(
    source: str, target: str, imports: list[Import], published: tuple[str, ...],
    rule: str, fails: bool
) -> Problem:
    package = target.split(".")[0]
    may = ", ".join(f"{package}.{name}" for name in published) or "nothing"
    return Problem(
        kind="private",
        rule=rule,
        components=(source, target),
        count=len(imports),
        imports=tuple(imports),
        hint=(
            f"{target} is not part of {package}'s public surface. {package} publishes: "
            f"{may}. Import one of those, or ask {package}'s owner to publish it."
        ),
        fails=fails,
    )
```

In `workspace.py`, extend `_check_between` to run the component-level rules over `edges.by_component`, after the existing package-level pass. Validate qualified grants against the owner's `public` first and raise `ConfigError` before any problem is produced, so a misconfigured file fails cleanly rather than half-reporting.

In `render/check.py` add `"private": "PRIVATE"` to `LABELS` and `"private"` to `PAIRS`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/archview/workspace.py src/archview/rules/check.py src/archview/render/check.py tests/
git commit -m "Check a cross-package import against the target's public surface

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 5: draw the public surface on the package boundary

**Files:**
- Modify: `src/archview/model/view.py` (`ViewNode`), `src/archview/workspace.py` (`workspace_view`)
- Modify: `src/archview/render/dot.py`, `src/archview/render/mermaid.py`
- Test: `tests/test_workspace.py`, `tests/test_golden.py`

**Interfaces:**
- Produces: `ViewNode.parent: str | None = None`. A public component is a node with `kind="package"`, `id` = the qualified `package.component`, `name` = the bare component name, and `parent` = its package's id.

This is the **view** JSON, not the model schema — nothing in `model/serialize.py`'s `SCHEMA_VERSION` changes.

Chosen from three mocked alternatives: published components become boxes on the package boundary, so a legal dependency visibly terminates at a port and a violation visibly bypasses one.

- A cross-package edge whose target is **public** lands on that component's node.
- One whose target is **private** lands on the package node itself, and the existing violations overlay already draws it red — that is the "bypasses the ports" reading.
- A package with no `public` declaration draws exactly as today: one node, no children.

- [ ] **Step 1: Write the failing test**

```python
def published(tmp_path, statement: str):
    """A workspace where core publishes `ports` only, and plugin imports `statement`."""
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core",)})
    core_rules(root, '["ports"]')      # the helper from Task 4
    plugin_imports(root, statement)
    return workspace_view(open_workspace(root))


def test_a_public_component_becomes_a_child_node(tmp_path):
    view = published(tmp_path, "from core.ports import Port")
    by_id = {n.id: n for n in view.nodes}
    assert by_id["core.ports"].parent == "core"
    assert by_id["core.ports"].name == "ports"
    assert by_id["core"].parent is None


def test_a_legal_edge_lands_on_the_public_component(tmp_path):
    view = published(tmp_path, "from core.ports import Port")
    assert ("plugin", "core.ports") in [(e.source, e.target) for e in view.edges]


def test_an_edge_to_a_private_component_lands_on_the_package(tmp_path):
    """It visibly bypasses the ports - which is the whole point of the drawing."""
    view = published(tmp_path, "from core.model import Thing")
    assert ("plugin", "core") in [(e.source, e.target) for e in view.edges]


def test_a_package_without_public_draws_as_one_node(tmp_path):
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core",)})
    view = workspace_view(open_workspace(root))
    assert [n.id for n in view.nodes] == ["core", "plugin"]
    assert all(n.parent is None for n in view.nodes)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_workspace.py -v -k "public_component or lands_on or one_node"`
Expected: FAIL, unexpected attribute `parent`.

- [ ] **Step 3: Implement**

Add `parent: str | None = None` to `ViewNode` — **last, after `zone`**, so no positional construction breaks. Check `view_to_dict` in `model/serialize.py` emits it (it uses `asdict`-style serialisation; confirm and adjust if it enumerates fields explicitly).

In `workspace_view`, after building the package nodes, add one child node per published component of each package that declares `public`, and retarget edges whose component is public onto the child id.

In `render/dot.py`, group nodes by `parent`: emit each parent's children inside

```
  subgraph cluster_<sanitised parent id> {
    label="<parent name>"; style="rounded"; color="#7890a0";
    ...child node lines...
  }
```

Sanitise the cluster id the same way node ids are already sanitised in that file — find the existing helper rather than writing a second one. In `render/mermaid.py` use its `subgraph` / `end` block equivalently.

- [ ] **Step 4: Run the tests, and look at the output**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`

Then look at it, and paste the output in your report:

```bash
uv run archview graph tests/fixtures/workspace --format dot
uv run archview graph tests/fixtures/workspace --format mermaid
```

The DOT must be valid and contain a cluster per package that publishes components. If `dot` is on your PATH, `uv run archview graph tests/fixtures/workspace --format dot | dot -Tsvg -o /dev/null` must exit 0 — say in your report whether you were able to run that.

- [ ] **Step 5: Commit**

```bash
git add src/archview/model/view.py src/archview/workspace.py src/archview/render/ tests/
git commit -m "Draw a package's published components on its boundary

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 6: the TypeScript paths, the fixture, and the unplaced notice

**Files:**
- Modify: `tests/fixtures/workspace/` (a private component in `core`, a `public` list), `tests/fixtures/ts-workspace/`
- Modify: `src/archview/workspace.py` (the `unplaced` notice)
- Test: `tests/test_workspace.py`

**Interfaces:** consumes everything above.

The fixture change is the issue's own shape: `core` publishes `ports`, keeps `model` private, and a plugin reaches the private one.

TypeScript cases to cover, gated with the existing `@requires_typescript` mark (read `tests/typescript_support.py` and follow how the current TypeScript tests are gated):

- a **relative** import into a sibling's private component must fail;
- a **bare npm name** import must pass, because it resolves to the entry point, which is the public surface by construction;
- an **npm subpath** import must produce the `unplaced` notice rather than passing silently.

- [ ] **Step 1: Write the failing tests**

Add the three TypeScript cases plus:

```python
@requires_typescript
def test_an_unplaced_import_is_reported_not_ignored(tmp_path):
    """The one case we cannot resolve must be visible, never silently allowed."""
    root = tmp_path / "ts"
    shutil.copytree(TS_WORKSPACE, root, symlinks=True)
    (root / "web" / "src" / "index.ts").write_text(
        'import { hidden } from "@fixture/core/internal";\nexport const x = hidden;\n'
    )
    report = check_workspace(open_workspace(root))
    assert [w.kind for w in report.between.warnings] == ["unplaced_import"]
    assert "index.ts" in report.between.warnings[0].message
```

Copy with `symlinks=True` so the fixture's `node_modules` symlink survives the copy; without it the TypeScript extractor will not find its compiler. Check what `TS_WORKSPACE` is called in the existing tests and reuse that constant.

Note `_check_between` currently builds its `Report` with `warnings=()` hardcoded — ADR 0012 records that as a known gap. This task is where that changes, so thread the notices through.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_workspace.py -v -k "unplaced or typescript"`
Expected: FAIL.

- [ ] **Step 3: Implement**

Extend the fixtures, and give `_check_between` a real `warnings` tuple built from `CrossEdges.unplaced`:

```python
        Notice(
            "unplaced_import",
            f"{imp.file}:{imp.line} {imp.text}: could not tell which component of "
            f"{target} this reaches, so its public surface was not checked",
        )
```

Sort the notices by `(file, line)` for determinism.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`
Expected: all pass. Confirm in your report whether the TypeScript tests **ran** or **skipped** — `uv run pytest tests/test_workspace.py -rs` shows skip reasons.

- [ ] **Step 5: Commit**

```bash
git add tests/ src/archview/workspace.py
git commit -m "Cover the TypeScript paths and report an import we cannot place

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 7: ADR 0013, docs, version — M9 closes

**Files:**
- Create: `docs/decisions/0013-public-surface.md`
- Modify: `docs/02-requirements.md`, `docs/05-approach-and-roadmap.md`, `docs/06-using-archview-in-a-repo.md`, `AGENTS.md`, `pyproject.toml`

**Interfaces:** consumes everything above.

- [ ] **Step 1: Write ADR 0013**

In the house style of `docs/decisions/0006-checker-semantics.md` and `0012-workspace-mode.md` — read both first for the Date / Status / Context / Decision / Consequences shape and the terse voice.

Record, each with its reasoning:
- **The problem was extraction, not rules.** grimp squashes an external import to its top-level name, so a package's own model cannot say which part of a sibling it reached; `from core import model as m2` proves a text scan cannot recover it.
- **A second, narrower query rather than a merged model.** Why this does not reopen ADR 0012's federation decision: no ids are rewritten, no separator is shared, no `Model` is combined.
- **The contract lives with the package that owns it.** `public` in the owner's own rules file, so adding a sixth plugin needs no new rule.
- **Absent `public` means everything is public**, for backwards compatibility.
- **Both the root grant and the owner's `public` must pass**, and a qualified grant naming an unpublished component is a `ConfigError` — the same reasoning ADR 0011 used for stdlib rules: a rule that looks live but is not is worse than an error.
- **Published components are drawn on the package boundary**, chosen over a label on the node or nothing at the top level, because it makes the rule legible without reading text.
- **Known limitations, stated plainly, not softened:** the TypeScript npm-subpath gap and why fixing it would need a model-schema bump; the `sys.path` coexistence requirement of the Python pass; and that `public` says nothing about a package's internal structure.

- [ ] **Step 2: Update the docs**

`docs/06` gains a workspace section showing `public` and qualified targets; `docs/02` gains a requirement row and a status-table line; `docs/05` gains an M9 milestone row; `AGENTS.md`'s "State of the repo" paragraph moves to M1–M9 and its command block gains nothing new unless you added a flag. Keep `AGENTS.md` terse — it is deliberately short.

Bump `version` in `pyproject.toml` to `0.4.0`: a minor bump per milestone, and the rules file gained a key.

- [ ] **Step 3: Verify the whole branch**

```bash
uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check
uv run archview check tests/fixtures/workspace
uv run archview graph tests/fixtures/workspace
uv run archview check --format json | python3 -c "import json,sys; print(json.load(sys.stdin)['unused_allowances'])"
```

The last must print `[]`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "M9: ADR 0013, docs and version 0.4.0

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Self-review notes

**Spec coverage.** §2 Python pass → T2; §2 TypeScript → T3, T6; §3 rules surface → T1, T4; §4 checker semantics → T4; §4 unplaced notice → T6; §5 viewer → T5; §6 testing → T3–T6; §7 limitations → T7's ADR.

**Known risk.** Task 3 changes `cross_edges`' return type, which M8 code reads in three places. `by_package` must stay byte-identical or the M8 tests will catch it — and they should be allowed to.

**Naming consistency.** `resolve_targets` (T2) is called in T3. `CrossEdges.by_package` / `.by_component` / `.unplaced` (T3) are used in T4, T5, T6. `Config.public` (T1) is read in T4 and T5. `ViewNode.parent` (T5) is rendered in T5. `ProblemKind` `"private"` (T4) is labelled in T4.
