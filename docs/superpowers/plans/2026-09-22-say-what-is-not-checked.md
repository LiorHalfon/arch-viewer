# M10 — Say what you are not checking: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three silences reported in GitHub issues #5, #8 and #10 — a rules key that is written, goes green, and never took effect.

**Architecture:** Four of the five code changes are new `Notice`s and `ConfigError`s in the existing rules layer. The fifth flips `type_checking_imports` to `"include"`, which is breaking and therefore lands now, while v0.4.0 is on `main` and untagged.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `ruff`, grimp.

**Spec:** `docs/superpowers/specs/2026-09-22-say-what-is-not-checked-design.md` — read it alongside this plan.

## Global Constraints

- Python 3.12+; `from __future__ import annotations` at the top of every module; modern type hints (`str | None`).
- Before every commit all four must pass: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check .`, `uv run archview check`.
- **Deterministic output (N1):** byte-identical output for identical input; sort by name wherever there is a tie. Every new notice must be emitted in a sorted order.
- **`tests/test_self_check.py` asserts zero warnings on this repo.** Three new notice kinds land here. If one fires on archview itself, that is a real finding about archview's own rules — report it; do not weaken the assertion.
- Measured before planning: archview has **zero** type-only imports, so Task 1 does not break its own check. The fixtures do have them — `sample` 1 of 10, `ts-sample` 4 of 18 — so test expectations and goldens will move in Task 1. That is the flip working, not a bug.
- Golden files: regenerate with `UPDATE_GOLDEN=1 uv run pytest`, then **read the diff** and explain every change. An unexplained golden change is a bug.
- Never edit `archview.toml` to make a check pass — fix the code or report it.
- Small functions; the repo targets cyclomatic complexity ≤ 5 where practical.
- Commit messages: imperative mood, no `feat:`/`fix:` prefixes. End every commit message with:

```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW
```

## File Structure

| File | Responsibility after this plan |
|---|---|
| `src/archview/rules/config.py` | the flipped default; `externals_undeclared`; rejecting the key where it cannot apply |
| `src/archview/rules/check.py` | three new notices, one new problem kind |
| `src/archview/project.py` | the empty-source-root notice needs what `open_project` knows |
| `docs/06-using-archview-in-a-repo.md` | the `allowed` vs `externals` contrast |

---

## Task 1: flip the `type_checking_imports` default

**Files:**
- Modify: `src/archview/rules/config.py` (the `_choice` call in `parse_config`)
- Test: `tests/test_rules_depth.py`, plus whatever Task 1 moves

**Interfaces:**
- Produces: `Config.type_checking_imports` defaults to `"include"`. The accepted values are unchanged (`"ignore"`, `"include"`).

This is the breaking change. It lands first so every later task is written against the new default.

- [ ] **Step 1: Write the failing test**

In `tests/test_rules_depth.py`, beside the existing `type_checking` tests (read them first and match their style):

```python
def test_a_type_only_import_is_checked_by_default():
    """A type-only import is still a dependency: it is a reason this file cannot be
    understood without that one, and it becomes a runtime import the moment someone
    needs a value (issue #8)."""
    m = model(("shop.api", "shop.infra"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))
    report = check(m, Config(allowed={"api": [], "infra": []}))
    assert [p.components for p in report.problems if p.fails] == [("api", "infra")]


def test_ignore_restores_the_old_behaviour():
    m = model(("shop.api", "shop.infra"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))
    report = check(m, Config(allowed={"api": [], "infra": []}, type_checking_imports="ignore"))
    assert report.problems == ()
```

Import `replace` from `dataclasses` and `model` from `tests.builders` as that file already does.

- [ ] **Step 2: Run them and watch the first fail**

Run: `uv run pytest tests/test_rules_depth.py -v -k "type_only_import_is_checked or ignore_restores"`
Expected: the first FAILs (no problem reported, because the default ignores it); the second passes already and is the control.

- [ ] **Step 3: Implement**

In `src/archview/rules/config.py`'s `parse_config`, the call is currently:

```python
        type_checking_imports=_choice(
            table, "type_checking_imports", ("ignore", "include"), "ignore", where
        ),
```

Change the default argument from `"ignore"` to `"include"`. Also change the `Config` dataclass field default from `"ignore"` to `"include"`, so a `Config()` built in code (as many tests do) matches a parsed one — if those two disagree, tests and the CLI will behave differently and it will be very hard to see why.

- [ ] **Step 4: Run the whole suite and deal with the fallout**

Run: `uv run pytest`

Expect failures — that is the point. For **each** one, decide which it is and say so in your report:

- a test that asserted the old default and should now assert the new one → update it, and say why in a comment or docstring;
- a test that happens to use a fixture with a type-only edge and now sees an extra edge → update the expectation;
- **a real behaviour change you did not predict** → stop and report it rather than adjusting the test.

Then regenerate goldens: `UPDATE_GOLDEN=1 uv run pytest`, read the diff, and explain each file's change in your report. Expect view and check goldens to gain edges; the model goldens should **not** change, because extraction is untouched.

- [ ] **Step 5: Verify and commit**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`

```bash
git add -A
git commit -m "Default type_checking_imports to include

A type-only import is a dependency: a reason this file cannot be
understood without that one, and a runtime import the moment someone
needs a value. The surprise should run towards archview checking more
than expected, never less (issue #8).

Breaking, and free only while v0.4.0 is unreleased.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 2: reject `type_checking_imports` where it cannot apply

**Files:**
- Modify: `src/archview/workspace.py` (`open_workspace`), or `src/archview/rules/config.py` if you find a cleaner seam
- Test: `tests/test_workspace.py`

**Interfaces:**
- Consumes: Task 1's default.
- Produces: opening a workspace whose **root** rules file sets `type_checking_imports` in its bare `[archview]` table raises `ConfigError`.

Verified before planning: with `type_checking_imports = "include"` in a workspace root's `[archview]` table, a type-only cross-package import still passed. The key is read into the root `Config` and never consulted, because each package is checked with its **own** config.

The workspace table already rejects unknown keys, so only the root's `[archview]` table needs this. Note the root `Config` legitimately carries `package` (the workspace name) and `workspace`, so do not reject the whole table — only this key.

- [ ] **Step 1: Write the failing test**

```python
def test_type_checking_imports_at_a_workspace_root_is_an_error(tmp_path):
    """It is read and never consulted there - each package is checked with its own
    config - so writing it reads as applied when it is not (issue #8)."""
    root = _prepare_workspace(tmp_path, allowed={"core": (), "plugin": ("core",)})
    text = (root / "archview.toml").read_text()
    (root / "archview.toml").write_text('[archview]\ntype_checking_imports = "include"\n' + text)
    with pytest.raises(ConfigError, match="type_checking_imports"):
        open_workspace(root)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_workspace.py -v -k "type_checking_imports_at_a_workspace_root"`
Expected: FAIL — `DID NOT RAISE`.

- [ ] **Step 3: Implement**

In `open_workspace`, after the `config.workspace is None` check, raise when the root config sets the key. You need to know whether it was **set**, not merely what it defaults to. `parse_config` does not record that today, so the simplest honest approach is to check the raw table: `open_workspace` already has `path`, so read it with the existing `_read_toml` helper and look for the key under the config's own table name. Prefer that over adding a sentinel default.

Message shape: name the key, say it has no effect at a workspace root, and say where it belongs (each package's own rules file).

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Reject type_checking_imports at a workspace root

It is read there and never consulted, because each package is checked
with its own config - so writing it reads as applied when it is not.

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 3: say when `[archview.externals]` is doing less than it looks

**Files:**
- Modify: `src/archview/rules/check.py` (`_warnings`)
- Test: `tests/test_rules_externals.py`

**Interfaces:**
- Produces: a `Notice` of kind `partial_externals`.

The algorithm, exactly: for each package named anywhere in `[archview.externals]`, find the components that import that package and are **not themselves keys** of the table. If any exist, emit one notice per (table key that names the package, package) pair, listing the unconstrained importers.

It fires only for packages actually named in the table, which is what keeps it quiet: a repo with thirty dependencies and two constrained components gets at most two lines.

A component that **is** a key but omits the package is already constrained and fails properly — it is not this notice's business.

- [ ] **Step 1: Write the failing test**

```python
def two_reach_openai() -> Model:
    """`wiring` and `book` both import openai; only `wiring` will be constrained."""
    nodes = (
        Node("shop", None, "package"),
        Node("shop.wiring", "shop", "module", "shop/wiring.py"),
        Node("shop.book", "shop", "module", "shop/book.py"),
        Node("openai", None, "external"),
        Node("httpx", None, "external"),
    )
    imports = (
        Import("shop.wiring", "openai", "shop/wiring.py", 1, "import openai"),
        Import("shop.book", "openai", "shop/book.py", 1, "import openai"),
        Import("shop.book", "httpx", "shop/book.py", 2, "import httpx"),
    )
    return Model(project="shop", nodes=nodes, imports=imports)


ALLOWED_BOTH = {"wiring": (), "book": ()}


def test_a_partial_externals_table_says_what_it_does_not_cover():
    """The whole of issue #5: the table reads as a fence and is an allow-list."""
    config = Config(allowed=ALLOWED_BOTH, externals={"wiring": ("openai",)})
    report = check(two_reach_openai(), config)
    note = next(w for w in report.warnings if w.kind == "partial_externals")
    assert "book" in note.message
    assert "openai" in note.message


def test_no_note_when_every_importer_is_constrained():
    config = Config(
        allowed=ALLOWED_BOTH,
        externals={"wiring": ("openai",), "book": ("openai", "httpx")},
    )
    report = check(two_reach_openai(), config)
    assert [w for w in report.warnings if w.kind == "partial_externals"] == []


def test_no_note_for_a_package_the_table_does_not_name():
    """httpx is imported by an unconstrained component, but the table never names it,
    so it is not this notice's business - that is what keeps the notice quiet."""
    config = Config(allowed=ALLOWED_BOTH, externals={"wiring": ("openai",)})
    report = check(two_reach_openai(), config)
    notes = [w for w in report.warnings if w.kind == "partial_externals"]
    assert not any("httpx" in w.message for w in notes)
```

Import `Model`, `Node` and `Import` from `archview.model.graph`. Note `two_reach_openai` also feeds the third test, where `httpx` is the package the table does not name.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_rules_externals.py -v -k partial_externals`
Expected: FAIL — no such notice kind.

- [ ] **Step 3: Implement**

In `_warnings`, after the existing `config.externals` loop. You need, for each external package, which components import it — `component_edges`' `outside` bucket has exactly that, and `_warnings` does not currently receive it. Thread `edges` in rather than recomputing it; `check()` already has it.

Keep it sorted: iterate table keys sorted, packages sorted, and list unconstrained importers sorted.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`

Confirm `tests/test_self_check.py` still passes — archview's own `archview.toml` has no `[archview.externals]` table, so nothing should fire.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Say when an externals table covers less than it appears to

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 4: `externals_undeclared = "error"`

**Files:**
- Modify: `src/archview/rules/config.py`, `src/archview/rules/check.py`, `src/archview/render/check.py`
- Test: `tests/test_rules_config.py`, `tests/test_rules_externals.py`

**Interfaces:**
- Produces: `Config.externals_undeclared: str = "allow"`, accepting `"allow"` and `"error"`. `ProblemKind` gains `"undeclared_externals"`.

When set to `"error"`, every component that imports anything outside the project must be a key in `[archview.externals]`, exactly as `[archview.allowed]` requires a component to be declared. The default stays open so adoption is unchanged.

Use the existing `_choice` helper so a bad value is a `ConfigError` rather than reading as "off".

- [ ] **Step 1: Write the failing test**

```python
def test_closed_mode_fails_a_component_with_no_externals_entry():
    config = Config(
        allowed={"api": ["llm"], "llm": []},
        externals={"api": ()},
        externals_undeclared="error",
    )
    report = check(model_with_external(), config)
    assert [(p.kind, p.components) for p in report.problems if p.fails] == [
        ("undeclared_externals", ("llm",))
    ]


def test_closed_mode_passes_when_every_reacher_is_declared():
    config = Config(
        allowed={"api": ["llm"], "llm": []},
        externals={"llm": ("openai",)},
        externals_undeclared="error",
    )
    assert [p for p in check(model_with_external(), config).problems if p.fails] == []


def test_the_default_is_open():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"api": ()})
    assert [p for p in check(model_with_external(), config).problems if p.fails] == []


def test_a_bad_externals_undeclared_value_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="externals_undeclared"):
        written(tmp_path, '[archview]\npackage = "shop"\nexternals_undeclared = "warn"\n')
```

`model_with_external()` lives in `tests/builders.py`; its `llm` component imports `openai`.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest -v -k "closed_mode or the_default_is_open or bad_externals_undeclared"`
Expected: FAIL — unknown key, then no such problem kind.

- [ ] **Step 3: Implement**

`config.py`: add the field, add `"externals_undeclared"` to `TOP_KEYS`, parse with
`_choice(table, "externals_undeclared", ("allow", "error"), "allow", where)`.

`check.py`: add `"undeclared_externals"` to `ProblemKind`, and produce one problem per
component that has an outside edge and is not a key of `config.externals`, when the
setting is `"error"`. Its hint should say what to add and where. Sort by component name.

`render/check.py`: add the kind to `LABELS` (`UNDECLARED EXTERNALS` or similar). It has
one component, not a pair, so do **not** add it to `PAIRS`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Add externals_undeclared = error to close the table

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 5: a source root that contributes nothing says so

**Files:**
- Modify: `src/archview/project.py`, `src/archview/rules/check.py` (to carry the notice) — find the seam; see below
- Test: `tests/test_project.py` (or wherever `open_project` is tested), `tests/test_cli_check.py`

**Interfaces:**
- Produces: a `Notice` of kind `empty_source_root`, one per `source_roots` entry that yields no modules.

Verified before planning: `source_roots = ["src", "tests"]` on a package laid out as
`src/<pkg>/` beside `tests/` reports exactly what `["src"]` reports — same components,
no warning.

**The seam is the judgement call in this task.** `open_project` knows the configured
roots and which modules were found; `check` produces the notices. Options: have
`open_project` attach the finding to `Project`, or have `check` recompute it from
`config.source_roots` and the model. Pick whichever keeps `model` free of `rules` and
does not make `Project` carry checker concerns, and **say in your report which you chose
and why**.

- [ ] **Step 1: Write the failing test**

```python
def test_a_source_root_that_contributes_nothing_says_so(tmp_path):
    """`tests/` here is a real package; it is just not under `package`, so the scoping
    drops it - silently, until now (issue #10)."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_a.py").write_text("from pkg import a\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "pkg"\nsource_roots = ["src", "tests"]\n'
        "[archview.allowed]\na = []\n"
    )
    report = project_report(open_project(tmp_path))
    note = next(w for w in report.warnings if w.kind == "empty_source_root")
    assert "tests" in note.message


def test_a_source_root_that_contributes_modules_is_quiet(tmp_path):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "pkg"\nsource_roots = ["src"]\n'
        "[archview.allowed]\na = []\n"
    )
    report = project_report(open_project(tmp_path))
    assert [w for w in report.warnings if w.kind == "empty_source_root"] == []
```

- [ ] **Step 2: Run them and watch the first fail**

Run: `uv run pytest -v -k "source_root_that_contributes"`
Expected: the first FAILs with `StopIteration`.

- [ ] **Step 3: Implement** at the seam you chose.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check`

archview's own `archview.toml` sets no `source_roots`, so nothing should fire on it.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Say when a source root contributes no modules

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Task 6: ADR 0014 and docs — M10 closes

**Files:**
- Create: `docs/decisions/0014-say-what-is-not-checked.md`
- Modify: `docs/06-using-archview-in-a-repo.md`, `docs/02-requirements.md`, `docs/05-approach-and-roadmap.md`, `AGENTS.md`

**Interfaces:** consumes everything above.

- [ ] **Step 1: Write ADR 0014**

House style of `docs/decisions/0006-checker-semantics.md` and `0013-public-surface.md` — read both. Record, each with its reasoning:

- **The three issues are one failure.** Quote the reporter: *a person writes the line, sees green, and believes it took.* Name all three silences and that each was reproduced before designing.
- **The default flips to `"include"`**, why a type-only import is a dependency, and that it is breaking and therefore lands while v0.4.0 is untagged.
- **A key that cannot take effect is an error**, consistent with ADR 0011 (stdlib) and ADR 0013 (unpublished grant).
- **The partial-externals notice's scoping rule** — only packages named in the table — and why that keeps it quiet.
- **`externals_undeclared` defaults open** while `type_checking_imports` flips: one is an adoption ramp, the other was a dangerous default. Say why they differ, because the asymmetry will look arbitrary otherwise.
- **A limitation, stated plainly:** the partial-externals notice sees only what the graph contains, so a package nothing imports yet produces no notice — the table can still be wrong in a way archview cannot see.

- [ ] **Step 2: Update the docs**

`docs/06`: the `allowed` vs `externals` contrast — a component missing from `allowed` **fails**, a component missing from `externals` is **unconstrained** — plus `externals_undeclared` and the new default. `docs/02`: a requirement row and a status line. `docs/05`: an M10 row. `AGENTS.md`: M1–M10 in the State of the repo paragraph, kept terse.

Do **not** bump the version: M10 and M11 ship together under 0.4.0, which is already on `main` untagged.

- [ ] **Step 3: Verify the whole branch**

```bash
uv run pytest && uv run ruff check && uv run ruff format --check . && uv run archview check
uv run archview check --format json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['ok'], d['warnings'], d['unused_allowances'])"
```

The last must show `True [] []`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "M10: ADR 0014 and docs

$(printf 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01JWxyJpR8LoHserffZzKuzW')"
```

---

## Self-review notes

**Spec coverage.** §1 → T1; §2 → T2; §3 → T3; §4 → T4; §5 → T5; §6 → T6; §7 testing is folded into each task; §8 out-of-scope items are M11.

**Known risk.** Task 1 is the one that moves existing expectations. The instruction there matters: an unpredicted behaviour change is a finding to report, not a test to adjust.

**Naming consistency.** Notice kinds: `partial_externals` (T3), `empty_source_root` (T5). Problem kind: `undeclared_externals` (T4). Config fields: `type_checking_imports` (T1, T2), `externals_undeclared` (T4).
