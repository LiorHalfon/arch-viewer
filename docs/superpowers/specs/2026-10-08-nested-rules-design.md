# M12 design: rules for sub-packages

Date: 2026-10-08. Status: approved in brainstorming, pending spec review.

GitHub issue #14. Rules can only be written between components, and a component is a
direct child of the project package unless `[archview.components]` says otherwise. That
map is flat. To write rules between the 12 packages under `src/webapp/services/` in
tiny-tale-backend, the reporter needed 27 component patterns, 35 components in all. Fifteen
of them exist only to stop the leftover `webapp` component from producing
`CYCLE print_svc -> webapp -> print_svc` on code with no cycle. A new `services/*` package
that nobody adds a pattern for joins `webapp` silently.

The fix is a rules file inside the sub-package, scoped to that package's children:

```toml
# src/webapp/services/archview.toml
[archview.allowed]
print            = ["payment", "pricing", "storage"]
pricing          = []
story_generation = ["print", "storage", "stories", "users"]
```

The root file is unchanged and still sees `services` as part of `webapp`.

## Decisions taken in brainstorming

- A nested file takes the rule keys only. The keys that shape the model belong to the
  root, and the scope inherits them.
- Module patterns in a nested file (`components`, `exceptions`) use full module names,
  as the root file, `check` output and `archview why` do. Component names in `allowed`,
  `forbidden`, `layers`, `independent` and `ignored` are the short child names.
- Nested files may nest. Workspace members may hold them.
- In this milestone: `check`, `init --root`, `serve`, and a baseline per scope.
- Not in this milestone: a key that limits which modules outside the scope a scope's
  components may import. Those imports stay under the parent's rules only.

## Approach

Check each scope with the existing `check()`, on a model cut down to the scope.

Cut the model to the modules inside `src.webapp.services`, keep only the imports with both
ends inside, and set `project` to `src.webapp.services`. `ComponentMap` then yields
`print`, `pricing` and the rest as components, with no change to its code. `check()` on
that model with the nested file's `Config` reports `not_allowed`, `forbidden`,
`undeclared` (a new `services/*` package missing from `allowed`), cycles, zones and unused
allowances exactly as it does for the root.

Two alternatives were rejected. Parent and child components inside `ComponentMap` would
reach every consumer (metrics, cycles, views, baseline) for the same result. Expanding a
nested file into flat `[archview.components]` patterns keeps the false cycle, because the
root would still need `webapp`'s other children as components.

## 1. The nested file and its schema

A nested rules file is a file named `archview.toml` in the directory of a package below
the project package. It uses the same `[archview]` table name as a root file. A
`pyproject.toml` inside a package is never read for rules.

It may set:

`allowed`, `forbidden`, `layers`, `independent`, `exceptions`, `components`, `ignored`,
`fail_on_violations`, `fail_on_cycles`, `metrics`, `baseline`.

Every other root key is a `ConfigError` (exit 2) that names the file and the key:

`package`, `language`, `tsconfig`, `source_roots`, `exclude`, `type_checking_imports`,
`externals`, `externals_undeclared`, `public`, `workspace`.

```
src/webapp/services/archview.toml: [archview] exclude belongs in the root rules file;
a nested file holds rules between the children of src.webapp.services
```

An unknown key still gets the "did you mean" hint `parse_config` gives today. Errors
in a nested file name it by its path relative to the repo, not by `path.name`, since
every nested file is called `archview.toml`.

The scope's `Config` takes `type_checking_imports` and `exclude` from the root config.
Root `exceptions`, `ignored` and `components` do not carry over. They name root
components and root pairs, and each file speaks for its own.

## 2. Finding nested files

After the project opens, walk its package directory for files named `archview.toml`,
skipping `node_modules` and hidden directories (the rule `server/state.py`'s
`source_files` already uses). The package directory is:

- Python: `project.source_root / project.package`.
- TypeScript: the repo joined with the source root the extractor stripped from the ids,
  `config.source_roots[0]` when set, otherwise read off the model the way
  `rules/init.py`'s `_inferred_source_roots` does. That helper moves somewhere both
  `init` and discovery can use it.

A file in a directory `D` strictly below the package directory names the scope
`project + sep + sep.join(D.relative_to(package_dir).parts)`. It is a scope when the model
has a node with that id of kind `"package"`. Otherwise the root report gets a notice of
kind `unchecked_rules_file`:

```
warning: src/webapp/legacy/archview.toml is not checked: src.webapp.legacy is not a
package archview analyses (excluded, or not a package)
```

A file directly in the package directory is never a scope, because that scope is the
root file's. If it is not the rules file in use, it gets the same notice ("the rules for
src are read from archview.toml"). For a TypeScript project whose source root is the
repo, that file usually is the root rules file, and nothing is said.

Scopes are sorted by id.

## 3. Checking a scope

`scoped_model(model, scope)` in `model/filter.py`:

- keeps the nodes whose id is `scope` or lies within it, and drops every external node;
- keeps the imports whose importer and imported both lie within the scope;
- sets `project` to `scope` and the scope node's `parent` to `None`, the shape every
  model's root has;
- drops the extractor warnings, which the root report already lists once.

A scope's report is `check(scoped_model(model, scope), scope_config)` with its own
baseline applied (section 5). Its `project` is the scope id; its components are the
scope's children.

A scope sees no outside names, so a `forbidden` entry in a nested file whose `to` is not
one of the scope's components can never fire. At the root, an absent `forbidden` target
stays silent on purpose: it is usually a third-party package nobody imports, the ban
working (issue #5). In a nested file it is a dead rule, so it gets an `unknown_component`
notice: "[archview.forbidden] names 'openai', which is not a child of
src.webapp.services; imports that leave a nested scope are checked by the rules above it".

Nesting needs no special handling. `services/archview.toml` sees `print` as one component,
the same way the root sees `services` as part of `webapp`. A file in `services/print/`
constrains only `print`'s own children, an edge set no other file constrains.

In a workspace, each member is a `Project` and gets its scopes from `project_report`, so
`check` at the workspace root reports them inside that member's section with no change
to `workspace.py`'s checking.

## 4. The report and its output

`Report` gains `scopes: tuple[tuple[str, Report], ...] = ()`, each entry the rules file's
path relative to the repo (POSIX separators) and that scope's report. Only the root
report holds scopes, as a flat list sorted by scope id. `Report.failed` is true when a
root problem fails or any scope failed. `project_report` fills `scopes`, so the CLI,
the Stop hook, workspace sections and `serve` all see them.

Text: root problems and warnings print as today. Each scope follows as a section, its
body indented, built the way `render/workspace.py` builds a package section:

```
src.webapp.services (src/webapp/services/archview.toml)  1 problem
  VIOLATION print -> users (2 imports) not allowed by [archview.allowed.print]
    src/webapp/services/print/flow.py:12  from ..users import repo
    hint: ...
1 problem in 9 components and 1 nested scope. exit 1
```

A scope with nothing failing prints its header with `ok`, plus any warnings. The total
counts failing problems across the root and every scope. Passing, it reads
`ok: src, 9 components and 1 nested scope, no failing problems`. When there are no scopes, every
line of the output is unchanged from today, so existing goldens keep passing.

JSON: `report_to_dict` gains `"scopes": [{"rules": "<path>", **report_to_dict(scope)}]`,
always present (empty when there are none), and the top-level `ok` covers the scopes.
This is an additive change; the golden JSON files gain the empty key.

## 5. Baselines

A nested file's `baseline` key is relative to that file, and a default-named
`archview-baseline.json` next to it is applied when it exists. These are the same rules
`baseline_path` applies to the root, with the nested file as `config_path`. A `baseline`
key that names a missing file is a `ConfigError`, as at the root.

`check --update-baseline` writes the root's baseline as today, then one per scope at its
`baseline_path`, one `wrote ...` line each, the way workspace mode writes one per member.
Each baseline is built from that report's own problems only. At a workspace root,
`--update-baseline` also writes the scopes of every member it writes a baseline for.

## 6. `archview init --root X`

`--root` names a package the same way `graph --root` does (`model/query.py`'s `resolve`:
a full name or one relative to the project). `init` writes `archview.toml` into that
package's directory, inferred from the scoped model:

```toml
# Dependency rules between the children of src.webapp.services, inferred by
# `archview init --root` from the imports as they are today. Imports that leave
# src.webapp.services are checked by the rules above it, not here. Delete the
# dependencies that should not exist; the check then fails until the code matches.
# Agents: never edit this file to make the check pass - fix the code or ask.

[archview]
fail_on_violations = true
fail_on_cycles = true

[archview.allowed]
authors = ["users"]
...
```

The root rules, when there are any, supply the inherited keys, so the edges `init`
writes are the ones `check` will read (the lesson of issue #13). With `--force`, the
existing nested file's `components` and `ignored` are kept, as the root's are today.
Existing cycles switch `fail_on_cycles` off with the same comment the root gets.

Usage errors (exit 2): `X` is a module, `X` is the project itself, or `--root` is given
with `--externals`, `--config` or `--exclude`, which are root-only. An existing nested file
without `--force` is refused with the root's message. `--stdout` prints instead of writing.

## 7. `serve`

`failing_imports` (`rules/overlay.py`) adds the failing imports of every scope, so
drilling into `src.webapp.services` draws its broken edges in red with no change to view
code. The check panel lists each scope after the root's problems, under a heading with
the scope id and its rules file, using the existing problem cards. The `--watch`
signature adds every `archview.toml` the discovery walk finds, plus each scope's
baseline, so editing or adding a nested file reloads the page.

## 8. Docs

- ADR 0016, nested rules files.
- `docs/02-requirements.md`: C17.
- `docs/05-approach-and-roadmap.md`: M12 row.
- `docs/06-using-archview-in-a-repo.md`: a recipe, with the tiny-tale-backend `services`
  case as its example.
- `AGENTS.md`: the state line.

Releasing: minor version bump, since the JSON shape and the CLI flags change.

## Testing

- A new Python fixture `tests/fixtures/nested`: `shop/{api, models, services/{print,
  pricing, users}}`, a root `archview.toml`, `shop/services/archview.toml`, a scope-level
  violation and an `unchecked_rules_file` case.
- Unit: `scoped_model` (nodes, imports that leave the scope, externals, the root shape);
  nested schema (each root-only key rejected, inherited keys copied, the error names the
  path); discovery (Python, TypeScript, the package directory's own file, an orphan).
- Check: `undeclared` for a new child, a scope cycle, a scope exception with a full
  module name, the root not seeing scope edges.
- CLI: text and JSON goldens with one scope; an unchanged golden with none; exit codes;
  `--update-baseline` writing per scope; `init --root` and its usage errors; `init
  --root` then `check` passing on unchanged code, with `type_checking_imports = "ignore"`
  at the root.
- Workspace: a member with a nested file reports it in its section.
- Server: the scope's failing import marks the edge at the scope's level, and
  `/api/check` carries `scopes`.
- TypeScript: a nested file in a copy of `ts-sample`.
- `tests/test_self_check.py` still passes with zero warnings.
- Dogfood: `init --root src.webapp.services` on tiny-tale-backend, rules kept out of
  that repo with `--stdout`, then `check` with the file in place.

## Not in this milestone

- A key that limits imports leaving a scope.
- `archview metrics` for a scope. The scope's metrics are in `check --format json`.
- `[tool.archview]` in a nested `pyproject.toml`.
