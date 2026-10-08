# M12 implementation plan: rules for sub-packages

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An `archview.toml` inside a package holds rules between that package's children, and `check`, `init --root`, `serve` and baselines all handle it (issue #14).

**Architecture:** Each nested file is a scope. `check` cuts the model down to the scope (`scoped_model`) and runs the unchanged `check()` on it with the nested `Config`. The root `Report` carries the scope reports in a new `scopes` field, so every consumer of `project_report` (CLI, Stop hook, workspace sections, server) sees them.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `ruff`, grimp; plain JavaScript in `src/archview/ui/app.js`.

**Spec:** `docs/superpowers/specs/2026-10-08-nested-rules-design.md`. Read it alongside this plan; section numbers below (§1 to §8) refer to it.

## Global Constraints

- Python 3.12+; `from __future__ import annotations` at the top of every module; modern hints (`str | None`).
- Before every commit all four pass: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check .`, `uv run archview check`.
- Deterministic output: sort by name wherever there is a tie. Scopes are sorted by scope id.
- `tests/test_self_check.py` asserts zero warnings on this repo. This repo has no nested files, so nothing here may add a warning to it.
- This repo's own rules: `rules` may import `model` only; `project` may import `extract`, `model`, `rules`; `render` may import `model`, `rules`; `server` may import `model`, `project`, `render`, `rules`, `workspace`. No new top-level component. Never edit `archview.toml` to make a check pass.
- Golden files: regenerate with `UPDATE_GOLDEN=1 uv run pytest`, then read the diff and account for every changed line.
- When there are no nested files, `check`'s text output is byte-identical to today; JSON gains only `"scopes": []`.
- Nested-file keys (§1): allowed `allowed`, `forbidden`, `layers`, `independent`, `exceptions`, `components`, `ignored`, `fail_on_violations`, `fail_on_cycles`, `metrics`, `baseline`; root-only `package`, `language`, `tsconfig`, `source_roots`, `exclude`, `type_checking_imports`, `externals`, `externals_undeclared`, `public`, `workspace`.
- New notice kind: `unchecked_rules_file`. A dead nested `forbidden` target reuses `unknown_component`.
- Prose (docstrings, docs, ADR): follow the `unslop` skill; no em dashes.
- Small functions, complexity at most 5 where practical.
- Commit messages: imperative mood, no `feat:`/`fix:` prefixes, ending with:

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018Zw6RJCWo1hctPRwDqGMh3
```

## Review Focus

1. Root package excluded by the root's `exclude` but holding a nested file: the file must get `unchecked_rules_file`, not be checked against an empty model. Test in Task 4.
2. Root rules given with `--config` outside the repo (the dogfood path): showing paths must not crash `relative_to`, and a file in the package directory still gets its notice. Test in Task 4.
3. A nested file that is not valid TOML, or sets a root-only key: exit 2, and the message names `shop/services/archview.toml`, not `archview.toml`. Test in Task 2 (unit) and Task 5 (CLI exit code).
4. `serve --watch` when a nested file is added after start: the page must reload. Test in Task 8.
5. A TypeScript project whose source root is the repo: `node_modules` and hidden directories are not walked, and the root `archview.toml` in the package directory gets no notice. Test in Task 4.

## File structure

| File | Change |
|---|---|
| `src/archview/model/filter.py` | `scoped_model` |
| `src/archview/model/names.py` | `stripped_source_root`, moved from `rules/init.py`'s `_inferred_source_roots` |
| `src/archview/rules/config.py` | nested key sets, `parse_nested_config`, `load_nested_config` |
| `src/archview/rules/check.py` | `Report.scopes`, `Report.failing`, `Report.failed` covers scopes |
| `src/archview/rules/scopes.py` (new) | `check_scope`: `check()` on the scoped model, plus the dead-`forbidden` notice |
| `src/archview/project.py` | `Scope`, `package_dir`, `scope_dir`, `nested_scopes`, scope baselines, `project_report` attaches scopes, `fresh_baselines` |
| `src/archview/rules/overlay.py` | `failing_imports` includes scopes |
| `src/archview/render/check.py`, `render/workspace.py` | scope sections, total line, `"scopes"` in JSON |
| `src/archview/rules/init.py` | `infer_scope_rules` |
| `src/archview/cli.py` | `init --root`, `--update-baseline` per scope |
| `src/archview/server/state.py`, `ui/app.js` | failing counts, watch signature, check panel |
| `tests/fixtures/nested/` (new) | the Python fixture |
| docs | ADR 0016, C17, M12, docs/06 recipe, AGENTS.md |

---

### Task 1: `scoped_model` and `stripped_source_root`

**Files:**
- Modify: `src/archview/model/filter.py`, `src/archview/model/names.py`, `src/archview/rules/init.py`
- Test: `tests/test_filter.py`, `tests/test_names.py`

**Interfaces:**
- Produces: `scoped_model(model: Model, scope: str) -> Model` in `model/filter.py`.
- Produces: `stripped_source_root(model: Model) -> str | None` in `model/names.py`: the directory (POSIX, relative to the repo) the TypeScript extractor stripped from the ids; `""` when the ids start at the repo; `None` for Python or when files disagree. Same algorithm as today's `_inferred_source_roots` in `rules/init.py`.

- [ ] **Step 1: Write the failing tests** in `tests/test_filter.py`, using `tests.builders.model`:

```python
def test_scoped_model_keeps_the_scope_and_the_imports_inside_it():
    m = model(
        ("app.svc.a.x", "app.svc.b.y"),   # inside
        ("app.svc.a.x", "app.models.m"),  # leaves the scope
        ("app.api.r", "app.svc.a.x"),     # enters the scope
    )
    s = scoped_model(m, "app.svc")
    assert s.project == "app.svc"
    assert {n.id for n in s.nodes} == {"app.svc", "app.svc.a", "app.svc.a.x", "app.svc.b", "app.svc.b.y"}
    assert [(i.importer, i.imported) for i in s.imports] == [("app.svc.a.x", "app.svc.b.y")]
    assert next(n for n in s.nodes if n.id == "app.svc").parent is None

def test_scoped_model_drops_externals_and_extraction_warnings():
    # model_with_external(): shop.llm imports openai; give the model one ExtractionWarning
    # in shop.llm; scoped_model(m, "shop") has no external node and no warnings
```

In `tests/test_names.py`, a TypeScript model built with `model(..., sep="/")` whose module files carry a `src/` prefix returns `"src"`, and a Python model returns `None`. Build the nodes by hand where `builders.model` cannot set the prefix.

- [ ] **Step 2: Run** `uv run pytest tests/test_filter.py tests/test_names.py -q`. Expected: ImportError on `scoped_model` and `stripped_source_root`.

- [ ] **Step 3: Implement both.** `scoped_model` uses `within` and `replace`; it keeps no external node, keeps an import only when both ends are within the scope, sets the scope node's `parent` to `None`, and empties `warnings`. Move the body of `_inferred_source_roots` into `stripped_source_root`. Change it to return `str | None` and take the docstring with it. `infer_rules` then writes `source_roots` from `config.source_roots or ((root,) if (root := stripped_source_root(model)) else ())`.

- [ ] **Step 4: Run** the full suite. Expected: all pass, `sample-archview.toml` golden and the TS init tests unchanged.

- [ ] **Step 5: Commit** "Add scoped_model, and move the stripped source root into the model".

---

### Task 2: the nested rules schema

**Files:**
- Modify: `src/archview/rules/config.py`
- Test: `tests/test_rules_config.py`

**Interfaces:**
- Produces: `NESTED_KEYS: frozenset[str]` and `ROOT_ONLY_KEYS = frozenset(TOP_KEYS) - NESTED_KEYS`.
- Produces: `parse_nested_config(table: dict[str, Any], root: Config, shown: str, scope: str, where: str = "archview") -> Config`. `shown` is the file's path as displayed (relative to the repo), and `scope` is the scope id used in the message.
- Produces: `load_nested_config(path: Path, root: Config, shown: str, scope: str) -> Config`. It reads `[archview]` from `path` and raises `ConfigError` with `shown` as the prefix for unreadable files, invalid TOML and a missing table.

- [ ] **Step 1: Write the failing tests:**

```python
ROOT = Config(type_checking_imports="ignore", exclude=("**/gen/**",))

def test_a_nested_file_takes_the_rule_keys_and_inherits_the_model_keys():
    c = parse_nested_config({"allowed": {"print": ["pricing"]}, "fail_on_cycles": False},
                            ROOT, "shop/services/archview.toml", "shop.services")
    assert c.allowed == {"print": ("pricing",)}
    assert (c.type_checking_imports, c.exclude, c.fail_on_cycles) == ("ignore", ("**/gen/**",), False)
    assert c.path == "shop/services/archview.toml"

@pytest.mark.parametrize("key", sorted(ROOT_ONLY_KEYS))
def test_a_nested_file_rejects_every_root_only_key(key):
    with pytest.raises(ConfigError, match=rf"^shop/services/archview\.toml: \[archview\] {key} belongs in the root rules file"):
        parse_nested_config({key: ...}, ROOT, "shop/services/archview.toml", "shop.services")

def test_a_nested_typo_still_gets_a_suggestion():  # "alowed" -> "did you mean 'allowed'"

def test_load_nested_config_names_the_file_by_its_shown_path(tmp_path):
    # write "[archview\n" (invalid TOML) -> ConfigError starting "shop/services/archview.toml: not valid TOML"
```

Pick a valid value per key for the parametrised test (a string, list or table as the key expects). The rejection must fire before value validation, so the simplest valid value for each key works.

- [ ] **Step 2: Run** `uv run pytest tests/test_rules_config.py -q`. Expected: ImportError.

- [ ] **Step 3: Implement.** First reject root-only keys present in `table`, in sorted order. The message is exact copy from §1: `f"{shown}: [{where}] {key} belongs in the root rules file; a nested file holds rules between the children of {scope}"`. Then call `parse_config(table, where, shown)`, wrapping its `ConfigError` so the message gains the `f"{shown}: "` prefix. Finally `replace(...)` with `type_checking_imports` and `exclude` from `root`. `load_nested_config` reuses `_read_toml`'s logic, with `shown` in place of `path.name`.

- [ ] **Step 4: Run** the full suite. Expected: all pass.

- [ ] **Step 5: Commit** "Parse a nested rules file: rule keys only, model keys from the root".

---

### Task 3: checking one scope

**Files:**
- Create: `src/archview/rules/scopes.py`
- Modify: `src/archview/rules/check.py` (`Report`)
- Test: `tests/test_rules_scopes.py` (new)

**Interfaces:**
- Consumes: `scoped_model` (Task 1).
- Produces: `Report.scopes: tuple[tuple[str, Report], ...] = ()`, holding (rules path as shown, scope report). Also `Report.failing -> int`, the failing problems here plus every scope's, and `Report.failed`, which is now `self.failing > 0`.
- Produces: `check_scope(model: Model, scope: str, config: Config, in_workspace: bool = False) -> Report` in `rules/scopes.py`.

- [ ] **Step 1: Write the failing tests** with `tests.builders.model`:

```python
M = model(
    ("app.svc.print.flow", "app.svc.pricing.price"),
    ("app.svc.print.flow", "app.svc.users.repo"),
    ("app.svc.print.flow", "app.models.order"),
    ("app.api.routes", "app.svc.print.flow"),
)

def test_a_scope_checks_the_children_of_its_package():
    r = check_scope(M, "app.svc", Config(allowed={"print": ("pricing",), "pricing": (), "users": ()}))
    assert r.project == "app.svc"
    assert r.components == ("pricing", "print", "users")
    assert [(p.kind, p.components) for p in r.problems] == [("not_allowed", ("print", "users"))]

def test_a_new_child_missing_from_allowed_is_undeclared(): ...      # allowed lacks "users"
def test_a_cycle_inside_the_scope_is_found(): ...                   # add users -> print
def test_an_exception_names_modules_by_their_full_name(): ...       # Exemption("app.svc.print.**", "app.svc.users.**", "legacy")
def test_a_forbidden_target_outside_the_scope_is_a_dead_rule():
    allowed = {"print": ("pricing", "users"), "pricing": (), "users": ()}
    r = check_scope(M, "app.svc", Config(allowed=allowed, forbidden=(Forbidden("print", "openai"),)))
    assert Notice("unknown_component",
        "[archview.forbidden] names 'openai', which is not a child of app.svc; "
        "imports that leave a nested scope are checked by the rules above it") in r.warnings

def test_a_report_fails_when_a_scope_fails():
    inner = check_scope(M, "app.svc", Config(allowed={"print": (), "pricing": (), "users": ()}))
    outer = Report("app", ("svc",), (), (), scopes=(("app/svc/archview.toml", inner),))
    assert outer.failed and outer.failing == 2
```

- [ ] **Step 2: Run** `uv run pytest tests/test_rules_scopes.py -q`. Expected: ImportError.

- [ ] **Step 3: Implement.** Add the `Report` fields. `check_scope` returns `check(scoped_model(model, scope), config, in_workspace)` with the extra notices appended to `warnings`. Only literal `forbidden` entries (`origin == "forbidden"`) whose target is not in the report's components get a notice, worded exactly as the test.

- [ ] **Step 4: Run** the full suite. Expected: all pass; existing `Report(...)` constructions are unaffected by the defaulted field.

- [ ] **Step 5: Commit** "Check a scope with check() on the model cut down to it".

---

### Task 4: discovery, and scopes in `project_report`

**Files:**
- Create: `tests/fixtures/nested/` (below)
- Modify: `src/archview/project.py`
- Test: `tests/test_project.py`, `tests/test_typescript_project.py`

**Interfaces:**
- Consumes: `load_nested_config` (Task 2), `check_scope` and `Report.scopes` (Task 3), `stripped_source_root` (Task 1).
- Produces, in `project.py`:
  - `Scope` (frozen, slots) with `id: str`, `rules: Path` (absolute), `shown: str` (POSIX path relative to `project.repo`), `config: Config`.
  - `package_dir(project: Project) -> Path`: Python `project.source_root / project.package`; TypeScript `project.repo / (project.config.source_roots[0] if set else stripped_source_root(model) or "")`.
  - `scope_dir(project: Project, scope: str) -> Path`: the inverse mapping.
  - `nested_scopes(project: Project) -> tuple[tuple[Scope, ...], tuple[Notice, ...]]`: the scopes sorted by id, plus the `unchecked_rules_file` notices.
  - `scope_baseline_path(scope: Scope) -> Path`: `scope.rules.parent / (scope.config.baseline or BASELINE_FILE)`.
  - `project_report(project, in_workspace=False)` now adds the notices to the root's warnings and fills `scopes` with `(scope.shown, report)`, where each report has its own baseline applied. A configured baseline that is missing is a `ConfigError`, as at the root.

The fixture, every package with an `__init__.py`:

```
tests/fixtures/nested/archview.toml          [archview] package = "shop"
                                              [archview.allowed] api = ["services"], models = [], services = ["models"]
shop/api/routes.py                            from shop.services.print import flow
shop/models/order.py                          class Order: ...
shop/services/archview.toml                   [archview.allowed] print = ["pricing"], pricing = [], users = []
shop/services/print/flow.py                   from shop.services.pricing import price
                                              from shop.services.users import repo   (line 2: the scope violation)
                                              from shop.models import order
shop/services/pricing/price.py                from shop.models import order
shop/services/users/repo.py                   VALUE = 1
shop/services/assets/archview.toml            (no Python here: the orphan)
```

The root passes; the scope has one `not_allowed` (`print -> users`); the root report has one `unchecked_rules_file` notice:
`"shop/services/assets/archview.toml is not checked: shop.services.assets is not a package archview analyses (excluded, or not a package)"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_project.py`, against a `tmp_path` copy of the fixture:
  - `project_report` on the fixture: `report.scopes[0][0] == "shop/services/archview.toml"`, the scope's problem is as above, the notice is the root's only warning, and `report.failed`.
  - `scope_dir(project, "shop.services") == package_dir(project) / "services"`.
  - A `shop/archview.toml` in the package directory gets `"shop/archview.toml is not checked: the rules for shop are read from archview.toml"`.
  - Review Focus 1: root `exclude = ["shop/services/**"]` turns the services file into an `unchecked_rules_file`, and the report has no scopes.
  - Review Focus 2: `open_project(copy, config_path=<rules file in another tmp dir>)` shows the rules path in full in that notice and does not raise.
  - A nested baseline: write `shop/services/archview-baseline.json` with `baseline_of` of the scope report; the scope then passes with `baselined == 1`. A nested `baseline = "missing.json"` raises `ConfigError`.

  In `tests/test_typescript_project.py` (`@requires_typescript`, the symlinked `node_modules` pattern of `test_init_pins_the_inferred_source_root_of_a_src_layout_project`):
  - src layout: `src/feat/a/x.ts` imports `src/feat/b/y.ts`, `src/feat/archview.toml` allows `a = []`, `b = []`, so the scope `proj/feat` reports `a -> b`.
  - Review Focus 5: the source root is the repo (`tsconfig.json` with `"include": ["api", "core"]`). The root `archview.toml` gets no notice, and an `archview.toml` under `node_modules/x/` or `.cache/` is never found.

- [ ] **Step 2: Run** `uv run pytest tests/test_project.py tests/test_typescript_project.py -q`. Expected: ImportError on `nested_scopes`.

- [ ] **Step 3: Implement.** Walk with `os.walk(package_dir)`, pruning `node_modules` and dot directories as `server/state.py`'s `source_files` does, and sort the results. A directory strictly below `package_dir` maps to `model.project + sep + sep.join(parts)`. It is a scope when the model has a `"package"` node with that id; otherwise it gets the orphan notice. A file directly in `package_dir` is skipped when it resolves to `project.config_path`; otherwise it gets the second notice. Show paths relative to `project.repo`, or in full when they are not below it. Load each scope's config with `load_nested_config(path, project.config, shown, scope_id)`.

- [ ] **Step 4: Run** the full suite. Expected: all pass, self-check still zero warnings.

- [ ] **Step 5: Commit** "Find nested rules files and check each scope in project_report".

---

### Task 5: output, text and JSON

**Files:**
- Modify: `src/archview/render/check.py`, `src/archview/render/workspace.py`
- Create: `tests/golden/nested-check.txt`, `tests/golden/nested-check.json`
- Test: `tests/test_cli_check.py`, `tests/test_cli_workspace.py`, `tests/test_render_check.py`

**Interfaces:**
- Consumes: `Report.scopes`, `Report.failing` (Task 3); the fixture (Task 4).
- Produces: `report_to_dict` adds `"scopes": [{"rules": shown, **report_to_dict(scope)}]` as the last key; `"ok"` is `not report.failed`. `report_to_text` prints the scope sections and the new total (§4).

- [ ] **Step 1: Write the failing tests.**
  - `test_check_reports_each_nested_scope_in_its_own_section` (CLI, tmp copy of `nested`): exit 1, output equals golden `nested-check.txt`, and it contains:
    ```
    warning: shop/services/assets/archview.toml is not checked: shop.services.assets is not a package archview analyses (excluded, or not a package)
    shop.services (shop/services/archview.toml)  1 problem
      VIOLATION print -> users (1 import) not allowed by [archview.allowed.print]
    1 problem in 3 components and 1 nested scope. exit 1
    ```
  - The same with `--format json` against `nested-check.json`; `ok` is false, `scopes[0].rules == "shop/services/archview.toml"`, `scopes[0].project == "shop.services"`.
  - With the nested file's `print` changed to `["pricing", "users"]`, the last line is `ok: shop, 3 components and 1 nested scope, no failing problems` and the scope header ends with `  ok`.
  - Review Focus 3: invalid TOML in the nested file makes `check` exit 2, and stderr contains `shop/services/archview.toml: not valid TOML`.
  - Workspace (`tests/test_cli_workspace.py`, tmp copy of `tests/fixtures/workspace`): add `core/src/core/engine/{__init__,a/__init__,a/x,b/__init__,b/y}.py` with `x` importing `core.engine.b.y`, `engine/archview.toml` allowing `a = []` and `b = []`, and `engine = []` in core's `allowed`. Then `check --format json` at the root shows `packages[0].scopes[0].project == "core.engine"` with one failing problem, the workspace `ok` is false, and the text output has the scope section inside core's.

- [ ] **Step 2: Run** them. Expected: FAIL (no scopes in output).

- [ ] **Step 3: Implement.** A scope section has a header of `f"{scope.project} ({shown})  {status}"`, painted red when failing, where status is `ok` or the plural problem count. Its body is `report_to_text(scope)` minus its last line, indented two spaces, as `render/workspace.py`'s `_section` builds one. The total line puts `f" and {plural(n, 'nested scope')}"` after the component count when there are scopes. Failing and known-in-baseline counts are summed over the root and its scopes. `render/workspace.py`'s `_failing` becomes `report.failing`.

- [ ] **Step 4: Run** `UPDATE_GOLDEN=1 uv run pytest`, then `git diff tests/golden`. Expected: the two new files, and `sample-check.json` gains only `"scopes": []`. Run `uv run pytest` again: all pass.

- [ ] **Step 5: Commit** "Report nested scopes in check's text and JSON output".

---

### Task 6: `--update-baseline` per scope

**Files:**
- Modify: `src/archview/project.py`, `src/archview/cli.py` (`_check`, `_update_workspace_baseline`)
- Test: `tests/test_cli_check.py`, `tests/test_cli_workspace.py`

**Interfaces:**
- Consumes: `nested_scopes`, `scope_baseline_path`, `check_scope`.
- Produces: `fresh_baselines(project: Project) -> list[tuple[Path, Baseline]]` in `project.py`: the root `(baseline_path(project), baseline_of(check(model, config)))` first, then one entry per scope in scope order, each from that scope's unbaselined `check_scope`.

- [ ] **Step 1: Write the failing tests.** `check --update-baseline` on the `nested` copy prints two `wrote ...` lines, the second for `shop/services/archview-baseline.json (1 known problems)`, and a following `check` exits 0 with the scope problem shown as `known:`. The workspace engine setup from Task 5 writes `core/src/core/engine/archview-baseline.json`.

- [ ] **Step 2: Run** them. Expected: FAIL, no scope baseline written.

- [ ] **Step 3: Implement** `fresh_baselines`; both CLI paths write every entry with the existing `_write_baseline`.

- [ ] **Step 4: Run** the full suite. Expected: all pass.

- [ ] **Step 5: Commit** "Write a baseline per nested scope with --update-baseline".

---

### Task 7: `archview init --root`

**Files:**
- Modify: `src/archview/rules/init.py`, `src/archview/cli.py` (`_init`, the `init` parser)
- Test: `tests/test_cli_check.py`, `tests/test_rules_check.py`

**Interfaces:**
- Consumes: `scoped_model`, `scope_dir`, `load_nested_config`, `resolve` (`model/query.py`).
- Produces: `infer_scope_rules(model: Model, scope: str, config: Config) -> str` in `rules/init.py`. `model` is the full model and `config` the nested config (inherited keys set). It returns the file text in §6: the header comment with the scope id, `[archview]` with `ignored` if set, the fail flags or the cycle comment, `[archview.allowed]`, and `[archview.components]` if set. It shares the allowed and components line builders with `infer_rules`.
- Produces: `init --root NAME`.

- [ ] **Step 1: Write the failing tests.**
  - Unit: `infer_scope_rules(M, "app.svc", Config())` (Task 3's `M`) contains `print = ["pricing", "users"]`, `pricing = []`, `users = []`, starts with `# Dependency rules between the children of app.svc,`, and has no `package =` line.
  - CLI on the `nested` copy, after deleting `shop/services/archview.toml`: `init --root services` writes it, prints `wrote .../shop/services/archview.toml`, and `check` then exits 0.
  - A second `init --root services` exits 2 with `--force` in stderr. With `--force`, a `[archview.components]` table in the file survives.
  - Exit 2 for `--root services.print.flow` (a module), `--root shop` (the project), and `--root services` combined with any of `--externals`, `--config x.toml` or `--exclude x`.
  - Issue #13's lesson: root `type_checking_imports = "ignore"` plus `shop/services/pricing/types.py` holding a `TYPE_CHECKING` import of `shop.services.users.repo`. Then `init --root services --force` and `check` exits 0.

- [ ] **Step 2: Run** them. Expected: FAIL (`--root` unknown to `init`).

- [ ] **Step 3: Implement.** In `_init`, when `args.root` is set: reject the root-only flags, open the project with the root config (as today), `resolve` the name, and require a `"package"` node other than the project. The target is `scope_dir(project, id) / RULES_FILE`. With `--force`, keep `components` and `ignored` from `load_nested_config` of the existing file. Write or print as the root path does.

- [ ] **Step 4: Run** the full suite. Expected: all pass.

- [ ] **Step 5: Commit** "Infer a nested rules file with init --root".

---

### Task 8: `serve`

**Files:**
- Modify: `src/archview/rules/overlay.py`, `src/archview/server/state.py`, `src/archview/ui/app.js`
- Test: `tests/test_server.py`, `tests/test_render_check.py` (or wherever `failing_imports` is tested)

**Interfaces:**
- Consumes: `Report.scopes`, `Report.failing`, `nested_scopes`, `scope_baseline_path`.
- Produces: `failing_imports(report)` includes the failing imports of every scope. The summary's `failing` uses `report.failing` (project and workspace summaries). `_project_signature` adds every `archview.toml` found under `package_dir(project)` and each scope's baseline file when it exists.

- [ ] **Step 1: Write the failing tests** (server tests use a `nested` copy and `client_for`):
  - `/api/project` reports `failing == 1`.
  - `/api/view?root=shop.services` marks the `shop.services.print -> shop.services.users` edge `violation: true`, and `pricing` is not marked. Read an existing view test for the exact query parameters.
  - `/api/check` has `scopes[0].project == "shop.services"`.
  - Review Focus 4: `ViewerState` built on the copy has one signature, `shop/api/archview.toml` is then written, and `_signature()` differs.

- [ ] **Step 2: Run** them. Expected: FAIL.

- [ ] **Step 3: Implement** the three Python changes. In `app.js`'s `openRules`, the heading counts the failing problems of the root and every scope. After the root's cards, unused allowances and warnings, each scope renders an `<h3>` with its `project`, a `.sub` line with `rules` and its component count, and then its own cards, unused allowances and warnings. Click handlers index into one flat array of every problem shown, so `data-p` stays unique across sections.

- [ ] **Step 4: Run** the full suite, then the viewer on the fixture: `uv run archview serve tests/fixtures/nested --no-open`. In the browser, drill into `services` (red edge `print -> users`) and open the rules panel (a `shop.services` section). Use the `run` skill or Claude in Chrome to take a screenshot.

- [ ] **Step 5: Commit** "Show nested scopes' problems in the viewer".

---

### Task 9: docs, and dogfood

**Files:**
- Create: `docs/decisions/0016-nested-rules-files.md`
- Modify: `docs/02-requirements.md` (C17; the Checker row at the bottom becomes `C1–C4, C6–C17`), `docs/05-approach-and-roadmap.md` (M12 row, rules-file sketch mentions nested files), `docs/06-using-archview-in-a-repo.md` (a "Rules inside a sub-package" recipe), `AGENTS.md` (state line: M1–M12, ADR list to 0016), spec status line to "implemented".

- [ ] **Step 1: Dogfood.** Run `uv run archview init ~/git/tiny-tale-backend --root src.webapp.services --stdout` and keep the output out of that repo. Then copy it to `src/webapp/services/archview.toml` there, run `uv run archview check ~/git/tiny-tale-backend`, and delete the file again. Expected: exit 0 with a `src.webapp.services` section and no false `webapp` cycle. Record the component count and the run time for the ADR.

- [ ] **Step 2: Write the docs.** ADR 0016 follows the shape of 0014 and 0015: context (issue #14, the 27 patterns), decision (spec §1 to §7 in short form), the rejected approaches, and consequences, including what is not in this milestone. C17's wording is the spec's summary. The docs/06 recipe uses the dogfood output as its example. Apply the `unslop` skill to every new paragraph.

- [ ] **Step 3: Run** all four checks. Expected: pass.

- [ ] **Step 4: Commit** "M12: ADR 0016 and docs".
