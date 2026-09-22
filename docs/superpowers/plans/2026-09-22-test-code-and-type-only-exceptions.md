# M11 — Test code under the rules, and type-only exceptions: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the second halves of GitHub issues #8 and #10 — let a rule reach test code, and let an exception be scoped to type-only imports.

**Architecture:** Two independent features. The larger one builds the grimp graph over the analysed package *plus* every other top-level package under a configured source root, the same multi-package call M9 already proved in `extract/siblings.py`, and threads "which top-level names are internal" through `_is_internal` and `ComponentMap`. The smaller one adds an optional `kind` to `[[archview.exceptions]]`.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `ruff`, grimp.

**Spec:** `docs/superpowers/specs/2026-09-22-test-code-and-type-only-exceptions-design.md` — read it alongside this plan, especially its "The mechanism, and what it rules out" section.

## Global Constraints

- Python 3.12+; `from __future__ import annotations` at the top of every module; modern type hints (`str | None`).
- Before every commit all four must pass: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check .`, `uv run archview check`.
- **Deterministic output (N1):** byte-identical output for identical input; sort by name wherever there is a tie. Extra internal roots must be processed in sorted order.
- **`tests/test_self_check.py` asserts zero warnings on this repo.** archview's own `archview.toml` sets no `source_roots`, so Task 1 must not change its behaviour at all. If it does, that is a finding — report it, do not weaken the assertion.
- **Backwards compatibility:** a repo with a single source root, or none configured, must produce byte-identical output. The golden files are the guard; if one moves for Task 1, stop and report it, because nothing about single-root analysis should change.
- Never edit `archview.toml` to make a check pass.
- Small functions; complexity ≤ 5 where practical.
- Do **not** bump the version. M11 ships under 0.4.0, already on `main` untagged.
- Commit messages: imperative mood, no `feat:`/`fix:` prefixes. End every commit message with:

```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW
```

## File Structure

| File | Responsibility after this plan |
|---|---|
| `src/archview/extract/python.py` | `build_model` takes extra internal roots; `_is_internal` takes a set |
| `src/archview/project.py` | `open_project` discovers extra top-level packages per configured root |
| `src/archview/rules/components.py` | `ComponentMap` knows the extra roots; each is its own component |
| `src/archview/rules/config.py` | `Exemption.kind`; validation |
| `src/archview/rules/check.py` | `_exemption` honours `kind` |

Task 2 (the exception `kind`) touches none of Task 1's files, so the two are independent.

---

## Task 1: extra source roots contribute components

**Files:**
- Modify: `src/archview/extract/python.py` (`build_model`, `_is_internal`, `_kind`, `_source_file`)
- Modify: `src/archview/project.py` (`open_project`, `_packages`)
- Modify: `src/archview/rules/components.py` (`ComponentMap`)
- Test: `tests/test_extract_python.py` (or wherever `build_model` is tested — find it), `tests/test_project.py`, `tests/test_rules_check.py`

**Interfaces:**
- Produces: `build_model(package, source_root, relative_to=None, extra=())`, where `extra` is a sorted tuple of `(name, root)` pairs for other top-level packages that must be graphed alongside.
- Produces: `ComponentMap` gains `extra_roots: frozenset[str] = frozenset()`. A module under one of those names is internal, and its component **is that name**.

**Read first:** `src/archview/extract/siblings.py`. It already builds a grimp graph over several packages with several roots on `sys.path`, which is exactly the call this task needs. Reuse its shape; do not invent a second way.

The mechanism, restated from the spec so you need not open it:

- `open_project` scans each configured source root for top-level packages, which `_packages` already does. The chosen one stays `Model.project`; the others are extra internal roots.
- `grimp.build_graph(package, *extras)` resolves them together.
- **Only packages count, not loose modules.** A bare `.py` directly under a root contributes nothing, because grimp graphs packages and there is nothing to name.
- Each extra root package is **one component named after itself** — `tests.test_live` belongs to component `tests` — exactly as the project's own root module is a component named after the project (ADR 0006).

- [ ] **Step 1: Write the failing tests**

```python
def _repo(tmp_path, roots: str) -> Path:
    """A src/-layout package beside a tests/ package, with `roots` as source_roots."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "api.py").write_text("x = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_api.py").write_text("from pkg import api\n")
    (tmp_path / "archview.toml").write_text(
        f'[archview]\npackage = "pkg"\nsource_roots = {roots}\n'
        "[archview.allowed]\napi = []\ntests = [\"api\"]\n"
    )
    return tmp_path


def test_a_package_under_another_root_becomes_a_component(tmp_path):
    """issue #10: with `package` scoping, nothing outside src/<pkg>/ could be a component,
    so no rule could reach a test file."""
    report = project_report(open_project(_repo(tmp_path, '["src", "."]')))
    assert "tests" in report.components
    assert not report.failed


def test_a_rule_reaches_test_code(tmp_path):
    root = _repo(tmp_path, '["src", "."]')
    (root / "archview.toml").write_text(
        '[archview]\npackage = "pkg"\nsource_roots = ["src", "."]\n'
        "[archview.allowed]\napi = []\ntests = []\n"
    )
    report = project_report(open_project(root))
    assert [(p.kind, p.components) for p in report.problems if p.fails] == [
        ("not_allowed", ("tests", "api"))
    ]


def test_the_wrong_spelling_contributes_nothing_and_still_warns(tmp_path):
    """`tests/` is a package rooted at the repo, not at `tests/`. The issue used this
    spelling and got silence; M10 made it warn and this milestone keeps it warning."""
    report = project_report(open_project(_repo(tmp_path, '["src", "tests"]')))
    assert "tests" not in report.components
    assert [w.kind for w in report.warnings if w.kind == "empty_source_root"] == [
        "empty_source_root"
    ]


def test_a_loose_module_under_a_root_contributes_nothing(tmp_path):
    """Only packages count - grimp graphs packages, and a bare file has nothing to name."""
    root = _repo(tmp_path, '["src", "."]')
    (root / "stray.py").write_text("y = 1\n")
    report = project_report(open_project(root))
    assert "stray" not in report.components


def test_a_single_root_repo_is_unchanged(tmp_path):
    """Nothing about single-root analysis may move."""
    root = _repo(tmp_path, '["src"]')
    report = project_report(open_project(root))
    assert report.components == ("api",)
```

Read `tests/test_project.py` first and match how it builds repos; if a helper like `_repo` already exists there, reuse it rather than adding a second.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_project.py -v -k "another_root or reaches_test_code or wrong_spelling or loose_module or single_root_repo"`
Expected: the first two FAIL (`tests` is treated as an outside name, so it is not a component); the last three may already pass and are the controls that must keep passing.

- [ ] **Step 3: Implement**

Work outward from the extractor:

1. `_is_internal(module, package)` becomes `_is_internal(module, roots)` over a set of top-level names. Every call site in `python.py` passes the set.
2. `build_model` gains `extra: tuple[tuple[str, Path], ...] = ()`. Put every root on `sys.path` for the extraction (see `siblings._importable`, which already does this for several roots), call `grimp.build_graph(package, *sorted(names))`, and compute each module's `file` against the root it came from.
3. `Node.parent` for an extra root's top-level module is `None`, exactly as the project root's is.
4. `project.py`: `open_project` collects the extra packages per configured root and passes them through. The analysed package is chosen as today.
5. `components.py`: `ComponentMap` gains `extra_roots`. In `_default`, a module whose first segment is in `extra_roots` returns that segment; the existing project-relative logic is unchanged.

Keep `Model.project` as the analysed package. Nothing about the project's identity changes.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`

**No golden file should move.** Every fixture uses a single root, and single-root behaviour is unchanged. If a golden moves, stop and report it rather than regenerating.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Let a package under another source root be a component

With \`package\` scoping, nothing outside src/<pkg>/ could be a component,
so no rule could reach a test file (issue #10). The graph is now built
over the analysed package plus every other top-level package under a
configured root - the multi-package grimp call M9 proved for siblings.

Only packages count: a bare module under a root has nothing to name.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 2: an exception scoped to type-only imports

**Files:**
- Modify: `src/archview/rules/config.py` (`Exemption`, `_exceptions`)
- Modify: `src/archview/rules/check.py` (`_exemption`)
- Test: `tests/test_rules_config.py`, `tests/test_rules_depth.py`, `tests/test_workspace.py`

**Interfaces:**
- Produces: `Exemption` gains `kind: str | None = None`. `_exemption` exempts an import only when `kind` is absent, or is `"type_only"` and the import's `type_checking` flag is set.

M10 flipped `type_checking_imports` to `"include"`, so type-only edges are now checked — which is what creates this need. The reporter's design says `screens -> ui`, and type-only imports from `api` are fine: a screen may name the shape of a prop it receives but must never call the API itself. Today the exception they must write is wider than the rule they mean, and its `reason` is a comment asking humans not to use it for what it permits.

`_exemption` is shared by the package-level and workspace-level paths, so one change covers both.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_type_only_exception_exempts_a_type_only_import():
    m = model(("web.screens", "web.api"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))
    config = Config(
        allowed={"screens": [], "api": []},
        exceptions=(Exemption("web.screens", "web.api", "prop shapes only", kind="type_only"),),
    )
    assert check(m, config).problems == ()


def test_a_type_only_exception_does_not_exempt_a_value_import():
    """The whole point: the carve-out must not widen to the call it forbids."""
    m = model(("web.screens", "web.api"))
    config = Config(
        allowed={"screens": [], "api": []},
        exceptions=(Exemption("web.screens", "web.api", "prop shapes only", kind="type_only"),),
    )
    assert [p.components for p in check(m, config).problems] == [("screens", "api")]


def test_an_exception_without_a_kind_still_exempts_anything():
    m = model(("web.screens", "web.api"))
    config = Config(
        allowed={"screens": [], "api": []},
        exceptions=(Exemption("web.screens", "web.api", "legacy"),),
    )
    assert check(m, config).problems == ()


def test_an_unknown_exception_kind_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="kind"):
        written(tmp_path, """
            [archview]
            package = "web"
            [[archview.exceptions]]
            importer = "web.screens"
            imported = "web.api"
            reason = "why"
            kind = "lazy"
        """)


def test_kind_is_parsed(tmp_path):
    config = written(tmp_path, """
        [archview]
        package = "web"
        [[archview.exceptions]]
        importer = "web.screens"
        imported = "web.api"
        reason = "prop shapes only"
        kind = "type_only"
    """)
    assert config.exceptions[0].kind == "type_only"
```

Plus one at workspace level, since `_exemption` is shared — a type-only cross-package import exempted by a workspace exception with `kind = "type_only"`, and a value import between the same pair still failing. Follow `tests/test_workspace.py`'s existing `_prepare_workspace` helpers.

Import `replace` from `dataclasses`; `model` from `tests.builders`; reuse `tests/test_rules_config.py`'s `written` helper.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest -v -k "type_only_exception or unknown_exception_kind or kind_is_parsed"`
Expected: FAIL — `Exemption` takes no `kind`.

- [ ] **Step 3: Implement**

`config.py`: add `kind: str | None = None` to `Exemption`. In `_exceptions`, `kind` is optional — note `_tables` currently requires every named key to be a non-empty string, so read `kind` separately rather than adding it to that required set. Validate against `("type_only",)` and raise `ConfigError` naming the key and the allowed values.

`check.py`: `_exemption` gains one condition — an exemption whose `kind` is `"type_only"` matches only when `imp.type_checking` is true.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Let an exception be scoped to type-only imports

A screen may name the shape of a prop it receives and must never call the
API. Without a kind, the exception has to be wider than the rule it means,
and its reason becomes a comment asking humans not to use what it permits
(issue #8).

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 3: ADR 0015, docs — M11 closes

**Files:**
- Create: `docs/decisions/0015-test-code-and-type-only-exceptions.md`
- Modify: `docs/06-using-archview-in-a-repo.md`, `docs/02-requirements.md`, `docs/05-approach-and-roadmap.md`, `AGENTS.md`

**Interfaces:** consumes everything above.

- [ ] **Step 1: Write ADR 0015**

House style of `docs/decisions/0006-checker-semantics.md` and `0014-say-what-is-not-checked.md` — read both. Record, each with its reasoning:

- **Why `source_roots` was chosen over an opt-in `test_roots`**: it needs no new syntax, `allowed`/`forbidden`/`exceptions` work on the result unchanged, and `--hide-tests` already exists for the production picture.
- **The mechanism**, and why it is the one M9 proved: a module outside `package` is otherwise indistinguishable from a third-party dependency, so the graph must be built over the analysed package plus the extras together.
- **Only packages count, not loose modules**, and why — grimp graphs packages.
- **Each extra root package is one component named after itself**, consistent with ADR 0006's treatment of the project's own root module.
- **Which spelling to use, and that the issue used the other one.** `["src", "."]` works; `["src", "tests"]` contributes nothing because a package `tests/` is rooted at the repo. Say plainly that the reporter guessed the second and got silence, that M10 made it warn, and that this milestone keeps it warning rather than quietly accepting both.
- **`kind` over a per-exception `type_checking_imports`**: it is a property of the import being exempted, not a re-configuration of the checker for one rule, and it leaves room for `lazy` later without a second mechanism.
- **A limitation, stated plainly:** adding a root turns previously invisible modules into components, so an existing `[archview.allowed]` table will now fail as `undeclared` until it names them. That is the `undeclared` rule working, and it only affects a repo that explicitly listed such a root — which until M10 did nothing at all, and since M10 has been warning about it.

- [ ] **Step 2: Update the docs**

`docs/06`: a section on bringing test code under the rules, leading with **which spelling to use** and the worked example from issue #10 ("no test may import a plugin, except this one" as a `forbidden` rule plus a module-level exception); plus `kind = "type_only"` in the exceptions documentation. `docs/02`: a requirement row and a status line. `docs/05`: an M11 row. `AGENTS.md`: M1–M11, ADR 0015 in the read-order list, kept terse.

- [ ] **Step 3: Verify the whole branch**

```bash
uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check
uv run archview check --format json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['ok'], d['warnings'], d['unused_allowances'])"
```

The last must print `True [] []`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "M11: ADR 0015 and docs

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Self-review notes

**Spec coverage.** §1 mechanism → T1; §2 `kind` → T2; §3 interaction needs no code; §4 adoption → T3's ADR limitation; §5 testing → folded into T1 and T2; §6 out-of-scope items stay out.

**Known risk.** Task 1 changes `_is_internal`, which is threaded through the whole Python extractor. The guard is that no golden file may move — every fixture is single-root, so any golden change means single-root behaviour shifted, which is the one thing this task must not do.

**Naming consistency.** `build_model(..., extra=)` (T1) and `ComponentMap.extra_roots` (T1) are used only within T1. `Exemption.kind` (T2) is read by `_exemption` (T2). No interface crosses between Tasks 1 and 2 — they are independent and could land in either order.
