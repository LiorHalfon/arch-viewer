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

archview needs Node.js and an installed project to read TypeScript. That bends N2: the
analysed repo's own `typescript` is loaded and run in the Node subprocess (its sources
are still only parsed), so analysing an untrusted repo runs code from its `node_modules`.
The model JSON is
schema 3 for both languages. Rules files for TypeScript name components as the
directories and root files below the source root (`"i18n.ts" = [...]`), and
`[components]` patterns use '/'. A whole-workspace monorepo model, `.vue`/`.svelte`
files and a global TypeScript fallback are left for later.

**Measured** (`storygenerator`, an Expo app, 408 source files, 2045 raw imports): full
analysis takes about 0.5 seconds; the model has 407 modules, 1935 imports, 11
components and 55 externals; exactly one unresolved import, which turned out to be a
genuine dead import in that app.
