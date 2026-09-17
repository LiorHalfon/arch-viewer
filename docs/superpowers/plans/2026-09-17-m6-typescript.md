# M6 TypeScript Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `archview` analyses TypeScript code bases (graph, check, init, metrics, queries, viewer) through the same model as Python, accepted on `~/git/storygenerator`.

**Architecture:** A small Node script (`extract/typescript.mjs`) loads the analysed repo's own `typescript` package, reads the tsconfig (following `extends` and `references`) and prints raw import facts as JSON. `extract/typescript.py` turns those facts into a `Model` whose ids are file paths joined by `/`. The model gains a `separator` field; every place above the extractor that split ids on `.` uses the helpers in the new `model/names.py` with `model.separator` instead.

**Tech Stack:** Python 3.12, uv, pytest, ruff; Node.js ≥ 18 at run time, the analysed repo's `typescript` (fixture pins 5.9.3); FastAPI viewer with vanilla JS.

**Spec:** `docs/superpowers/specs/2026-09-17-m6-typescript-design.md`

## Global Constraints

- Static analysis only: never execute the analysed project; `typescript.mjs` parses, never runs, the source. No network at run time (CI's `npm ci` for the fixture is the only install).
- archview never installs `typescript`; without it in the analysed repo: exit 2, `typescript not found in <repo>/node_modules; run npm install`. No global fallback.
- Deterministic output: sort by name on every tie; no timestamps or absolute paths in the model (ADR 0001).
- Model JSON schema version becomes **3**; Python output changes only by `"separator": "."`.
- Name helpers take `sep` explicitly, with no default.
- Dependency direction stays as `archview.toml` declares (`extract → model`, `project → extract, model, rules`). Never edit `archview.toml` to make `archview check` pass.
- Style: modern type hints (`str | None`), small functions, ruff line length 100, docstrings/comments at the density of the surrounding code.
- Every commit message ends with these two lines (after a blank line):
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW
  ```
- Work on branch `m6-typescript`. Do not push, tag or release without the user's go-ahead.
- After every task: `uv run pytest && uv run ruff format --check && uv run ruff check && uv run archview check` all pass.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/archview/model/names.py` | create | hierarchy on ids: `within`, `parent`, `ancestors`, `last`, `truncate` |
| `src/archview/model/graph.py` | modify | `Model.separator` |
| `src/archview/model/serialize.py`, `model/schema.json` | modify | schema 3, `separator`, `unresolved_import` |
| `src/archview/model/patterns.py` | modify | `matches_name`/`specificity` take `sep` |
| `src/archview/model/filter.py` | modify | test-name patterns per language |
| `src/archview/model/view.py`, `model/query.py` | modify | use `names` with `model.separator` |
| `src/archview/rules/components.py`, `rules/check.py` | modify | `ComponentMap.sep`, exemptions with `sep` |
| `src/archview/rules/config.py`, `rules/init.py` | modify | `language`, `tsconfig` keys |
| `src/archview/extract/typescript.py` | create | facts → `Model`; running the script; project name; tsconfig lookup |
| `src/archview/extract/typescript.mjs` | create | the Node side: tsconfig, resolution, per-file facts |
| `src/archview/project.py` | modify | language selection, `SeveralPackages` |
| `src/archview/cli.py` | modify | `--language`, `--tsconfig`, shared `_open` |
| `src/archview/server/workspace.py`, `ui/app.js` | modify | separator in payloads and UI; watch TypeScript files |
| `tests/fixtures/ts-sample/**` | create | the TypeScript fixture project |
| `tests/typescript_support.py` | create | skip markers for Node / the fixture's `node_modules` |
| `tests/test_names.py`, `tests/test_extract_typescript.py`, `tests/test_typescript_facts.py`, `tests/test_typescript_project.py` | create | tests |
| `.github/workflows/ci.yml`, `.gitignore` | modify | Node + fixture install in CI |
| `docs/decisions/0010-typescript-extractor.md` and other docs | create/modify | ADR, requirements, roadmap, usage, AGENTS.md |

---

### Task 1: Name helpers and the model's separator (schema 3)

**Files:**
- Create: `src/archview/model/names.py`, `tests/test_names.py`
- Modify: `src/archview/model/graph.py` (class `Model`), `src/archview/model/serialize.py`, `src/archview/model/schema.json`, `tests/test_serialize.py`, `tests/golden/sample-model.json` (regenerated)

**Interfaces:**
- Produces: `names.within(name: str, ancestor: str, sep: str) -> bool`, `names.parent(name: str, sep: str) -> str | None`, `names.ancestors(name: str, sep: str) -> list[str]` (shortest first, the name itself last), `names.last(name: str, sep: str) -> str`, `names.truncate(name: str, depth: int, sep: str) -> str`; `Model.separator: str = "."` (last field); `SCHEMA_VERSION = 3`.

- [ ] **Step 1: Write the failing tests**

`tests/test_names.py`:

```python
"""Hierarchy on node ids, for '.' (Python) and '/' (TypeScript) alike."""

import pytest

from archview.model.names import ancestors, last, parent, truncate, within


@pytest.mark.parametrize(
    ("name", "ancestor", "sep", "expected"),
    [
        ("app.api.routes", "app.api", ".", True),
        ("app.api", "app.api", ".", True),
        ("app.apis", "app.api", ".", False),
        ("app/components/Button.tsx", "app/components", "/", True),
        ("app/components.tsx", "app/components", "/", False),
        ("app/ui/Button.web.tsx", "app/ui/Button", "/", False),
    ],
)
def test_within_needs_the_separator_after_the_ancestor(name, ancestor, sep, expected):
    assert within(name, ancestor, sep) is expected


def test_parent_ancestors_last_and_truncate_split_on_the_given_separator():
    assert parent("app/ui/Button.web.tsx", "/") == "app/ui"
    assert parent("app", "/") is None
    assert ancestors("app/ui/Button.web.tsx", "/") == ["app", "app/ui", "app/ui/Button.web.tsx"]
    assert ancestors("app.api.routes", ".") == ["app", "app.api", "app.api.routes"]
    assert last("app/ui/Button.web.tsx", "/") == "Button.web.tsx"
    assert last("app.api.routes", ".") == "routes"
    assert truncate("app/ui/Button.tsx", 2, "/") == "app/ui"
```

In `tests/test_serialize.py`, replace `test_declares_the_schema_version_and_language` with:

```python
def test_declares_the_schema_version_language_and_separator(sample):
    data = model_to_dict(sample)
    assert (data["schema"], data["language"], data["separator"], data["project"]) == (
        3,
        "python",
        ".",
        "sample",
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_names.py tests/test_serialize.py -v`
Expected: FAIL — `ModuleNotFoundError: archview.model.names`, and `KeyError: 'separator'`.

- [ ] **Step 3: Implement**

`src/archview/model/names.py`:

```python
"""Hierarchy on node ids: a name, its parent and its ancestors.

Python ids are split by '.', TypeScript ids by '/' (ADR 0010). `sep` is always passed
explicitly - from `Model.separator` - so no caller silently assumes one language.
"""

from __future__ import annotations


def within(name: str, ancestor: str, sep: str) -> bool:
    """True if `name` is `ancestor` or lies below it."""
    return name == ancestor or name.startswith(ancestor + sep)


def parent(name: str, sep: str) -> str | None:
    head, found, _ = name.rpartition(sep)
    return head if found else None


def ancestors(name: str, sep: str) -> list[str]:
    """`a.b.c` -> `a`, `a.b`, `a.b.c`: shortest first, the name itself last."""
    parts = name.split(sep)
    return [sep.join(parts[: i + 1]) for i in range(len(parts))]


def last(name: str, sep: str) -> str:
    return name.rpartition(sep)[2]


def truncate(name: str, depth: int, sep: str) -> str:
    return sep.join(name.split(sep)[:depth])
```

`src/archview/model/graph.py` — add the field at the end of `Model` and mention it in the docstring:

```python
@dataclass(frozen=True, slots=True)
class Model:
    """Everything an extractor produces; every view is derived from this.

    `separator` splits a node id into its ancestors: '.' for Python, '/' for TypeScript.
    """

    project: str
    nodes: tuple[Node, ...]
    imports: tuple[Import, ...]
    language: str = "python"
    warnings: tuple[ExtractionWarning, ...] = ()
    separator: str = "."
```

`src/archview/model/serialize.py`: `SCHEMA_VERSION = 3`; in `model_to_dict` add `"separator": model.separator,` right after `"language"`; in `model_from_dict` add `separator=data["separator"],` after `language=`.

`src/archview/model/schema.json`:
- `"$id"`: `https://github.com/liorhalfon/archview/schema/model-3.json`
- `"required"` (top level): `["schema", "language", "separator", "project", "nodes", "imports", "warnings"]`
- `"schema": {"const": 3}`
- add after `"language"`:
  ```json
  "separator": {
    "enum": [".", "/"],
    "description": "splits a node id into its ancestors: '.' for Python, '/' for TypeScript"
  },
  ```
- `"project"` description: `"the top-level package or TypeScript project analysed"`
- node `"id"` description: `"unique; its ancestors are the prefixes ending before a separator"`
- import `"type_checking"` description: `"only for type checkers: under if TYPE_CHECKING: (Python), import type (TypeScript)"`
- import `"lazy"` description: `"runs on call, not on import: inside a function (Python, require), import() (TypeScript)"`
- warning `"kind"`: `{"enum": ["dynamic_import", "unresolved_import"]}`
- warning `"target"` description: `"the imported name or specifier, when it is a string literal"`

- [ ] **Step 4: Run the tests, then accept the golden change**

Run: `uv run pytest tests/test_names.py tests/test_serialize.py -v` → PASS.
Run: `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py && git diff --stat tests/golden`
Expected: only `tests/golden/sample-model.json` changed (schema 2 → 3, one `separator` line). Then `uv run pytest` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/archview/model tests/test_names.py tests/test_serialize.py tests/golden/sample-model.json
git commit   # "Model: a separator for node ids (schema 3)" + trailer
```

---

### Task 2: The model layer splits ids by the model's separator

**Files:**
- Modify: `src/archview/model/patterns.py`, `src/archview/model/filter.py`, `src/archview/model/view.py`, `src/archview/model/query.py`, `tests/builders.py`, `tests/test_patterns.py`, `tests/test_view.py`, `tests/test_query.py`, `tests/test_filter.py`, `tests/test_render_dot.py`

**Interfaces:**
- Consumes: `names.*` and `Model.separator` (Task 1).
- Produces: `matches_name(pattern: str, name: str, sep: str) -> bool`, `specificity(pattern: str, sep: str) -> tuple[int, int]`, `TEST_NAMES: dict[str, tuple[str, ...]]` keyed by language, `tests.builders.model(*imports, sep: str = ".")` (with `sep="/"` the model has `language="typescript"`, `separator="/"`). `query.within` is removed (use `names.within`).

- [ ] **Step 1: Extend the test builder**

Replace `tests/builders.py` with:

```python
"""Small model builders shared by the unit tests."""

from archview.model.graph import Import, Model, Node
from archview.model.names import ancestors, parent


def model(*imports: tuple[str, str], sep: str = ".") -> Model:
    """A model whose tree is implied by the names in `imports`, split by `sep`."""
    ids: set[str] = set()
    for pair in imports:
        for name in pair:
            ids.update(ancestors(name, sep))
    leaves = {name for pair in imports for name in pair}
    suffix = ".py" if sep == "." else ""
    nodes = tuple(
        Node(
            id=i,
            parent=parent(i, sep),
            kind="module" if i in leaves else "package",
            file=f"{i.replace(sep, '/')}{suffix}" if i in leaves else None,
        )
        for i in sorted(ids)
    )
    return Model(
        project=sorted(ids)[0].split(sep)[0],
        nodes=nodes,
        imports=tuple(
            Import(
                importer=a,
                imported=b,
                file=f"{a.replace(sep, '/')}{suffix}",
                line=n + 1,
                text=f"import {b}",
            )
            for n, (a, b) in enumerate(imports)
        ),
        language="python" if sep == "." else "typescript",
        separator=sep,
    )
```

- [ ] **Step 2: Write the failing tests**

`tests/test_patterns.py`: change the call in `test_matches_dotted_names_and_their_subtrees` to `matches_name(pattern, name, ".")`, and add:

```python
@pytest.mark.parametrize(
    ("pattern", "name", "expected"),
    [
        ("app/components", "app/components/ui/Button.tsx", True),
        ("app/components", "app/components.tsx", False),
        ("app/components/**", "app/components/ui/Button.tsx", True),
        ("app/*.ts", "app/i18n.ts", True),
        ("app/*.ts", "app/utils/format.ts", False),
        ("**/*.test.*", "app/services/pricing.test.ts", True),
        ("**/*.test.*", "app/services/pricing.ts", False),
        ("**/__mocks__", "app/services/__mocks__/pricing.ts", True),
    ],
)
def test_matches_slash_separated_names_and_their_subtrees(pattern, name, expected):
    assert matches_name(pattern, name, "/") is expected
```

`tests/test_view.py` — add:

```python
def test_slash_separated_ids_with_dotted_file_names_are_their_own_nodes():
    m = model(
        ("app/api/routes.ts", "app/domain/order.ts"),
        ("app/api/Button.web.tsx", "app/api/Button.tsx"),
        sep="/",
    )

    top = build_view(m, "app")
    api = build_view(m, "app/api")

    assert [(e.source, e.target, e.count) for e in top.edges] == [("app/api", "app/domain", 1)]
    assert [n.name for n in api.nodes] == ["Button.tsx", "Button.web.tsx", "routes.ts"]
    assert [(e.source, e.target) for e in api.edges] == [
        ("app/api/Button.web.tsx", "app/api/Button.tsx")
    ]


def test_tangled_packages_are_found_with_slash_separated_ids():
    m = model(("app/a/x.ts", "app/b/y.ts"), ("app/b/y.ts", "app/a/x.ts"), sep="/")

    assert tangled_packages(m) == frozenset({"app"})
```

`tests/test_query.py` — add:

```python
def test_queries_work_on_slash_separated_ids():
    m = model(
        ("app/api/routes.ts", "app/domain/order.ts"),
        ("app/domain/order.ts", "app/infra/db.ts"),
        sep="/",
    )
    m = replace(m, nodes=(*m.nodes, Node("@expo/vector-icons", None, "external")))

    assert resolve(m, "api/routes.ts") == "app/api/routes.ts"
    assert resolve(m, "@expo/vector-icons") == "@expo/vector-icons"
    assert [d.name for d in dependencies(m, "app/api")] == ["app/domain"]
    assert [d.name for d in dependents(m, "app/domain/order.ts")] == ["app/api/routes.ts"]
    assert [i.importer for i in why(m, "app/api", "app/infra").chain] == [
        "app/api/routes.ts",
        "app/domain/order.ts",
    ]
```

`tests/test_filter.py` — add:

```python
def test_hides_typescript_tests_by_their_conventional_names():
    from archview.model.filter import without_tests

    m = model(
        ("app/services/pricing.ts", "app/domain/order.ts"),
        ("app/services/pricing.test.ts", "app/services/pricing.ts"),
        ("app/services/pricing.spec.tsx", "app/services/pricing.ts"),
        ("app/services/__mocks__/pricing.ts", "app/domain/order.ts"),
        ("app/__tests__/flow.ts", "app/services/pricing.ts"),
        ("app/e2e/flow.ts", "app/services/pricing.ts"),
        ("app/ui/Button.e2e.tsx", "app/services/pricing.ts"),
        sep="/",
    )

    kept = without_tests(m)

    assert [(i.importer, i.imported) for i in kept.imports] == [
        ("app/services/pricing.ts", "app/domain/order.ts")
    ]
```

`tests/test_render_dot.py` — add (add `from tests.builders import model` and `from archview.model.view import build_view` to the imports if missing):

```python
def test_quotes_ids_with_slashes_dots_and_at_signs():
    m = model(("app/ui/Button.web.tsx", "app/@scope/x.ts"), sep="/")

    dot = to_dot(build_view(m, "app"))

    assert '"app/ui" -> "app/@scope" [label="1"' in dot
    assert '  "app/ui" [label="ui\\n(1 module)"' in dot
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_patterns.py tests/test_view.py tests/test_query.py tests/test_filter.py tests/test_render_dot.py -v`
Expected: FAIL — `matches_name() takes 2 positional arguments but 3 were given`; the view, query and filter slash tests fail on wrong owners/names.

- [ ] **Step 4: Implement**

`src/archview/model/patterns.py` — module docstring first paragraph becomes "Glob patterns over node names and file paths." and "A name pattern that names a package also covers everything below it, so `app.db` matches `app.db.session` (and `app/db` matches `app/db/session.ts`)."; import `from archview.model.names import ancestors`; replace the two functions:

```python
def matches_name(pattern: str, name: str, sep: str) -> bool:
    """True if `name` or one of its ancestors matches `pattern`, both split by `sep`."""
    regex = _compile(pattern, sep)
    return any(regex.fullmatch(prefix) for prefix in ancestors(name, sep))


def specificity(pattern: str, sep: str) -> tuple[int, int]:
    """Longer, less wild patterns win when several match the same name."""
    return (pattern.count(sep) + 1, -pattern.count("*"))
```

`src/archview/model/filter.py`:

```python
TEST_NAMES = {
    "python": ("**.tests", "**.test", "**.test_*", "**.*_test", "**.*_tests", "**.conftest"),
    "typescript": (
        "**/*.test.*",
        "**/*.spec.*",
        "**/*.e2e.*",
        "**/__tests__",
        "**/__mocks__",
        "**/test",
        "**/tests",
        "**/e2e",
    ),
}
```

In `without_names` the docstring becomes "Drop every node whose name matches a pattern (with its subtree)." and the match is `matches_name(p, n.id, model.separator)`. `without_tests` returns `without_names(model, TEST_NAMES.get(model.language, ()))`.

`src/archview/model/view.py` — add `from archview.model.names import ancestors, within`, and:

```python
def _owner(module: str, children: frozenset[str], sep: str) -> str | None:
    """The child of the root that `module` belongs to, if any."""
    return next((c for c in ancestors(module, sep) if c in children), None)


def _in_subtree(node_id: str, model: Model) -> list[Node]:
    return [n for n in model.nodes if within(n.id, node_id, model.separator)]
```

In `_grouped_imports` call `_owner(imp.importer, children, model.separator)` and `_owner(imp.imported, children, model.separator)`; in `_externals` call `_owner(imp.importer, inside, model.separator)`. In `tangled_packages` replace the two `parts` lines with `tangled.update(ancestors(package, model.separator))`.

`src/archview/model/query.py` — delete `within` and `_shorten`; add `from archview.model.names import truncate, within`; then:

```python
def resolve(model: Model, name: str) -> str:
    """A full name, a name relative to the project, or an external."""
    ids = sorted(n.id for n in model.nodes)
    known = set(ids)
    relative = f"{model.project}{model.separator}{name}"
    for candidate in (name, relative):
        if candidate in known:
            return candidate
    close = difflib.get_close_matches(relative, ids, n=3)
    close += difflib.get_close_matches(name, ids, n=3)
    hint = f"; did you mean {', '.join(dict.fromkeys(close))}?" if close else ""
    raise UnknownName(f"no module or package {name!r} in {model.project}{hint}")
```

In `why`: `sep = model.separator` first, then `within(inner, outer, sep)` and `within(i.importer, source, sep) and within(i.imported, target, sep)`. In `_shortest_chain`: `sep = model.separator` first, and the three calls become `within(importer, source, sep)`, `within(nxt, target, sep)`, `within(nxt, source, sep)`. In `_neighbours`:

```python
def _neighbours(model: Model, name: str, outgoing: bool) -> tuple[Dependency, ...]:
    sep = model.separator
    externals = {n.id for n in model.nodes if n.kind == "external"}
    depth = name.count(sep) + 1
    grouped: dict[str, list[Import]] = defaultdict(list)
    for imp in model.imports:
        here, there = (imp.importer, imp.imported) if outgoing else (imp.imported, imp.importer)
        if not within(here, name, sep) or within(there, name, sep):
            continue
        short = there if name in externals or there in externals else truncate(there, depth, sep)
        grouped[short].append(imp)
    return tuple(
        Dependency(other, tuple(sorted(imports, key=_import_key)))
        for other, imports in sorted(grouped.items())
    )
```

In `all_cycles`: `within(n.id, root, model.separator)`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -v` → all PASS (golden files unchanged). Run `uv run ruff format && uv run ruff check && uv run archview check`.

- [ ] **Step 6: Commit**

```bash
git add src/archview/model tests
git commit   # "Model: views, queries, patterns and test filters split ids by the separator" + trailer
```

---

### Task 3: Rules and config for slash-separated projects

**Files:**
- Modify: `src/archview/rules/components.py`, `src/archview/rules/check.py`, `src/archview/rules/config.py`, `src/archview/rules/init.py`, `tests/test_rules_check.py`, `tests/test_rules_config.py`

**Interfaces:**
- Consumes: `matches_name(pattern, name, sep)`, `specificity(pattern, sep)` (Task 2), `names.within` (Task 1), `tests.builders.model(..., sep="/")`.
- Produces: `ComponentMap(project: str, sep: str, explicit: Mapping[str, tuple[str, ...]], ignored: frozenset[str] = frozenset())`; `component_map(config: Config, project: str, sep: str) -> ComponentMap`; `Config.language: str | None`, `Config.tsconfig: str | None`; `LANGUAGES = ("python", "typescript")` in `rules/config.py`.

- [ ] **Step 1: Write the failing tests**

`tests/test_rules_check.py` — change the existing constructor call to `ComponentMap("app", ".", {"infra": ("app.infra",), "cache": ("app.infra.cache",)})` and add (import `Exemption` from `archview.rules.config` and `infer_rules` from `archview.rules.init` if not imported yet):

```python
def test_components_of_a_slash_separated_project_include_root_files():
    m = model(
        ("app/components/ui/Button.tsx", "app/utils/format.ts"),
        ("app/i18n.ts", "app/components/ui/Button.tsx"),
        sep="/",
    )
    config = Config(allowed={"components": (), "utils": (), "i18n.ts": ("components",)})

    assert kinds(check(m, config)) == [("not_allowed", ("components", "utils"))]


def test_slash_separated_component_patterns_and_exceptions():
    components = ComponentMap("app", "/", {"ui": ("app/components/ui",)})
    m = model(("app/components/ui/Button.tsx", "app/utils/format.ts"), sep="/")
    config = Config(
        allowed={"components": (), "utils": ()},
        exceptions=(Exemption("app/components/**", "app/utils/format.ts", "legacy"),),
    )

    assert components.of("app/components/ui/Button.tsx") == "ui"
    assert components.of("app/components/Card.tsx") == "components"
    assert components.of("app") == "app"
    assert kinds(check(m, config)) == []


def test_init_quotes_file_components_and_records_the_language():
    m = model(("app/i18n.ts", "app/utils/format.ts"), sep="/")

    text = infer_rules(m)

    assert 'language = "typescript"' in text
    assert '"i18n.ts" = ["utils"]' in text
```

`tests/test_rules_config.py` — add (import `ConfigError`, `parse_config` from `archview.rules.config` if missing, and `pytest`):

```python
def test_reads_the_language_and_tsconfig():
    config = parse_config({"language": "typescript", "tsconfig": "server/tsconfig.json"})

    assert (config.language, config.tsconfig) == ("typescript", "server/tsconfig.json")


def test_rejects_an_unknown_language():
    with pytest.raises(ConfigError, match="language must be one of 'python', 'typescript'"):
        parse_config({"language": "java"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rules_check.py tests/test_rules_config.py -v`
Expected: FAIL — `matches_name() missing 1 required positional argument: 'sep'` (existing rules tests), `unknown key 'language'`.

- [ ] **Step 3: Implement**

`src/archview/rules/components.py` — update the docstring example to mention both forms ("`shop.api.routes` belongs to `api`, as `shop/api/routes.ts` does"), import `from archview.model.names import within`, and:

```python
@dataclass(frozen=True, slots=True)
class ComponentMap:
    project: str
    sep: str
    explicit: Mapping[str, tuple[str, ...]]
    ignored: frozenset[str] = frozenset()

    def of(self, module: str) -> str | None:
        """The component `module` belongs to, or None if it is outside the project or ignored."""
        component = self._explicit(module) or self._default(module)
        return None if component in self.ignored else component

    def _explicit(self, module: str) -> str | None:
        hits = [
            (specificity(pattern, self.sep), name)
            for name, patterns in self.explicit.items()
            for pattern in patterns
            if matches_name(pattern, module, self.sep)
        ]
        if not hits:
            return None
        best = max(score for score, _ in hits)
        return min(name for score, name in hits if score == best)

    def _default(self, module: str) -> str | None:
        if module == self.project:
            return self.project
        if not within(module, self.project, self.sep):
            return None
        return module[len(self.project) + 1 :].split(self.sep)[0]

    def unmatched_patterns(self, modules: Iterable[str]) -> list[tuple[str, str]]:
        """(component, pattern) pairs that match no module - usually a typo."""
        names = sorted(modules)
        return [
            (name, pattern)
            for name, patterns in sorted(self.explicit.items())
            for pattern in patterns
            if not any(matches_name(pattern, m, self.sep) for m in names)
        ]
```

`src/archview/rules/check.py`:

```python
def component_map(config: Config, project: str, sep: str) -> ComponentMap:
    return ComponentMap(project, sep, config.components, frozenset(config.ignored))
```

In `component_edges` call `_exemption(imp, exemptions, model.separator)`, and:

```python
def _exemption(imp: Import, exemptions, sep: str) -> int | None:
    for index, e in enumerate(exemptions):
        if matches_name(e.importer, imp.importer, sep) and matches_name(
            e.imported, imp.imported, sep
        ):
            return index
    return None
```

In `check`: `components = component_map(config, model.project, model.separator)`. Search the rest of `rules/` for other `component_map(` / `ComponentMap(` / `matches_name(` calls (`grep -rn "component_map(\|ComponentMap(\|matches_name(" src`) and pass the separator the same way.

`src/archview/rules/config.py` — in `Config` add after `package`:

```python
    language: str | None = None
    tsconfig: str | None = None
```

Add `"language"` and `"tsconfig"` to `TOP_KEYS`; add `LANGUAGES = ("python", "typescript")` next to `ZONES`; in `parse_config` add `language=_language(table, where),` and `tsconfig=_optional_str(table, "tsconfig", where),` after `package=`; and:

```python
def _language(table: dict[str, Any], where: str) -> str | None:
    value = _optional_str(table, "language", where)
    if value is not None and value not in LANGUAGES:
        raise ConfigError(f"[{where}] language must be one of {', '.join(map(repr, LANGUAGES))}")
    return value
```

`src/archview/rules/init.py` — `components = component_map(config, model.project, model.separator)`, and after the `package = ...` line of `lines`:

```python
    if model.language != "python":
        lines.append(f"language = {json.dumps(model.language)}")
    if config.tsconfig:
        lines.append(f"tsconfig = {json.dumps(config.tsconfig)}")
```

(`_key` already quotes names that are not bare TOML keys.)

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -v` → all PASS, golden files unchanged (`tests/golden/sample-archview.toml` has no `language` line). `uv run ruff format && uv run ruff check && uv run archview check`.

- [ ] **Step 5: Commit**

```bash
git add src/archview/rules tests
git commit   # "Rules: components, exceptions and init for slash-separated projects; language and tsconfig keys" + trailer
```

---

### Task 4: TypeScript facts → model (pure Python)

**Files:**
- Create: `src/archview/extract/typescript.py`, `tests/test_extract_typescript.py`

**Interfaces:**
- Consumes: `Model`, `Node`, `Import`, `ExtractionWarning` (`model/graph.py`), `names.ancestors`, `names.parent`.
- Produces (used by Tasks 5–6):
  - Facts format (what `typescript.mjs` prints): `{"files": [{"file": str, "abstract": bool, "imports": [{"specifier": str | None, "resolved": str | None, "line": int, "text": str, "type_only": bool, "lazy": bool, "dynamic": bool, "builtin": bool, "alias": bool}]}]}`. `file` and `resolved` are POSIX paths relative to the repo (`resolved` may start with `../` or contain `node_modules`); `specifier` is None only for a dynamic import; `alias` is true when an unresolved specifier matches a tsconfig `paths` pattern whose target lies inside the repo; `builtin` for `node:*` or an unresolved Node builtin.
  - `Target(kind: str, name: str | None = None)`, kinds `"internal" | "external" | "drop" | "unresolved" | "dynamic"`
  - `classify(fact: dict[str, Any]) -> Target`
  - `find_source_root(files: Iterable[str]) -> str`
  - `build_model(facts: dict[str, Any], project: str, source_root: str | None = None) -> Model`

- [ ] **Step 1: Write the failing tests**

`tests/test_extract_typescript.py`:

```python
"""The TypeScript extractor's Python half: compiler facts turned into the model (ADR 0010)."""

import pytest

from archview.extract.typescript import Target, build_model, classify, find_source_root


def fact(specifier, resolved=None, line=1, **flags):
    return {
        "specifier": specifier,
        "resolved": resolved,
        "line": line,
        "text": f'import x from "{specifier}";',
        "type_only": False,
        "lazy": False,
        "dynamic": False,
        "builtin": False,
        "alias": False,
        **flags,
    }


def facts(*files):
    """`files`: (path, imports) or (path, imports, abstract)."""
    return {
        "files": [
            {"file": f[0], "imports": list(f[1]), "abstract": f[2] if len(f) > 2 else False}
            for f in files
        ]
    }


def test_ids_keep_the_extension_and_directories_become_packages():
    m = build_model(
        facts(("components/ui/Button.tsx", []), ("components/ui/Button.web.tsx", []), ("i18n.ts", [])),
        "app",
    )

    assert (m.language, m.separator, m.project) == ("typescript", "/", "app")
    assert [(n.id, n.parent, n.kind, n.file) for n in m.nodes] == [
        ("app", None, "package", None),
        ("app/components", "app", "package", None),
        ("app/components/ui", "app/components", "package", None),
        ("app/components/ui/Button.tsx", "app/components/ui", "module", "components/ui/Button.tsx"),
        (
            "app/components/ui/Button.web.tsx",
            "app/components/ui",
            "module",
            "components/ui/Button.web.tsx",
        ),
        ("app/i18n.ts", "app", "module", "i18n.ts"),
    ]


def test_a_file_next_to_a_directory_of_the_same_name_does_not_clash():
    m = build_model(facts(("T/T.tsx", []), ("T/T/Fade.tsx", [])), "app")

    assert {(n.id, n.kind) for n in m.nodes} >= {("app/T/T", "package"), ("app/T/T.tsx", "module")}


def test_the_one_top_level_directory_holding_every_file_is_the_source_root():
    m = build_model(facts(("src/a.ts", []), ("src/b/c.ts", [])), "hono")

    assert [(n.id, n.file) for n in m.nodes] == [
        ("hono", None),
        ("hono/a.ts", "src/a.ts"),
        ("hono/b", None),
        ("hono/b/c.ts", "src/b/c.ts"),
    ]
    assert find_source_root(["a.ts", "src/b.ts"]) == ""
    assert find_source_root(["src/a.ts", "lib/b.ts"]) == ""
    assert find_source_root([]) == ""


def test_root_config_files_are_left_out_before_the_source_root_is_chosen():
    m = build_model(facts(("vite.config.ts", []), ("src/a.ts", [])), "p")

    assert [n.id for n in m.nodes] == ["p", "p/a.ts"]


def test_a_given_source_root_drops_the_files_outside_it():
    m = build_model(
        facts(("src/a.ts", [fact("../scripts/x", resolved="scripts/x.ts")]), ("scripts/x.ts", [])),
        "p",
        source_root="src",
    )

    assert [n.id for n in m.nodes] == ["p", "p/a.ts"]
    assert m.imports == ()


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (fact("@/utils/x", resolved="utils/x.ts"), Target("internal", "utils/x.ts")),
        (fact("../legacy.js", resolved="legacy.js"), Target("internal", "legacy.js")),
        (fact("./global", resolved="global.d.ts"), Target("drop")),
        (fact("./data.json", resolved="data.json"), Target("drop")),
        (fact("node:fs", builtin=True), Target("drop")),
        (fact("@/assets/icon.png", alias=True), Target("drop")),
        (fact("./missing"), Target("unresolved")),
        (fact("@/utils/missing", alias=True), Target("unresolved")),
        (fact(None, dynamic=True), Target("dynamic")),
        (fact("react"), Target("external", "react")),
        (fact("@expo/vector-icons/Ionicons"), Target("external", "@expo/vector-icons")),
        (
            fact("react", resolved="node_modules/@types/react/index.d.ts"),
            Target("external", "react"),
        ),
        (
            fact(
                "@tanstack/react-query",
                resolved="node_modules/.pnpm/@tanstack+react-query@5.90.2/node_modules/"
                "@tanstack/react-query/build/modern/index.js",
            ),
            Target("external", "@tanstack/react-query"),
        ),
        (fact("@acme/ui", resolved="../ui/src/index.ts"), Target("external", "@acme/ui")),
        (fact("../../shared/x", resolved="../shared/x.ts"), Target("external", "../shared")),
        (
            fact("~/vendor/lib", resolved="node_modules/some-lib/index.js", alias=False),
            Target("external", "some-lib"),
        ),
    ],
)
def test_classifies_every_kind_of_specifier(given, expected):
    assert classify(given) == expected


def test_imports_carry_flags_and_externals_come_after_the_internal_nodes():
    m = build_model(
        facts(
            (
                "a.ts",
                [
                    fact("./b", resolved="b.ts", line=2, type_only=True),
                    fact("react", line=3),
                    fact("./c", resolved="c.ts", line=4, lazy=True),
                ],
            ),
            ("b.ts", []),
            ("c.ts", []),
        ),
        "p",
    )

    assert [(i.importer, i.imported, i.file, i.line, i.type_checking, i.lazy) for i in m.imports] == [
        ("p/a.ts", "p/b.ts", "a.ts", 2, True, False),
        ("p/a.ts", "p/c.ts", "a.ts", 4, False, True),
        ("p/a.ts", "react", "a.ts", 3, False, False),
    ]
    assert (m.nodes[-1].id, m.nodes[-1].parent, m.nodes[-1].kind) == ("react", None, "external")


def test_a_resolved_internal_file_outside_the_file_list_becomes_a_module():
    m = build_model(facts(("a.ts", [fact("./legacy.js", resolved="legacy.js")])), "p")

    assert ("p/legacy.js", "module", "legacy.js") in {(n.id, n.kind, n.file) for n in m.nodes}
    assert [(i.importer, i.imported) for i in m.imports] == [("p/a.ts", "p/legacy.js")]


def test_dynamic_and_unresolved_imports_become_warnings():
    m = build_model(
        facts(
            (
                "a.ts",
                [fact(None, line=5, dynamic=True, text="return import(name);"), fact("./missing", line=2)],
            )
        ),
        "p",
    )

    assert [(w.kind, w.module, w.file, w.line, w.target) for w in m.warnings] == [
        ("unresolved_import", "p/a.ts", "a.ts", 2, "./missing"),
        ("dynamic_import", "p/a.ts", "a.ts", 5, None),
    ]
    assert m.imports == ()


def test_abstract_comes_from_the_facts():
    m = build_model(facts(("types.ts", [], True), ("order.ts", [])), "p")

    assert {n.id: n.abstract for n in m.nodes if n.file} == {"p/order.ts": False, "p/types.ts": True}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_extract_typescript.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'archview.extract.typescript'`.

- [ ] **Step 3: Implement**

`src/archview/extract/typescript.py`:

```python
"""Turn what the TypeScript compiler reports into the model (ADR 0010).

`typescript.mjs` runs in Node with the analysed repo's own `typescript` package and
prints raw facts per file (see `read_facts`); every decision about ids, kinds,
externals and warnings is made here. Ids are paths below the source root, prefixed by
the project and keeping the file extension, split by '/'.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from archview.model.graph import ExtractionWarning, Import, Model, Node
from archview.model.names import ancestors, parent

SEP = "/"
CODE = re.compile(r"\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$")
DECLARATION = re.compile(r"\.d\.(ts|mts|cts)$")
NON_CODE = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|avif|ico|bmp|css|scss|sass|less|json|md|mdx|html|txt"
    r"|woff2?|ttf|otf|eot|mp3|mp4|wav|webm|lottie|riv|wasm|graphql|gql|ya?ml)$",
    re.IGNORECASE,
)
ROOT_CONFIG = re.compile(r"^[^/]*\.config\.[^/]+$")  # vite.config.ts, next.config.mjs


@dataclass(frozen=True, slots=True)
class Target:
    """Where one import goes: `internal` (a repo file), `external` (an npm package),
    `drop` (builtin, declaration, asset), `unresolved` or `dynamic` (warnings)."""

    kind: str
    name: str | None = None


def _package_name(specifier: str) -> str:
    """`react-native/Libraries/x` -> `react-native`; `@expo/vector-icons/x` -> `@expo/vector-icons`."""
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") and len(parts) > 1 else parts[0]


def _is_bare(specifier: str) -> bool:
    return not specifier.startswith((".", "/"))


def _external_name(specifier: str, resolved: str) -> str:
    """The package a bare specifier names; else the package or folder the file sits in."""
    if _is_bare(specifier) and not specifier.startswith("~"):
        return _package_name(specifier)
    parts = resolved.split("/")
    if "node_modules" in parts:
        last = max(i for i, p in enumerate(parts) if p == "node_modules")
        return _package_name("/".join(parts[last + 1 :]))
    ups = next(i for i, p in enumerate(parts) if p != "..")
    return "/".join(parts[: ups + 1])


def classify(fact: dict[str, Any]) -> Target:
    specifier, resolved = fact["specifier"], fact["resolved"]
    if fact["dynamic"]:
        return Target("dynamic")
    if fact["builtin"]:
        return Target("drop")
    if resolved is not None:
        return _resolved_target(specifier, resolved)
    if NON_CODE.search(specifier.split("?")[0]):
        return Target("drop")
    if not _is_bare(specifier) or fact["alias"]:
        return Target("unresolved")
    return Target("external", _package_name(specifier))


def _resolved_target(specifier: str, resolved: str) -> Target:
    if "node_modules" in resolved.split("/") or resolved.startswith("../"):
        return Target("external", _external_name(specifier, resolved))
    if DECLARATION.search(resolved) or not CODE.search(resolved):
        return Target("drop")
    return Target("internal", resolved)


def find_source_root(files: Iterable[str]) -> str:
    """The one top-level directory every file lies under (`src`), else '' (the repo)."""
    tops = {f.split(SEP)[0] if SEP in f else "" for f in files}
    return next(iter(tops)) if len(tops) == 1 and "" not in tops else ""


def _below(file: str, root: str) -> bool:
    return not root or file.startswith(root + SEP)


def build_model(facts: dict[str, Any], project: str, source_root: str | None = None) -> Model:
    """The model of one TypeScript project; `source_root` (relative to the repo) is
    found with `find_source_root` when not given, and files outside it are left out."""
    files = {f["file"]: f for f in facts["files"] if not ROOT_CONFIG.match(f["file"])}
    targets = {
        (file, index): classify(fact)
        for file, entry in files.items()
        for index, fact in enumerate(entry["imports"])
    }
    internal = set(files) | {
        t.name
        for t in targets.values()
        if t.kind == "internal" and t.name and not ROOT_CONFIG.match(t.name)
    }
    root = find_source_root(internal) if source_root is None else source_root.strip(SEP)
    ids = {
        file: f"{project}{SEP}{file[len(root) + 1 :] if root else file}"
        for file in sorted(internal)
        if _below(file, root)
    }
    imports, warnings = _imports(files, targets, ids, project)
    externals = sorted({i.imported for i in imports} - set(ids.values()))
    return Model(
        project=project,
        nodes=(*_tree(project, ids, files), *(Node(e, None, "external") for e in externals)),
        imports=tuple(sorted(imports, key=lambda i: (i.importer, i.imported, i.line))),
        language="typescript",
        warnings=tuple(sorted(warnings, key=lambda w: (w.module, w.line))),
        separator=SEP,
    )


def _tree(project: str, ids: dict[str, str], files: dict[str, Any]) -> list[Node]:
    """The project, every directory on the way to a file, and the files."""
    nodes = {project: Node(project, None, "package")}
    for file, node_id in ids.items():
        for directory in ancestors(node_id, SEP)[1:-1]:
            nodes.setdefault(directory, Node(directory, parent(directory, SEP), "package"))
        abstract = bool(files.get(file, {}).get("abstract"))
        nodes[node_id] = Node(node_id, parent(node_id, SEP), "module", file, abstract)
    return sorted(nodes.values(), key=lambda n: n.id)


def _imports(files, targets, ids, project) -> tuple[list[Import], list[ExtractionWarning]]:
    imports: list[Import] = []
    warnings: list[ExtractionWarning] = []
    for file in sorted(f for f in files if f in ids):
        importer = ids[file]
        for index, fact in enumerate(files[file]["imports"]):
            target = targets[(file, index)]
            if target.kind in ("dynamic", "unresolved"):
                kind = "dynamic_import" if target.kind == "dynamic" else "unresolved_import"
                warnings.append(
                    ExtractionWarning(
                        kind, importer, file, fact["line"], fact["text"], fact["specifier"]
                    )
                )
                continue
            imported = _imported(target, ids, project)
            if imported is None or imported == importer:
                continue
            imports.append(
                Import(
                    importer, imported, file, fact["line"], fact["text"], fact["type_only"], fact["lazy"]
                )
            )
    return imports, warnings


def _imported(target: Target, ids: dict[str, str], project: str) -> str | None:
    if target.kind == "internal":
        return ids.get(target.name or "")
    if target.kind == "external" and target.name and target.name != project:
        return target.name  # a package importing itself by name would clash with the root
    return None
```

Note on `~`: the `~/…` alias style (outline) is not a relative path, but it is not an npm package name either; `_external_name` therefore names it by the resolved path, which the parametrized case pins.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_extract_typescript.py -v` → PASS. If a line exceeds 100 characters, `uv run ruff format` fixes it. Then `uv run pytest && uv run ruff check && uv run archview check`.

- [ ] **Step 5: Commit**

```bash
git add src/archview/extract/typescript.py tests/test_extract_typescript.py
git commit   # "Extract: TypeScript compiler facts turned into the model" + trailer
```

---

### Task 5: The Node script, the fixture project and CI

**Files:**
- Create: `src/archview/extract/typescript.mjs`, `tests/typescript_support.py`, `tests/test_typescript_facts.py`, the fixture files under `tests/fixtures/ts-sample/` listed in Step 1
- Modify: `src/archview/extract/typescript.py` (add `ExtractionError`, `SCRIPT`, `read_facts`), `.gitignore`, `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the facts format (Task 4).
- Produces: `ExtractionError(Exception)`; `read_facts(repo: Path, tsconfig: Path) -> dict[str, Any]`; `tests.typescript_support.TS_SAMPLE: Path`, `requires_node`, `requires_typescript` (pytest skip markers).

- [ ] **Step 1: Create the fixture project**

`tests/fixtures/ts-sample/package.json`:
```json
{
  "name": "@acme/ts-sample",
  "private": true,
  "devDependencies": {
    "typescript": "5.9.3"
  }
}
```

`tests/fixtures/ts-sample/tsconfig.json` (solution style):
```json
{
  "files": [],
  "references": [{ "path": "./tsconfig.app.json" }, { "path": "./tsconfig.test.json" }]
}
```

`tests/fixtures/ts-sample/tsconfig.base.json`:
```json
{
  "compilerOptions": {
    "strict": true,
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "allowJs": true,
    "noEmit": true,
    "paths": { "@/*": ["./*"] }
  }
}
```

`tests/fixtures/ts-sample/tsconfig.app.json`:
```json
{
  "extends": "./tsconfig.base.json",
  "include": ["**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules", "**/*.test.ts"]
}
```

`tests/fixtures/ts-sample/tsconfig.test.json`:
```json
{
  "extends": "./tsconfig.base.json",
  "include": ["**/*.test.ts"]
}
```

`tests/fixtures/ts-sample/vite.config.ts`:
```ts
import { format } from "./utils/format";

export default { base: format(0) };
```

`tests/fixtures/ts-sample/global.d.ts`:
```ts
declare module "*.png";
```

`tests/fixtures/ts-sample/app/index.tsx`:
```tsx
import { Button } from "@/components";
import { format } from "@/utils/format";

export const loadHome = () => import("@/app/screens/Home");

export function loadByName(name: string) {
  return import(name);
}

export default function App() {
  return <Button label={format(1)} />;
}
```

`tests/fixtures/ts-sample/app/screens/Home.tsx`:
```tsx
import type { Order } from "@/domain/types";
import { total } from "@/domain/order";

export default function Home({ order }: { order: Order }) {
  return <p>{total(order)}</p>;
}
```

`tests/fixtures/ts-sample/app/screens/Home.web.tsx`:
```tsx
import Home from "./Home";

export default Home;
```

`tests/fixtures/ts-sample/components/index.ts`:
```ts
export { Button } from "./Button";
export * from "./Transitions/Transitions";
```

`tests/fixtures/ts-sample/components/Button.tsx`:
```tsx
import { useQuery } from "@tanstack/react-query";

interface Props {
  label: string;
}

function legacyIcon() {
  require("@/assets/icon.png");
  return require("../utils/legacy.js");
}

export function Button({ label }: Props) {
  useQuery({ queryKey: [label] });
  return (
    <button>
      {label}
      {legacyIcon()}
    </button>
  );
}
```

`tests/fixtures/ts-sample/components/Transitions/Transitions.tsx`:
```tsx
import { Fade } from "./Transitions/Fade";

export const Transitions = { Fade };
```

`tests/fixtures/ts-sample/components/Transitions/Transitions/Fade.tsx`:
```tsx
import React from "react";

export function Fade() {
  return React.createElement("div");
}
```

`tests/fixtures/ts-sample/domain/types.ts`:
```ts
export interface Order {
  id: string;
  lines: number[];
}

export type OrderId = Order["id"];
```

`tests/fixtures/ts-sample/domain/Repository.ts`:
```ts
import type { Order } from "./types";

export abstract class Repository {
  abstract find(id: string): Order | undefined;
}
```

`tests/fixtures/ts-sample/domain/order.ts`:
```ts
import type { Order } from "./types";
import { discount } from "@/services/pricing";

export function total(order: Order): number {
  return order.lines.reduce((sum, line) => sum + line, 0) - discount(order);
}
```

`tests/fixtures/ts-sample/services/pricing.ts`:
```ts
import { total } from "@/domain/order";
import type { Order } from "@/domain/types";

export function discount(order: Order): number {
  return order.lines.length > 3 ? total({ ...order, lines: [] }) / 10 : 0;
}
```

`tests/fixtures/ts-sample/services/pricing.test.ts`:
```ts
import { discount } from "./pricing";

export const cases = [discount({ id: "1", lines: [] })];
```

`tests/fixtures/ts-sample/services/__mocks__/pricing.ts`:
```ts
export const discount = () => 0;
```

`tests/fixtures/ts-sample/utils/format.ts`:
```ts
import { readFileSync } from "fs";
import path from "node:path";
import { nope } from "@/utils/missing";

export function format(value: number): string {
  return `${value}${path.sep}${readFileSync.name}${nope}`;
}
```

`tests/fixtures/ts-sample/utils/legacy.js`:
```js
module.exports = { icon: "legacy" };
```

Append to `.gitignore`:
```
# TypeScript fixture (npm ci --prefix tests/fixtures/ts-sample)
tests/fixtures/ts-sample/node_modules/
```

Run: `npm install --prefix tests/fixtures/ts-sample`
Expected: creates `tests/fixtures/ts-sample/package-lock.json` and `node_modules/typescript` (5.9.3). This is the one network step; it installs only into the fixture.

- [ ] **Step 2: Write the failing tests**

`tests/typescript_support.py`:

```python
"""The TypeScript tests need Node, and the fixture needs `npm ci`; without them the
tests skip - unless ARCHVIEW_REQUIRE_TS is set (CI), where a missing setup is an error."""

import os
import shutil
from pathlib import Path

import pytest

TS_SAMPLE = Path(__file__).parent / "fixtures" / "ts-sample"
HAS_NODE = shutil.which("node") is not None
READY = HAS_NODE and (TS_SAMPLE / "node_modules" / "typescript").is_dir()

if os.environ.get("ARCHVIEW_REQUIRE_TS") and not READY:
    raise RuntimeError(
        "ARCHVIEW_REQUIRE_TS is set but node or the fixture's node_modules is missing; "
        "run npm ci --prefix tests/fixtures/ts-sample"
    )

requires_node = pytest.mark.skipif(not HAS_NODE, reason="node is not installed")
requires_typescript = pytest.mark.skipif(
    not READY, reason="run npm ci --prefix tests/fixtures/ts-sample"
)
```

`tests/test_typescript_facts.py`:

```python
"""The Node half: what `typescript.mjs` reports for the fixture project (ADR 0010)."""

import json

import pytest

from archview.extract import typescript
from archview.extract.typescript import ExtractionError, read_facts
from tests.typescript_support import TS_SAMPLE, requires_node, requires_typescript


@pytest.fixture(scope="module")
def facts():
    if not (TS_SAMPLE / "node_modules" / "typescript").is_dir():
        pytest.skip("run npm ci --prefix tests/fixtures/ts-sample")
    return read_facts(TS_SAMPLE, TS_SAMPLE / "tsconfig.json")


def imports_of(facts, file):
    return {i["specifier"]: i for i in next(f for f in facts["files"] if f["file"] == file)["imports"]}


@requires_typescript
def test_lists_the_files_of_every_referenced_project_sorted(facts):
    files = [f["file"] for f in facts["files"]]

    assert files == sorted(files)
    assert set(files) == {
        "app/index.tsx",
        "app/screens/Home.tsx",
        "app/screens/Home.web.tsx",
        "components/Button.tsx",
        "components/Transitions/Transitions.tsx",
        "components/Transitions/Transitions/Fade.tsx",
        "components/index.ts",
        "domain/Repository.ts",
        "domain/order.ts",
        "domain/types.ts",
        "services/__mocks__/pricing.ts",
        "services/pricing.test.ts",
        "services/pricing.ts",
        "utils/format.ts",
        "vite.config.ts",
    }


@requires_typescript
def test_resolves_paths_aliases_barrels_and_same_named_directories(facts):
    assert imports_of(facts, "domain/order.ts")["@/services/pricing"]["resolved"] == "services/pricing.ts"
    assert imports_of(facts, "app/index.tsx")["@/components"]["resolved"] == "components/index.ts"
    assert (
        imports_of(facts, "components/Transitions/Transitions.tsx")["./Transitions/Fade"]["resolved"]
        == "components/Transitions/Transitions/Fade.tsx"
    )
    assert imports_of(facts, "app/screens/Home.web.tsx")["./Home"]["resolved"] == "app/screens/Home.tsx"


@requires_typescript
def test_flags_type_only_lazy_and_dynamic_imports(facts):
    home = imports_of(facts, "app/screens/Home.tsx")
    app = imports_of(facts, "app/index.tsx")
    button = imports_of(facts, "components/Button.tsx")

    assert (home["@/domain/types"]["type_only"], home["@/domain/order"]["type_only"]) == (True, False)
    assert (app["@/app/screens/Home"]["lazy"], app["@/app/screens/Home"]["resolved"]) == (
        True,
        "app/screens/Home.tsx",
    )
    assert app[None]["dynamic"] is True
    assert (button["../utils/legacy.js"]["lazy"], button["../utils/legacy.js"]["resolved"]) == (
        True,
        "utils/legacy.js",
    )
    assert button["@tanstack/react-query"]["lazy"] is False


@requires_typescript
def test_marks_builtins_and_unresolved_aliases(facts):
    fmt = imports_of(facts, "utils/format.ts")
    button = imports_of(facts, "components/Button.tsx")

    assert (fmt["fs"]["builtin"], fmt["node:path"]["builtin"]) == (True, True)
    assert (fmt["@/utils/missing"]["resolved"], fmt["@/utils/missing"]["alias"]) == (None, True)
    assert (button["@/assets/icon.png"]["resolved"], button["@/assets/icon.png"]["alias"]) == (None, True)
    assert (button["@tanstack/react-query"]["resolved"], button["@tanstack/react-query"]["alias"]) == (
        None,
        False,
    )


@requires_typescript
def test_records_the_line_and_its_text(facts):
    order = imports_of(facts, "domain/order.ts")["@/services/pricing"]

    assert (order["line"], order["text"]) == (2, 'import { discount } from "@/services/pricing";')


@requires_typescript
def test_abstract_means_an_abstract_class_or_only_type_exports(facts):
    abstract = {f["file"]: f["abstract"] for f in facts["files"]}

    assert abstract["domain/types.ts"] is True
    assert abstract["domain/Repository.ts"] is True
    assert abstract["domain/order.ts"] is False
    assert abstract["components/Button.tsx"] is False


@requires_node
def test_a_repo_without_typescript_installed_says_to_run_npm_install(tmp_path):
    (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["*.ts"]}))
    (tmp_path / "a.ts").write_text("export const a = 1;\n")

    with pytest.raises(ExtractionError, match="typescript not found in .*; run npm install"):
        read_facts(tmp_path, tmp_path / "tsconfig.json")


@requires_typescript
def test_a_broken_extends_is_an_error_not_a_quiet_fallback(tmp_path):
    (tmp_path / "node_modules").symlink_to(TS_SAMPLE / "node_modules")
    (tmp_path / "tsconfig.json").write_text(json.dumps({"extends": "./missing.json"}))
    (tmp_path / "a.ts").write_text("export const a = 1;\n")

    with pytest.raises(ExtractionError, match=r"tsconfig\.json: .*missing\.json"):
        read_facts(tmp_path, tmp_path / "tsconfig.json")


def test_no_node_on_the_path_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(typescript.shutil, "which", lambda _: None)

    with pytest.raises(ExtractionError, match="node not found on PATH"):
        read_facts(tmp_path, tmp_path / "tsconfig.json")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_typescript_facts.py -v`
Expected: FAIL — `ImportError: cannot import name 'ExtractionError'`.

- [ ] **Step 4: Implement the Python side of the boundary**

In `src/archview/extract/typescript.py` extend the imports with `import json`, `import shutil`, `import subprocess` and `from pathlib import Path`; extend the module docstring's second sentence to "…prints raw facts per file (the format is documented on `read_facts`)…"; and add below the constants:

```python
SCRIPT = Path(__file__).with_name("typescript.mjs")


class ExtractionError(Exception):
    """The TypeScript project cannot be read: no Node, no `typescript`, a broken tsconfig."""


def read_facts(repo: Path, tsconfig: Path) -> dict[str, Any]:
    """Run `typescript.mjs` on the project and return what it prints.

    `{"files": [{"file", "abstract", "imports": [{"specifier", "resolved", "line", "text",
    "type_only", "lazy", "dynamic", "builtin", "alias"}]}]}` - paths relative to `repo`;
    `specifier` is None only for a dynamic import; `alias`: an unresolved specifier that
    matches a tsconfig `paths` pattern pointing inside the repo.
    """
    node = shutil.which("node")
    if node is None:
        raise ExtractionError("node not found on PATH; archview needs Node.js to read TypeScript")
    done = subprocess.run(
        [node, str(SCRIPT), str(repo), str(tsconfig)], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise ExtractionError(done.stderr.strip() or f"{SCRIPT.name} exited with {done.returncode}")
    try:
        return json.loads(done.stdout)
    except ValueError as error:
        raise ExtractionError(f"{SCRIPT.name} printed no JSON: {error}") from None
```

- [ ] **Step 5: Implement the Node script**

`src/archview/extract/typescript.mjs`:

```js
// archview: what the TypeScript compiler knows about a project's imports (ADR 0010).
//
//   node typescript.mjs <repo> <tsconfig>
//
// Loads the analysed repo's own `typescript` package, reads the tsconfig (following
// `extends` and `references`) and prints {"files": [...]} as JSON; the format is
// documented on `read_facts` in typescript.py, which builds the model from it. The
// source is parsed, never executed. Any problem is one line on stderr and exit code 2.

import fs from "node:fs";
import path from "node:path";
import { builtinModules, createRequire } from "node:module";

const CODE = /\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/;
const DECLARATION = /\.d\.(ts|mts|cts)$/;
const NO_INPUTS = 18003; // a solution-style tsconfig lists no files of its own

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(2);
}

const [repoArg, tsconfigArg] = process.argv.slice(2);
if (!repoArg || !tsconfigArg) fail("usage: node typescript.mjs <repo> <tsconfig>");
const repo = fs.realpathSync(path.resolve(repoArg));
const rel = (file) => path.relative(repo, file).split(path.sep).join("/");
const real = (file) => {
  try {
    return fs.realpathSync(file);
  } catch {
    return file;
  }
};

function loadTypeScript() {
  try {
    return createRequire(path.join(repo, "package.json"))("typescript");
  } catch {
    return fail(`typescript not found in ${path.join(repo, "node_modules")}; run npm install`);
  }
}

const ts = loadTypeScript();
const message = (diagnostic) => ts.flattenDiagnosticMessageText(diagnostic.messageText, " ");

function parseConfig(configPath) {
  const host = {
    ...ts.sys,
    onUnRecoverableConfigFileDiagnostic: (d) => fail(`${rel(configPath)}: ${message(d)}`),
  };
  const parsed = ts.getParsedCommandLineOfConfigFile(configPath, {}, host);
  const errors = parsed.errors.filter(
    (d) => d.category === ts.DiagnosticCategory.Error && d.code !== NO_INPUTS,
  );
  if (errors.length > 0) fail(`${rel(configPath)}: ${message(errors[0])}`);
  return parsed;
}

function projects(configPath, found = new Map()) {
  if (found.has(configPath)) return found;
  const parsed = parseConfig(configPath);
  found.set(configPath, parsed);
  for (const reference of parsed.projectReferences ?? []) {
    projects(real(ts.resolveProjectReferencePath(reference)), found);
  }
  return found;
}

function aliasInsideRepo(specifier, options) {
  const base = options.baseUrl ?? options.pathsBasePath ?? repo;
  for (const [pattern, targets] of Object.entries(options.paths ?? {})) {
    const star = pattern.indexOf("*");
    const prefix = star < 0 ? pattern : pattern.slice(0, star);
    const suffix = star < 0 ? "" : pattern.slice(star + 1);
    const matched =
      star < 0
        ? specifier === pattern
        : specifier.length >= prefix.length + suffix.length &&
          specifier.startsWith(prefix) &&
          specifier.endsWith(suffix);
    if (!matched) continue;
    const middle = star < 0 ? "" : specifier.slice(prefix.length, specifier.length - suffix.length);
    return targets.some((target) => {
      const where = rel(path.resolve(base, target.replace("*", middle)));
      return !where.startsWith("..") && !where.split("/").includes("node_modules");
    });
  }
  return false;
}

function resolver(options) {
  const cache = ts.createModuleResolutionCache(repo, (name) => name, options);
  return (specifier, containingFile, mode) => {
    const found = ts.resolveModuleName(
      specifier, containingFile, options, ts.sys, cache, undefined, mode,
    ).resolvedModule;
    return found ? rel(real(found.resolvedFileName)) : null;
  };
}

const hasModifier = (node, kind) => (node.modifiers ?? []).some((m) => m.kind === kind);

function isImportCall(node) {
  return (
    ts.isCallExpression(node) &&
    (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
      (ts.isIdentifier(node.expression) && node.expression.text === "require"))
  );
}

function allTypeOnly(clause) {
  if (!clause) return false;
  if (clause.isTypeOnly) return true;
  const named = clause.namedBindings;
  return (
    !clause.name &&
    !!named &&
    ts.isNamedImports(named) &&
    named.elements.length > 0 &&
    named.elements.every((element) => element.isTypeOnly)
  );
}

function scan(file, options, resolve) {
  const text = fs.readFileSync(file, "utf8");
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
  const lines = text.split(/\r?\n/);
  const imports = [];
  const exported = { types: false, values: false };
  let abstractClass = false;

  const add = (node, literal, typeOnly, lazy) => {
    const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
    const common = { line, text: lines[line - 1].trim(), type_only: typeOnly, lazy };
    if (!literal) {
      imports.push({ specifier: null, resolved: null, ...common, dynamic: true, builtin: false, alias: false });
      return;
    }
    const specifier = literal.text;
    const mode = ts.getModeForUsageLocation?.(source, literal, options);
    const resolved = resolve(specifier, file, mode);
    const builtin =
      specifier.startsWith("node:") || (!resolved && builtinModules.includes(specifier.split("/")[0]));
    const alias = !resolved && aliasInsideRepo(specifier, options);
    imports.push({ specifier, resolved, ...common, dynamic: false, builtin, alias });
  };

  const visit = (node, inFunction) => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      add(node, node.moduleSpecifier, allTypeOnly(node.importClause), false);
    } else if (ts.isExportDeclaration(node)) {
      if (node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
        add(node, node.moduleSpecifier, node.isTypeOnly, false);
      }
      exported[node.isTypeOnly ? "types" : "values"] = true;
    } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
      const expression = node.moduleReference.expression;
      add(node, ts.isStringLiteral(expression) ? expression : null, node.isTypeOnly, inFunction);
    } else if (isImportCall(node)) {
      const [argument] = node.arguments;
      const literal = argument && ts.isStringLiteralLike(argument) ? argument : null;
      add(node, literal, false, node.expression.kind === ts.SyntaxKind.ImportKeyword || inFunction);
    } else if (ts.isExportAssignment(node)) {
      exported.values = true;
    }
    if (ts.isClassDeclaration(node) && hasModifier(node, ts.SyntaxKind.AbstractKeyword)) {
      abstractClass = true;
    }
    if (node.parent === source && hasModifier(node, ts.SyntaxKind.ExportKeyword)) {
      const typeOnly = ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node);
      exported[typeOnly ? "types" : "values"] = true;
    }
    const nested = inFunction || ts.isFunctionLike(node);
    ts.forEachChild(node, (child) => visit(child, nested));
  };
  ts.forEachChild(source, (child) => visit(child, false));

  return { file: rel(file), abstract: abstractClass || (exported.types && !exported.values), imports };
}

const configPath = path.resolve(tsconfigArg);
if (!fs.existsSync(configPath)) fail(`no ${rel(configPath)} in ${repo}`);

const owners = new Map(); // file -> the compiler options of the first tsconfig listing it
for (const parsed of projects(real(configPath)).values()) {
  for (const name of parsed.fileNames) {
    const file = real(name);
    const skipped = !CODE.test(file) || DECLARATION.test(file) || file.split(path.sep).includes("node_modules");
    if (!skipped && !owners.has(file)) owners.set(file, parsed.options);
  }
}

const resolvers = new Map();
const files = [...owners.keys()]
  .sort((a, b) => (rel(a) < rel(b) ? -1 : rel(a) > rel(b) ? 1 : 0))
  .map((file) => {
    const options = owners.get(file);
    if (!resolvers.has(options)) resolvers.set(options, resolver(options));
    return scan(file, options, resolvers.get(options));
  });
process.stdout.write(`${JSON.stringify({ files })}\n`);
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_typescript_facts.py -v`
Expected: PASS. If an assertion on the fixture fails, print the facts (`uv run python -c "from pathlib import Path; from archview.extract.typescript import read_facts; import json; print(json.dumps(read_facts(Path('tests/fixtures/ts-sample'), Path('tests/fixtures/ts-sample/tsconfig.json')), indent=1))"`) and fix the script, not the expectation, unless the expectation contradicts the spec.

Then check the package ships the script: `uv build --wheel -o /tmp/archview-wheel && unzip -l /tmp/archview-wheel/*.whl | grep typescript.mjs` → one line.

- [ ] **Step 7: CI**

Look up the current major of `actions/setup-node`: `gh api repos/actions/setup-node/releases/latest --jq .tag_name`. In `.github/workflows/ci.yml`, after the `setup-uv` step add (with that major):

```yaml
      - uses: actions/setup-node@vN
        with:
          node-version: 24
      - name: Install the TypeScript fixture
        run: npm ci --prefix tests/fixtures/ts-sample
```

and give the `Tests` step:

```yaml
        env:
          ARCHVIEW_REQUIRE_TS: "1"
```

Run: `ARCHVIEW_REQUIRE_TS=1 uv run pytest && uv run ruff format --check && uv run ruff check && uv run archview check` → PASS.

- [ ] **Step 8: Commit**

```bash
git add src/archview/extract tests/typescript_support.py tests/test_typescript_facts.py tests/fixtures/ts-sample .gitignore .github/workflows/ci.yml
git status --short tests/fixtures/ts-sample | grep node_modules && echo "node_modules must not be staged"
git commit   # "Extract: the Node side of the TypeScript extractor, with a fixture project" + trailer
```

---

### Task 6: Open TypeScript projects from the CLI

**Files:**
- Modify: `src/archview/extract/typescript.py` (add `project_name`, `find_tsconfigs`, `extract`), `src/archview/project.py`, `src/archview/cli.py`, `tests/test_golden.py`
- Create: `tests/test_typescript_project.py`, `tests/golden/ts-sample-model.json`, `tests/golden/ts-sample-view.json`

**Interfaces:**
- Consumes: `build_model`, `read_facts`, `ExtractionError` (Tasks 4–5); `Config.language`, `Config.tsconfig` (Task 3).
- Produces: `typescript.extract(repo: Path, name: str | None = None, tsconfig: str | None = None, source_root: str | None = None) -> Model`; `open_project(repo, package=None, config_path=None, config=None, language: str | None = None, tsconfig: str | None = None) -> Project` (for TypeScript `Project.package == model.project` and `Project.source_root == repo`); `SeveralPackages(ProjectError)`; CLI flags `--language {python,typescript}` and `--tsconfig PATH` on every command.

- [ ] **Step 1: Write the failing tests**

`tests/test_typescript_project.py`:

```python
"""A TypeScript project end to end: language selection, the CLI, errors (M6)."""

import json

import pytest

from archview.cli import main
from archview.model.filter import without_tests
from archview.model.serialize import SCHEMA, model_to_dict
from archview.model.view import build_view
from archview.project import ProjectError, open_project
from tests.typescript_support import TS_SAMPLE, requires_typescript


@pytest.fixture(scope="module")
def project():
    if not (TS_SAMPLE / "node_modules" / "typescript").is_dir():
        pytest.skip("run npm ci --prefix tests/fixtures/ts-sample")
    return open_project(TS_SAMPLE)


@requires_typescript
def test_a_root_tsconfig_selects_the_typescript_extractor(project):
    model = project.model

    assert (project.package, model.language, model.separator) == ("ts-sample", "typescript", "/")
    assert sorted(n.id for n in model.nodes if n.parent == "ts-sample") == [
        "ts-sample/app",
        "ts-sample/components",
        "ts-sample/domain",
        "ts-sample/services",
        "ts-sample/utils",
    ]
    assert [n.id for n in model.nodes if n.kind == "external"] == ["@tanstack/react-query", "react"]
    assert {(n.id, n.kind) for n in model.nodes} >= {
        ("ts-sample/components/Transitions/Transitions", "package"),
        ("ts-sample/components/Transitions/Transitions.tsx", "module"),
        ("ts-sample/utils/legacy.js", "module"),
    }


@requires_typescript
def test_warnings_views_cycles_and_test_filtering(project):
    model = project.model

    assert [(w.kind, w.module, w.target) for w in model.warnings] == [
        ("dynamic_import", "ts-sample/app/index.tsx", None),
        ("unresolved_import", "ts-sample/utils/format.ts", "@/utils/missing"),
    ]
    assert build_view(model, "ts-sample").cycles == (("ts-sample/domain", "ts-sample/services"),)
    hidden = {n.id for n in model.nodes} - {n.id for n in without_tests(model).nodes}
    assert hidden == {
        "ts-sample/services/__mocks__",
        "ts-sample/services/__mocks__/pricing.ts",
        "ts-sample/services/pricing.test.ts",
    }


@requires_typescript
def test_the_typescript_model_matches_the_published_schema(project):
    from jsonschema import Draft202012Validator

    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(model_to_dict(project.model))


@requires_typescript
def test_graph_why_and_init_work_on_the_fixture(capsys):
    assert main(["graph", str(TS_SAMPLE), "--root", "ts-sample/domain", "--json"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert [n["name"] for n in view["nodes"]] == ["Repository.ts", "order.ts", "types.ts"]

    assert main(["why", "domain", "services", str(TS_SAMPLE)]) == 0
    assert "ts-sample/domain/order.ts" in capsys.readouterr().out

    assert main(["init", str(TS_SAMPLE), "--stdout"]) == 0
    rules = capsys.readouterr().out
    assert 'package = "ts-sample"' in rules
    assert 'language = "typescript"' in rules
    assert 'domain = ["services"]' in rules


def test_a_missing_tsconfig_lists_the_ones_found(tmp_path):
    (tmp_path / "packages" / "core").mkdir(parents=True)
    (tmp_path / "packages" / "core" / "tsconfig.json").write_text("{}")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "tsconfig.json").write_text("{}")

    with pytest.raises(ProjectError, match=r"no tsconfig\.json in .*found packages/core/tsconfig\.json"):
        open_project(tmp_path, language="typescript")


def test_python_stays_the_default_without_a_tsconfig(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")

    assert open_project(tmp_path).model.language == "python"
```

`tests/test_golden.py` — add (import `from archview.project import open_project` and `from tests.typescript_support import TS_SAMPLE, requires_typescript`):

```python
@requires_typescript
def test_typescript_model_and_view_match_the_golden_files():
    model = open_project(TS_SAMPLE).model
    check("ts-sample-model.json", dumps(model))
    view = build_view(model, "ts-sample")
    check("ts-sample-view.json", json.dumps(view_to_dict(view), indent=2) + "\n")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_typescript_project.py tests/test_golden.py -v`
Expected: FAIL — `open_project() got an unexpected keyword argument 'language'`; the root-tsconfig test fails because the Python extractor finds no package.

- [ ] **Step 3: Implement `extract`**

In `src/archview/extract/typescript.py` add `import os`, then:

```python
def project_name(repo: Path) -> str:
    """`package.json` name without its `@scope/`; else the directory name."""
    try:
        data = json.loads((repo / "package.json").read_text())
    except (OSError, ValueError):
        data = None
    name = data.get("name") if isinstance(data, dict) else None
    return name.rpartition("/")[2] if isinstance(name, str) and name else repo.name


def find_tsconfigs(repo: Path, limit: int = 5) -> list[str]:
    """`tsconfig.json` files below `repo`, outside node_modules and hidden directories."""
    found = []
    for directory, subdirs, files in os.walk(repo):
        subdirs[:] = sorted(d for d in subdirs if d != "node_modules" and not d.startswith("."))
        if "tsconfig.json" in files:
            found.append((Path(directory) / "tsconfig.json").relative_to(repo).as_posix())
    return sorted(found)[:limit]


def extract(
    repo: Path, name: str | None = None, tsconfig: str | None = None, source_root: str | None = None
) -> Model:
    """The model of the TypeScript project at `repo`; `tsconfig` is relative to `repo`."""
    repo = Path(repo).resolve()
    wanted = tsconfig or "tsconfig.json"
    if not (repo / wanted).is_file():
        found = find_tsconfigs(repo)
        hint = f"; found {', '.join(found)} - pick one with --tsconfig" if found else ""
        raise ExtractionError(f"no {wanted} in {repo}{hint}")
    facts = read_facts(repo, repo / wanted)
    return build_model(facts, name or project_name(repo), source_root)
```

- [ ] **Step 4: Implement language selection in `project.py`**

Replace the extractor import with:

```python
from archview.extract import typescript
from archview.extract.discover import find_packages
from archview.extract.python import build_model
```

Add below `ProjectError`:

```python
class SeveralPackages(ProjectError):
    """More than one top-level Python package, and none was named."""
```

Replace `open_project` and add the helpers:

```python
def open_project(
    repo: Path,
    package: str | None = None,
    config_path: Path | None = None,
    config: Config | None = None,
    language: str | None = None,
    tsconfig: str | None = None,
) -> Project:
    """Analyse `repo` with the rules at `config_path`, found in the repo, or given as `config`."""
    repo = Path(repo).expanduser().resolve()
    if not repo.is_dir():
        raise ProjectError(f"{repo} is not a directory")
    path = config_path or find_config(repo)
    if config is None:
        config = load_config(path) if path else Config()
    tsconfig = tsconfig or config.tsconfig
    if _language(repo, config, language, tsconfig) == "typescript":
        model = _typescript_model(repo, config, package or config.package, tsconfig)
        return Project(repo, model.project, repo, config, path, without_files(model, config.exclude))
    packages = _packages(repo, config)
    name = _choose(packages, repo, package or config.package)
    model = build_model(name, packages[name], relative_to=repo)
    return Project(repo, name, packages[name], config, path, without_files(model, config.exclude))


def _language(repo: Path, config: Config, asked: str | None, tsconfig: str | None) -> str:
    """`--language`, then the rules file; else a tsconfig means TypeScript."""
    chosen = asked or config.language
    if chosen:
        return chosen
    return "typescript" if tsconfig or (repo / "tsconfig.json").is_file() else "python"


def _typescript_model(repo: Path, config: Config, name: str | None, tsconfig: str | None) -> Model:
    if len(config.source_roots) > 1:
        raise ProjectError(
            f"a TypeScript project has one source root; source_roots lists {len(config.source_roots)}"
        )
    root = config.source_roots[0] if config.source_roots else None
    try:
        return typescript.extract(repo, name, tsconfig, root)
    except typescript.ExtractionError as error:
        raise ProjectError(str(error)) from None
```

In `_choose`, raise `SeveralPackages(...)` instead of `ProjectError(...)` for the `len(packages) > 1` case.

- [ ] **Step 5: CLI flags and a shared opener**

In `src/archview/cli.py`: import `Project`, `SeveralPackages` from `archview.project` alongside the existing names. In `_common` add:

```python
    parser.add_argument(
        "--language", choices=["python", "typescript"], help="default: typescript if tsconfig.json"
    )
    parser.add_argument("--tsconfig", help="tsconfig to read, relative to the repo")
```

Add next to `_rules_project`:

```python
def _open(args: argparse.Namespace, names: list[str] | None = None) -> Project:
    """The project; with several Python packages, the first name may pick one."""
    options = {"language": args.language, "tsconfig": args.tsconfig}
    try:
        return open_project(args.path, args.package, args.config, **options)
    except SeveralPackages:
        if args.package or not names:
            raise
    try:
        return open_project(args.path, names[0].split(".")[0], args.config, **options)
    except ProjectError:
        raise ProjectError(f"several packages in {args.path}; pick one with --package") from None
```

Then:
- `_graph`: replace the first two lines with `project = _open(args, [args.root] if args.root else None)`.
- `_rules_project`: `project = _open(args)`.
- `_query_model`: replace the whole `try/except` with `project = _open(args, names)`.
- `_metrics`: `project = _open(args)`.
- `_init`: after the `--exclude` block add
  ```python
      if args.tsconfig:
          config = replace(config, tsconfig=args.tsconfig)
  ```
  and open with `open_project(repo, args.package, config=config, language=args.language)`.
- `_serve`: leave it unchanged here; Task 7 changes the `Workspace` signature and passes the two new options.
- `--runtime-only` help: `"leave out imports only type checkers see (TYPE_CHECKING, import type)"`.

- [ ] **Step 6: Run the tests and write the golden files**

Run: `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py && git status --short tests/golden`
Expected: two new files, `ts-sample-model.json` and `ts-sample-view.json`; Python golden files unchanged. Read both new files: ids like `ts-sample/app/index.tsx`, `file` paths relative to the fixture, no absolute paths, externals last, warnings as in the test.

Run: `uv run pytest -v && uv run ruff format && uv run ruff check && uv run archview check` → PASS.

Also by hand: `uv run archview graph tests/fixtures/ts-sample` and `uv run archview cycles tests/fixtures/ts-sample` print readable output; `uv run archview graph /tmp --language typescript; echo $?` prints `archview: no tsconfig.json in /private/tmp…` and `2`.

- [ ] **Step 7: Commit**

```bash
git add src/archview tests
git commit   # "Open TypeScript projects: language selection, --language and --tsconfig" + trailer
```

---

### Task 7: The viewer for TypeScript projects

**Files:**
- Modify: `src/archview/server/workspace.py`, `src/archview/ui/app.js`, `src/archview/cli.py` (`_serve`), `tests/test_server.py`

**Interfaces:**
- Consumes: `open_project(..., language, tsconfig)` (Task 6), `names.last` (Task 1).
- Produces: `Workspace(repo, package=None, config_path=None, language=None, tsconfig=None)`; `/api/project` gains `"language"` and `"separator"`; `source_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]` in `workspace.py`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_server.py` add (import `from archview.server.workspace import source_files` and `from tests.typescript_support import TS_SAMPLE, requires_typescript`):

```python
def test_python_summary_carries_the_language_and_separator(client):
    summary = client.get("/api/project").json()

    assert (summary["language"], summary["separator"]) == ("python", ".")


def test_watching_lists_source_files_outside_node_modules_and_hidden_directories(tmp_path):
    for name in ("a.ts", "src/b.tsx", "node_modules/x/c.ts", ".git/d.ts", "README.md"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("")

    found = source_files(tmp_path, (".ts", ".tsx"))

    assert [p.relative_to(tmp_path).as_posix() for p in found] == ["a.ts", "src/b.tsx"]


@requires_typescript
def test_serves_a_typescript_project(tmp_path):
    repo = tmp_path / "ts-sample"
    shutil.copytree(TS_SAMPLE, repo, ignore=shutil.ignore_patterns("node_modules"))
    (repo / "node_modules").symlink_to(TS_SAMPLE / "node_modules")
    client = TestClient(create_app(Workspace(repo)))

    summary = client.get("/api/project").json()
    view = client.get("/api/view").json()
    tree = client.get("/api/tree", params={"root": "ts-sample/domain"}).json()

    assert (summary["project"], summary["language"], summary["separator"]) == ("ts-sample", "typescript", "/")
    assert [n["name"] for n in view["nodes"]] == ["app", "components", "domain", "services", "utils"]
    assert [c["name"] for c in tree["children"]] == ["Repository.ts", "order.ts", "types.ts"]
    assert client.get("/api/source", params={"module": "ts-sample/domain/order.ts"}).status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL — `ImportError: cannot import name 'source_files'`, `KeyError: 'language'`.

- [ ] **Step 3: Implement the workspace changes**

In `src/archview/server/workspace.py` add `import os` and `from archview.model.names import last`, and:

```python
SOURCE_SUFFIXES = {
    "python": (".py",),
    "typescript": (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".json"),
}


def source_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Files to watch below `root`, skipping node_modules and hidden directories."""
    found: list[Path] = []
    for directory, subdirs, files in os.walk(root):
        subdirs[:] = [d for d in subdirs if d != "node_modules" and not d.startswith(".")]
        found.extend(Path(directory) / f for f in files if f.endswith(suffixes))
    return sorted(found)
```

- `__init__(self, repo: Path, package: str | None = None, config_path: Path | None = None, language: str | None = None, tsconfig: str | None = None)`: keep `self._args = (repo, package, config_path)` and add `self._options = {"language": language, "tsconfig": tsconfig}`; `reload` calls `open_project(*self._args, **self._options)`.
- `_signature`:
  ```python
      def _signature(self) -> tuple:
          project = self.project
          language = project.model.language
          root = project.repo if language == "typescript" else project.source_root / project.package
          files = source_files(root, SOURCE_SUFFIXES.get(language, (".py",)))
          extra = [p for p in (project.config_path, baseline_path(project)) if p and p.is_file()]
          return tuple((str(p), p.stat().st_mtime_ns) for p in (*files, *extra) if p.exists())
  ```
- `summary`: add `"language": project.model.language,` and `"separator": project.model.separator,` after `"repo"`.
- `tree.item`: `"name": last(node.id, model.separator),`.

In `src/archview/cli.py` `_serve`: `Workspace(args.path, args.package, args.config, args.language, args.tsconfig)`.

- [ ] **Step 4: Implement the UI changes**

In `src/archview/ui/app.js` replace the `short` and `parentOf` definitions with:

```js
const sep = () => state.project.separator;
const inProject = (id) => id === state.project.project || id.startsWith(state.project.project + sep());
const short = (id) => (inProject(id) ? id.split(sep()).pop() : id);
const parentOf = (id) => (inProject(id) && id.includes(sep()) ? id.slice(0, id.lastIndexOf(sep())) : null);
```

In `crumbs`: `const parts = root.split(sep());` and `const id = parts.slice(0, i + 1).join(sep());`.
In `exportView`: `const base = state.root.replaceAll(sep(), "-");`.
Then `grep -n 'split("\.")\|"\."' src/archview/ui/app.js` must print nothing that splits node ids.

- [ ] **Step 5: Run the tests and look at it**

Run: `uv run pytest -v && uv run ruff format && uv run ruff check && uv run archview check` → PASS.
Run: `uv run archview serve tests/fixtures/ts-sample --no-open --port 8799` in the background and open `http://127.0.0.1:8799/` in the browser (claude-in-chrome). Check: breadcrumbs read `ts-sample / domain`; drilling into `components` then `Transitions` shows `Transitions.tsx` and the `Transitions` package; the file drawer names end in `.tsx`; `@tanstack/react-query` shows its full name with externals on; the domain↔services cycle is red; the warnings list both warnings; a Python repo (`uv run archview serve . --no-open --port 8798`) still reads `archview / model`. Stop both servers.

- [ ] **Step 6: Commit**

```bash
git add src/archview/server src/archview/ui/app.js src/archview/cli.py tests/test_server.py
git commit   # "Viewer: TypeScript projects - separator in the API and UI, watching .ts files" + trailer
```

---

### Task 8: Accept on storygenerator

**Files:**
- Modify: whatever the run shows is wrong — each fix starts with a failing test (in `tests/test_extract_typescript.py` for model decisions, or a new fixture file plus a `tests/test_typescript_facts.py` case for resolution)

**Interfaces:**
- Consumes: everything above. Produces: no new interface.

- [ ] **Step 1: Run every command on the real repo**

`~/git/storygenerator` is read-only for this task; rules live in the scratchpad.

```bash
SG=~/git/storygenerator; RULES=$TMPDIR/sg-archview.toml
time uv run archview graph $SG
uv run archview graph $SG --externals | head -40
uv run archview init $SG --config $RULES && cat $RULES
uv run archview check $SG --config $RULES; echo "exit $?"
uv run archview metrics $SG --config $RULES
uv run archview why components utils $SG
uv run archview cycles $SG | head -40
uv run archview graph $SG --json | python3 -c "import json,sys; v=json.load(sys.stdin); print(len(v['nodes']), 'nodes', len(v['edges']), 'edges')"
```

Expected: every command exits 0 (`check` exits 0 right after `init`); `graph` finishes in seconds (A14); the components are the repo's top-level directories plus root files such as `i18n.ts`, and no `*.config.*` files; externals include `react-native`, `expo-router`, `@expo/vector-icons`.

- [ ] **Step 2: Check the warnings and resolution**

```bash
uv run python - <<'EOF'
from collections import Counter
from pathlib import Path
from archview.project import open_project
m = open_project(Path.home() / "git/storygenerator").model
print(Counter(w.kind for w in m.warnings))
for w in m.warnings[:15]:
    print(w.kind, w.file, w.line, w.target)
print(sum(1 for n in m.nodes if n.kind == "module"), "modules", len(m.imports), "imports")
EOF
```

Expected: few `unresolved_import` warnings, each a real problem in storygenerator (not a resolver miss); every `@/…` import of a `.ts`/`.tsx` file lands on an internal module. Any warning that is a resolver miss is a bug: reproduce it in the fixture with a failing test, fix, rerun.

- [ ] **Step 3: Remove one rule and see the check fail**

Delete one dependency from a component's list in `$RULES` (e.g. drop `"utils"` from `components`), run `uv run archview check $SG --config $RULES; echo "exit $?"`.
Expected: exit 1 with `file:line` of the offending imports and a hint.

- [ ] **Step 4: Look at it in the viewer**

`uv run archview serve $SG --config $RULES --no-open --port 8797` in the background; open it in the browser. Navigate top → `components` → a component directory → a file, with source. Note anything unreadable (too many nodes, barrels dominating, labels) for the user. Stop the server.

- [ ] **Step 5: Commit any fixes**

```bash
git add src tests
git commit   # "TypeScript: <what the storygenerator run found>" + trailer  (skip if nothing changed)
```

---

### Task 9: Docs, ADR and version

**Files:**
- Create: `docs/decisions/0010-typescript-extractor.md`
- Modify: `docs/02-requirements.md`, `docs/05-approach-and-roadmap.md`, `docs/06-using-archview-in-a-repo.md`, `AGENTS.md`, `pyproject.toml`, `uv.lock`, `README.md` (only if it says Python-only)

**Interfaces:** none.

- [ ] **Step 1: Write ADR 0010**

`docs/decisions/0010-typescript-extractor.md`:

```markdown
# 10. TypeScript through the compiler API; ids split by a model separator

Date: 2026-09-17 (M6)

## Status

Accepted.

## Context

M6 adds a second language. The frontend repo it is accepted on, `storygenerator`
(Expo / React Native), resolves 845 imports through a tsconfig `paths` alias and
extends `expo/tsconfig.base` from `node_modules`. Nine public repos (Next.js, Expo,
Vite, NestJS, ESM libraries, monorepos) added: solution-style tsconfigs (`files: []`
plus `references`), tsconfigs below the root, NodeNext `.js` specifiers, pnpm
workspaces, and file names with dots (`Button.web.tsx`, `x.service.spec.ts`) next to
directories of the same name. Everything above the extractor split ids on '.'.

## Decision

- **Parser.** `extract/typescript.mjs` runs in Node with the analysed repo's own
  `typescript` package and prints raw facts per file; `extract/typescript.py` builds
  the model. Resolution is tsc's own (`resolveModuleName`), as grimp's is for Python -
  no resolver of ours. tree-sitter would have meant writing one; dependency-cruiser
  would have meant an install and a translation.
- **No install, no fallback.** Without `typescript` in the repo: exit 2, "run npm install".
- **tsconfig.** Any config diagnostic is fatal: tsc otherwise falls back to default
  options when an `extends` target is missing and resolution quietly degrades (67%
  instead of 95% on one repo). `references` are followed, each file resolved with the
  options of the tsconfig that lists it. `tsconfig =` / `--tsconfig` picks another one;
  a monorepo is analysed one package at a time.
- **Ids keep the file extension and are split by '/'.** `Model.separator` ('.' for
  Python, '/' for TypeScript; schema 3) is used through `model/names.py` everywhere a
  name is split. No escaping, no clashes, and ids match the paths agents already use.
  A barrel `index.ts` is an ordinary child of its directory.
- **Internal vs external** by the real path of the resolved file (inside the repo, not
  under `node_modules`), not tsc's `isExternalLibraryImport`, which pnpm symlinks fool.
- **Source root.** The one top-level directory holding every file (`src/`), else the
  repo; root `*.config.*` files are build tooling and left out.
- **Flags.** `type_checking` means type-only (`import type`), `lazy` means `import()`
  or `require()` in a function; `unresolved_import` is a new warning for relative or
  in-repo alias specifiers tsc cannot resolve.

## Consequences

archview needs Node.js and an installed project to read TypeScript. The model JSON is
schema 3 for both languages. Rules files for TypeScript name components as the
directories and root files below the source root (`"i18n.ts" = [...]`), and
`[components]` patterns use '/'. A whole-workspace monorepo model, `.vue`/`.svelte`
files and a global TypeScript fallback are left for later.
```

- [ ] **Step 2: Update the other docs**

- `docs/02-requirements.md`: A13's Pri column becomes `MVP (design) / M6 (impl, ADR 0010)`; add after A14:
  `| A15 | TypeScript extractor: tsc's own resolution (paths, extends, references), ids that keep file extensions split by '/', type-only and lazy flags, unresolved-import warnings. Needs Node and the project's installed typescript. | M6 | LH |`
  In §12 add a paragraph: `M6 (2026-09-17): TypeScript through the compiler API (ADR 0010); accepted on storygenerator.` Update the title's "(Python first)" to "(Python and TypeScript)".
- `docs/05-approach-and-roadmap.md` M6 row: deliverable `TypeScript extractor through the TS compiler API (ADR 0010), same JSON (schema 3)`; done-when `Viewer/checker work unchanged on storygenerator (done 2026-09-17)`; name it `**M6 — second language** (done)`.
- `docs/06-using-archview-in-a-repo.md`: add a section `## TypeScript` after `## Install once`:
  ```markdown
  ## TypeScript

  A `tsconfig.json` at the repo root makes archview read TypeScript (or `language =
  "typescript"` / `--language typescript`). It needs Node.js on the PATH and the
  project's own dependencies installed (`npm install`): archview uses the repo's
  `typescript` package, so imports resolve exactly as `tsc` resolves them.

  - Another tsconfig: `tsconfig = "server/tsconfig.json"` or `--tsconfig`.
  - Monorepos: point archview at one package (`archview packages/core`).
  - Names are paths with their extension: `archview why components/ui utils`,
    `archview graph --root myapp/components`, `[archview.components]` patterns like
    `"myapp/features/**"`, and file components are quoted keys (`"i18n.ts" = []`).
  - `type_checking_imports` applies to `import type`.
  ```
- `AGENTS.md`: the state paragraph says M1–M6 are done and TypeScript is read through the compiler API (ADR 0010); "Python code bases first" in *Decisions already made* becomes "Python and TypeScript (M6, ADR 0010); the model JSON and everything above the extractors stay language-agnostic."; reading order item 3 mentions 0010; add to *Useful commands*:
  ```
  uv run archview graph ~/git/storygenerator         # TypeScript (needs node + npm install there)
  npm ci --prefix tests/fixtures/ts-sample           # once, for the TypeScript tests
  ```
- `README.md` and `pyproject.toml` `description`: "for Python and TypeScript code bases" where they say Python only.

- [ ] **Step 3: Version**

Set `version = "0.2.0"` in `pyproject.toml` (schema bump = minor), run `uv lock`, then `uv tool install --editable . --force`.

Run: `uv run pytest && uv run ruff format --check && uv run ruff check && uv run archview check` → PASS.

- [ ] **Step 4: Commit**

```bash
git add docs AGENTS.md README.md pyproject.toml uv.lock
git commit   # "M6 docs: ADR 0010, requirements, roadmap and usage for TypeScript; version 0.2.0" + trailer
```

Tagging, pushing and the release wait for the user.
