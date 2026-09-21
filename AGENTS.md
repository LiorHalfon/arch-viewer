# arch-viewer

An architecture viewer + dependency-rules checker for Python and TypeScript code bases, inspired by Uncle Bob's
arch-view / dependency-checker (Clojure). Two faces, one model: an interactive drill-down diagram of
packages/modules with dependency direction and cycles, and a deterministic `check` command that holds
AI coding agents to a declared dependency structure.

## State of the repo

**M1–M10 are done**: `src/archview/` holds the extractors (grimp + an `ast` pass for
Python, the TypeScript compiler API for TypeScript, ADR 0010), the model (views,
cycles, layers, metrics, agent queries), the checker (`rules/`, with layers, zones,
baseline and rules that name a package outside the project, ADR 0011, and notices for
what it is not checking — a type-only import, a partly-covered externals table, an
unfed source root, ADR 0014), workspace mode (`workspace.py`, several packages
checked and drawn as one architecture, with a public surface per package, ADRs 0012
and 0013), the viewer (`server/` + `ui/`) and the CLI (`graph`, `check`, `init`,
`metrics`, `serve`, `why`, `deps`, `rdeps`, `cycles`). The repo commits its own
`archview.toml` and `tests/test_self_check.py` enforces it; GitHub Actions
(`.github/workflows/ci.yml`) runs tests, lint and `archview check` on every push.
Read in this order:

1. `docs/02-requirements.md` — what to build (IDs A*/V*/C*/G*/N* are referenced everywhere)
2. `docs/05-approach-and-roadmap.md` — architecture, formats, milestones M1–M10
3. `docs/superpowers/specs/` — the binding design specs a milestone is built from (ADRs 0011, 0012 both open by naming the one they record)
4. `docs/decisions/` — ADRs; 0001–0004 record what M1 settled, 0005 the optional MCP server, 0006 the checker semantics, 0007 the viewer, 0008 the M4 depth, 0009 the agent queries and the Stop hook, 0010 the TypeScript extractor, 0011 rules for outside imports, 0012 workspace mode, 0013 a package's public surface, 0014 say what is not checked
5. `docs/03-reference-uncle-bob-tools.md` — the original design (arch-view, dependency-checker)
6. `docs/04-research-tool-landscape.md` — what exists; why grimp, why not X
7. `docs/06-using-archview-in-a-repo.md` — adoption, the CLAUDE.md paragraph, hooks, workspace mode
8. `docs/01-video-notes.md` — the talk that started this
9. `spike/arch_graph.py` — the original one-file spike; superseded by `src/archview/`
10. `spike/viewer/view.py` — the spike's self-contained HTML viewer; superseded by `archview serve`

## Decisions already made

- Python and TypeScript (M6, ADR 0010); the model JSON and everything above the extractors stay language-agnostic.
- Scope = viewer **and** checker, sharing one analysis core.
- Extraction via **grimp** (BSD-2). Do not write a custom import resolver.
- Rules file: `archview.toml` with an `allowed` map per component (dependency-checker style); `archview init` infers it.
- Viewer: local web UI; Graphviz-WASM (`@viz-js/viz`) for the MVP, ELK + React Flow only if interactions demand it.
- Static analysis only — never import or execute the analysed project's sources, though reading TypeScript does run that repo's own `typescript` compiler. No network. Permissive licences only.
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

`archview` is installed as an editable uv tool (`uv tool install --editable . --force`
after dependency changes), so code edits here are live everywhere.

```
uv run archview graph                              # this repo, as text
uv run archview graph ~/git/tiny-tale-backend --root src [--json|--dot]
uv run archview graph ~/git/tiny-tale-backend --root src.webapp    # drill down
archview .                                        # in any repo: the viewer (short for `archview serve .`)
uv run archview serve ~/git/tiny-tale-backend --watch   # viewer in the browser
uv run archview graph --mermaid | --externals | --hide-tests
uv run archview metrics                           # Ca, Ce, I, A, D, zone per component
uv run archview check [--format json] [--update-baseline]   # exit 0 pass, 1 problems, 2 could not run
uv run archview why cli networkx                   # also: deps X, rdeps X, cycles [--root X]
uv run archview init ~/git/tiny-tale-backend --config /tmp/tt.toml   # rules kept outside that repo
uv run archview graph ~/git/storygenerator         # TypeScript (needs node + npm install there)
uv run archview check --package core               # at a workspace root: check one member alone
uv run archview graph --package core               # ditto for the view; drop --package for the whole workspace
npm ci --prefix tests/fixtures/ts-sample           # once, for the TypeScript tests
uv run pytest && uv run ruff check
UPDATE_GOLDEN=1 uv run pytest                      # accept new golden files, then read the diff
```

Releasing: bump `version` in `pyproject.toml`, commit, wait for CI, then
`git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`. The Release workflow checks that
the tag matches the version, reruns CI, builds, creates the GitHub release, and moves the
floating `vX.Y` tag to it. Minor bump per milestone or breaking change (rules file, JSON,
flags, exit codes), patch for fixes; no release for docs, tests or CI.

