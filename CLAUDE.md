# arch-viewer

An architecture viewer + dependency-rules checker for Python code bases, inspired by Uncle Bob's
arch-view / dependency-checker (Clojure). Two faces, one model: an interactive drill-down diagram of
packages/modules with dependency direction and cycles, and a deterministic `check` command that holds
AI coding agents to a declared dependency structure.

## State of the repo

**M1 is done**: `src/archview/` holds the extractor, the model and `archview graph`,
with 43 tests, golden files and its own analysis clean of cycles. **M2 (the checker)
is next.** Read in this order:

1. `docs/02-requirements.md` — what to build (IDs A*/V*/C*/G*/N* are referenced everywhere)
2. `docs/05-approach-and-roadmap.md` — architecture, formats, milestones M1–M6
3. `docs/decisions/` — ADRs; 0001–0004 record what M1 settled
4. `docs/03-reference-uncle-bob-tools.md` — the original design (arch-view, dependency-checker)
5. `docs/04-research-tool-landscape.md` — what exists; why grimp, why not X
6. `docs/01-video-notes.md` — the talk that started this
7. `spike/arch_graph.py` — the original one-file spike; superseded by `src/archview/`
8. `spike/viewer/view.py` — `uv run spike/viewer/view.py <repo>` → self-contained drill-down
   HTML; still the fastest way to *look* at a repo until `archview serve` lands in M3

## Decisions already made

- Python code bases first; the model JSON and everything above the extractor stay language-agnostic (TypeScript later).
- Scope = viewer **and** checker, sharing one analysis core.
- Extraction via **grimp** (BSD-2). Do not write a custom import resolver.
- Rules file: `archview.toml` with an `allowed` map per component (dependency-checker style); `archview init` infers it.
- Viewer: local web UI; Graphviz-WASM (`@viz-js/viz`) for the MVP, ELK + React Flow only if interactions demand it.
- Static analysis only — never import or execute the analysed project. No network. Permissive licences only.
- Working name `archview` for the package and CLI.

## Conventions

- Python 3.12+, `uv` for envs/locking, `pytest`, `ruff` (format + lint), type hints in modern style (`str | None`).
- Layout: `src/archview/{extract,model,rules,cli.py,server,ui}`; `tests/` with a fixture project under `tests/fixtures/` and golden JSON outputs.
- Small functions, tests first for the core, deterministic output (sort by name wherever there is a tie).
- The repo commits its own `archview.toml`; `archview check` must pass on this code base (CI).
- Keep this file short; put details in `docs/`.

## Working agreements for sessions

- Work in vertical slices (extract → model → CLI → UI), one milestone at a time; dogfood on `~/git/tiny-tale-backend` from M1.
- Never edit a rules file to make `archview check` pass; fix the code or ask.
- Update `docs/02-requirements.md` when a requirement changes; record decisions in `docs/decisions/` (ADR style, one file each).

## Useful commands

```
uv run archview graph                              # this repo, as text
uv run archview graph ~/git/tiny-tale-backend --root src [--json|--dot]
uv run archview graph ~/git/tiny-tale-backend --root src.webapp    # drill down
uv run pytest && uv run ruff check
UPDATE_GOLDEN=1 uv run pytest                      # accept new golden files, then read the diff
```

Not built yet: `archview check` / `init` (M2), `archview serve` (M3).
