# M6 — TypeScript extractor: design

Date: 2026-09-17. Status: approved in brainstorming, pending spec review.

Milestone M6 (`docs/05-approach-and-roadmap.md`): a second extractor that produces the
same model JSON for TypeScript, so the viewer, checker, metrics and agent queries work
unchanged. Acceptance repo: `~/git/storygenerator` (Expo / React Native, TypeScript 5.9).
The roadmap's `tiny-tale-bespoke-pages` turned out to be a Python repo.

The design was checked against storygenerator and nine public repos (Next.js, Expo,
Vite, NestJS, ESM libraries, monorepos); findings are cited where they changed a decision.

## 1. Architecture

### Language selection

`open_project` picks the extractor:

1. `language = "typescript" | "python"` in `archview.toml`, or `--language`, wins.
2. Else a `tsconfig.json` at the repo root, or a `tsconfig` setting (below), means TypeScript.
3. Else Python, as today.

### The Node boundary

- `src/archview/extract/typescript.mjs` (package data, ~150 lines) is run by Python as
  `node typescript.mjs <repo> <tsconfig>` in a subprocess.
- It loads **the analysed repo's own `typescript`** via
  `createRequire(<repo>/package.json)`. It never installs anything and never touches the
  network.
- It prints **raw facts** as JSON on stdout, one entry per file:
  `{file, abstract, imports: [{specifier, resolved, line, text, type_only, lazy, dynamic}]}`,
  where `resolved` is the real path (symlinks followed), relative to the repo, or null.
- `src/archview/extract/typescript.py` turns the facts into a `Model` (ids, parents,
  kinds, externals, sorting, warnings). All model-building logic is Python, unit-tested
  without Node.

Dependency direction stays `extract → model`; `project` uses both extractors; the repo's
own `archview.toml` is not edited.

### tsconfig

- Default `tsconfig.json` at the repo root; `tsconfig = "server/tsconfig.json"` in
  `archview.toml` or `--tsconfig` picks another (immich keeps it in `server/`).
- Loaded with `ts.getParsedCommandLine`, following `extends`.
- **Any config diagnostic is fatal** (exit 2 with tsc's message). tsc otherwise falls back
  to default options when an `extends` target is missing, and resolution silently drops
  (bluesky: 67% resolved instead of 95%).
- **`references` are followed**: the file list is the union of every referenced project's
  files, and each file is resolved with the compiler options of the tsconfig that owns it
  (hono's root tsconfig is `files: []` plus references).
- If there is no tsconfig where expected, the error lists the `tsconfig.json` files found
  below the repo (excluding `node_modules`), so the user can pick one.
- Monorepos are analysed **one package at a time** (`archview packages/core`, or
  `tsconfig =`). A whole-workspace model is out of scope for M6.

## 2. Mapping TypeScript onto the model

### Project, root, files

- **Project name**: `package.json` `name` with any `@scope/` stripped; else the directory
  name; `package =` overrides.
- **Source root**: if every analysed file (after the `*.config.*` and `.d.ts` drops below) lies under one top-level directory (`src/`),
  that directory is the root node's directory, as with the Python `src` layout; otherwise
  the directory of `package.json` (the repo). `source_roots = ["src"]` overrides.
- **Files**: the tsconfig program's root files, minus `.d.ts`, minus anything under
  `node_modules`, minus root-level `*.config.*` files (build tooling; `next.config.ts`,
  `vitest.config.ts`). Then `exclude` applies as for Python.
- Internal `.js`/`.jsx`/`.mjs`/`.cjs` files that are *resolved from an import* but not in
  the program's file list become module nodes too (ai-chatbot `lib/editor/diff.js`).

### Ids

The model gains `separator = "/"`. Ids are the path relative to the source root, prefixed
by the project, **keeping the file extension**:

```
storygenerator
storygenerator/components                 package (directory)
storygenerator/components/ui/index.ts     module (a barrel is an ordinary child)
storygenerator/components/ui/Button.tsx   module
storygenerator/components/ui/Button.web.tsx
```

- Directories are `package` nodes (`file = null`), files are `module` nodes.
- No clashes by construction: a file next to a same-named directory
  (`Transitions/Transitions.tsx` and `Transitions/Transitions/`; seen in 5 of 9 public
  repos) and dotted file names (`*.service.spec.ts`, `*.web.tsx`) need no special cases.
- At component level nothing is lost: an import of `@/components/ui` resolves to
  `components/ui/index.ts`, inside `components/ui`.

### Imports

Every `import`, `export … from`, `import()`, `require()` and `import x = require()` is one
`Import` with its line and statement text. Classification of each specifier:

| Resolved to | Result |
|---|---|
| a file inside the repo, not under `node_modules`, that is code (`.ts .tsx .js .jsx .mjs .cjs .mts .cts`) | internal import to that module |
| a `.d.ts` file | dropped |
| a file under `node_modules`, or a bare specifier that does not resolve | one `external` node per npm package: `react-native`, `@expo/vector-icons` (the first segment, or two for `@scope/`) |
| a Node builtin (`fs`, `node:fs`, from `module.builtinModules`) | dropped, like the Python stdlib |
| a non-code file (`.png`, `.json`, `.css`, `.svg`, …) | dropped |
| nothing, for a relative specifier or a `paths` alias whose target is inside the repo | warning `unresolved_import` |

Internal vs external is decided by the **real path of the resolved file**, not by tsc's
`isExternalLibraryImport` (which is computed on the pre-symlink path and would mark pnpm
workspace siblings external). An alias that maps into `node_modules` (outline maps bare
names like `vite`) is an external, not a warning.

Flags:

- `type_checking = true` for `import type`, `export type … from`, and imports whose named
  bindings are all `type`-qualified. The field keeps its name; the docs say it means
  "type-only" for TypeScript.
- `lazy = true` for `import()`, and for `require()` inside a function body.

Warnings:

- `dynamic_import` (existing kind) for `import(expr)` / `require(expr)` with a
  non-literal argument.
- `unresolved_import` (new kind), as in the table.

### Abstract (A9)

A module is abstract if it declares an `abstract class`, or if all its exports are
type-only (interfaces, type aliases). A component that also defines `interface Props` is
not. On the public repos this marks 1–7% of modules, mostly `types.ts` files and abstract
base classes.

## 3. The separator above the extractor

`Model.separator: str = "."`, serialized; model JSON schema goes to **3**. Python output
changes only by that field.

- New `model/names.py`: `within(name, ancestor, sep)`, `parent(name, sep)`,
  `ancestors(name, sep)`, `last(name, sep)`, `truncate(name, depth, sep)`. `sep` has no
  default.
- Callers pass `model.separator`: `model/view.py` (`_owner`, `_in_subtree`,
  `tangled_packages`), `model/query.py` (`within`, `_neighbours`, `_shorten`),
  `model/patterns.py` (`matches_name`, `specificity` take `sep`),
  `rules/components.py` (`ComponentMap` gets `sep`), `server/workspace.py` (file drawer
  names), `cli.py` (the package guess from `--root` stays Python-only).
- `[components]` and `ignored` patterns are written in the project's separator
  (`storygenerator/components/**`).
- UI: `/api` summary carries `separator`; `app.js` uses it in `short`, `parentOf` and the
  breadcrumbs; externals are labelled with their full id (`@expo/vector-icons`).
- Tests-hiding (V10): a pattern list per language. TypeScript: `**/*.test.*`,
  `**/*.spec.*`, `**/*.e2e.*`, `**/__tests__`, `**/__mocks__`, `**/test`, `**/tests`,
  `**/e2e`.
- Watch mode (V9): the signature globs the extractor's source extensions plus the
  tsconfig files, not only `*.py`.
- Rules file: components are still the direct children of the source root. `archview
  init` quotes keys that are not bare TOML keys (`"i18n.ts" = []`). New top-level keys:
  `language`, `tsconfig`.
- Renderers: DOT ids are quoted; a test pins ids containing `/`, `.` and `@`. Mermaid
  already sanitizes ids.

## 4. Errors, testing, CI, docs, release

### Errors (exit 2, one line, no traceback)

- `node` not on PATH.
- `typescript` not in `<repo>/node_modules`: "typescript not found in <repo>/node_modules;
  run npm install". No global fallback.
- A tsconfig diagnostic (tsc's message), or no tsconfig (with the list of found ones).
- The script crashing (its stderr in the message).

Syntax errors in individual files do not stop the run; tsc still reports their imports.

### Tests

- Fixture `tests/fixtures/ts-sample/`: `package.json` plus `package-lock.json` pinning
  `typescript`, and sources covering: a `paths` alias with an `extends` chain, a
  `references` split, a barrel `index.ts`, a file next to a same-named directory, a
  `.web.tsx` file, a `.test.ts` file and a `__mocks__` directory, `import type`,
  `import()`, a `require()` inside a function, `import(expr)`, a broken `@/` alias, a
  `.png` require, a scoped external, a Node builtin, an internal `.js` file, a `.d.ts`,
  a root `vite.config.ts`, an interface-only module, an abstract class, and a cycle.
- `tests/test_extract_typescript.py`: unit tests feeding hand-written facts JSON to
  `typescript.py` (no Node), plus end-to-end runs over the fixture, including the error
  cases (missing tsconfig, broken `extends`).
- `tests/golden/ts-sample/`: model and view JSON, via `UPDATE_GOLDEN=1`.
- `tests/test_names.py`: the helpers under `.` and `/`; the view, query, patterns and
  components tests each gain a `/` case.
- TypeScript tests skip when Node or the fixture's `node_modules` is missing;
  `ARCHVIEW_REQUIRE_TS=1` turns the skip into a failure.

### CI

`actions/setup-node`, then `npm ci --prefix tests/fixtures/ts-sample`, with
`ARCHVIEW_REQUIRE_TS=1` for the test step. `archview check` on this repo is unchanged.

### Dogfooding (acceptance)

`archview graph`, `check`, `metrics`, `why`, `cycles` and `serve` run on
`~/git/storygenerator` with rules outside that repo (`--config /tmp/sg.toml`), and the
viewer output is looked at before M6 is called done.

### Docs and release

- ADR 0010: TypeScript via the compiler API; the model separator; ids keep extensions;
  tsconfig handling (fatal diagnostics, references, one package at a time).
- `docs/02-requirements.md`: A13 implemented; new A15 (TypeScript extractor).
- `docs/05-approach-and-roadmap.md`: M6 acceptance repo is `storygenerator`.
- `docs/06-using-archview-in-a-repo.md`: a TypeScript section (Node, `npm install`,
  `tsconfig =`, monorepos).
- `AGENTS.md`: state and commands.
- Release 0.2.0 (schema bump).

## Out of scope for M6

A whole-workspace model for monorepos; `.vue`/`.svelte` files; a global TypeScript
fallback; resolving through `exports` beyond what tsc's own resolution does.
