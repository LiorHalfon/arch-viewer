# arch-viewer

An architecture viewer and dependency-rules checker for Python and TypeScript code
bases, inspired by Uncle Bob's arch-view and dependency-checker (Clojure). Two faces,
one model: an interactive drill-down diagram of packages and modules with dependency
direction and cycles, and a deterministic `check` command that holds AI coding agents to
a declared dependency structure.

## State of the repo

`src/archview/` holds:

- `extract/` reads the imports: grimp plus an `ast` pass for Python, the TypeScript
  compiler API for TypeScript (ADR 0010).
- `model/` builds views, cycles, layers, metrics and the agent queries (ADRs 0003, 0008,
  0009).
- `rules/` is the checker (ADR 0006), with layers, zones and a baseline. Rules can name a
  package outside the project (0011) and reach test code, exceptions can cover type-only
  imports (0015), rules files can sit inside sub-packages (0016, 0021), and a rule can
  name part of a component (0018, 0020). `check` says what it is not checking (0014).
- `workspace.py` checks and draws several packages as one architecture, each with its
  public surface (ADRs 0012, 0013).
- `server/` and `ui/` are the viewer. The UI draws its own SVG from Graphviz's layout,
  with colour schemes, dragging and quick find (ADRs 0007, 0017).
- `render/` writes DOT, Mermaid and the check report.
- `cli.py` has `graph`, `check`, `init`, `metrics`, `serve`, `why`, `deps`, `rdeps` and
  `cycles`. Every command reads components the way `check` does (ADR 0019).

The repo commits its own `archview.toml`. `tests/test_self_check.py` enforces it, and
GitHub Actions (`.github/workflows/ci.yml`) runs tests, lint and `archview check` on
every push. `examples/pizzeria` is the demo the README's GIF is recorded from;
`tests/test_examples.py` pins its one cycle and one broken rule.

Read in this order:

1. `docs/02-requirements.md`: what to build (the IDs A*/V*/C*/G*/N* are referenced everywhere)
2. `docs/05-architecture.md`: the architecture, the formats and the risks
3. `docs/decisions/`: one ADR per decision that shaped the code; the file names say which
4. `docs/03-reference-uncle-bob-tools.md`: the original design (arch-view, dependency-checker)
5. `docs/04-research-tool-landscape.md`: what exists; why grimp, why not X
6. `docs/06-using-archview-in-a-repo.md`: adoption, the CLAUDE.md paragraph, hooks, workspace mode
7. `docs/metrics.md`: Ca, Ce, I, A, D and the zones
8. `docs/01-video-notes.md`: the talk that started this

## Decisions already made

- Python and TypeScript (ADR 0010); the model JSON and everything above the extractors stay language-agnostic.
- Scope = viewer **and** checker, sharing one analysis core.
- Extraction via **grimp** (BSD-2). Do not write a custom import resolver.
- Rules file: `archview.toml` with an `allowed` map per component (dependency-checker style); `archview init` infers it.
- Viewer: local web UI, plain ES modules, no build step. Graphviz-WASM (`@viz-js/viz`) lays every view out and the UI draws the SVG from its JSON (ADR 0017); ELK + React Flow only if interactions demand more.
- Static analysis only: never import or execute the analysed project's sources, though reading TypeScript does run that repo's own `typescript` compiler. No network. Permissive licences only.
- Working name `archview` for the package and CLI.

## Conventions

- Python 3.12+, `uv` for envs/locking, `pytest`, `ruff` (format + lint), type hints in modern style (`str | None`).
- Layout: `src/archview/{extract,model,rules,render,server,ui,cli.py}`; `tests/` with fixture projects under `tests/fixtures/` and golden JSON outputs.
- Small functions, tests first for the core, deterministic output (sort by name wherever there is a tie).
- The repo commits its own `archview.toml`; `archview check` must pass on this code base (CI).
- Keep this file short; put details in `docs/`.

## Working agreements for sessions

- Work in vertical slices (extract → model → CLI → UI), one feature at a time. Dogfood on `examples/pizzeria` and on any real repo you have.
- Never edit a rules file to make `archview check` pass; fix the code or ask.
- Update `docs/02-requirements.md` when a requirement changes; record decisions in `docs/decisions/` (ADR style, one file each). Specs and plans are working notes in `docs/superpowers/`, which git ignores.
- When a change alters what the README's GIF shows (the pizzeria's views, the panel, the source view), re-record it with `uv run scripts/record_demo.py` and look at it before committing. Each re-record adds about 2.5 MB to the history, so leave it alone for changes it does not show.

## Useful commands

`archview` is installed as an editable uv tool (`uv tool install --editable . --force`
after dependency changes), so code edits here are live everywhere.

```
uv run archview graph                              # this repo, as text
uv run archview graph examples/pizzeria [--json|--dot]
uv run archview graph examples/pizzeria --root pizzeria.kitchen   # drill down
archview .                                        # in any repo: the viewer (short for `archview serve .`)
uv run archview serve examples/pizzeria --watch   # viewer in the browser
uv run archview graph --mermaid | --externals | --hide-tests
uv run archview metrics                           # Ca, Ce, I, A, D, zone per component
uv run archview check [--format json] [--update-baseline]   # exit 0 pass, 1 problems, 2 could not run
uv run archview check examples/pizzeria           # exit 1: the demo's planted cycle and broken rule
uv run archview why cli networkx                   # also: deps X, rdeps X, cycles [--root X]
uv run archview init <repo> --config /tmp/rules.toml   # rules kept outside that repo
uv run archview graph tests/fixtures/ts-sample     # TypeScript (needs node + npm ci there)
uv run archview check --package core               # at a workspace root: check one member alone
uv run archview graph --package core               # ditto for the view; drop --package for the whole workspace
npm ci --prefix tests/fixtures/ts-sample           # once, for the TypeScript tests
uv run pytest && uv run ruff check
node --test "tests/ui/*.test.mjs"                 # the viewer's JS modules alone (pytest runs them too)
UPDATE_GOLDEN=1 uv run pytest                      # accept new golden files, then read the diff
uv run scripts/record_demo.py                      # re-record docs/images/demo.gif from the pizzeria
```

Releasing: bump `version` in `pyproject.toml`, commit, wait for CI, then
`git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`. The Release workflow checks that
the tag matches the version, reruns CI, builds, creates the GitHub release, and moves the
floating `vX.Y` and `latest` tags to it, so the install line in the README never names a
version. Minor bump per feature or breaking change (rules file, JSON,
flags, exit codes), patch for fixes; no release for docs, tests or CI.
