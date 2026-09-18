# arch-viewer

Project brief for an **architecture viewer + dependency-rules checker for Python and TypeScript code bases**, inspired by the tool Uncle Bob describes in [LIVE: Uncle Bob on Software Fundamentals in the Age of AI](https://www.youtube.com/watch?v=zcLPGC-tvgk) (26:55–28:06) and by his real implementations, [unclebob/arch-view](https://github.com/unclebob/arch-view) and [unclebob/dependency-checker](https://github.com/unclebob/dependency-checker).

The idea in one paragraph: agents write most of the code; the human's job is to *see* the modular structure and decide how modules should be partitioned and which way dependencies run; a spec file captures that decision and a fast deterministic checker keeps the agents inside it. This repo contains the requirements, the research on what exists, a recommended approach, and the tool itself: milestones M1–M4 are built (graph, checker, browser viewer, metrics, baseline); agent queries (M5) are next.

## Contents

| Path | What it is |
|---|---|
| `AGENTS.md` | Context for coding-agent sessions: decisions, conventions, reading order (`CLAUDE.md` only imports it) |
| `docs/01-video-notes.md` | Paraphrased notes from the talk with timestamps |
| `docs/02-requirements.md` | Requirements with IDs and priorities (analysis core, viewer, checker, agent integration, non-functional, MVP acceptance) |
| `docs/03-reference-uncle-bob-tools.md` | How arch-view and dependency-checker actually work (formats, legend, metrics, CLI), and what to improve |
| `docs/04-research-tool-landscape.md` | Open-source tools and libraries surveyed on 2026-08-30, with verified behaviour and what to reuse vs build |
| `docs/05-approach-and-roadmap.md` | Proposed architecture, JSON model, `archview.toml` rules format, checker output, viewer stack, milestones M1–M6, risks |
| `docs/06-using-archview-in-a-repo.md` | Adoption, rules reference, baseline, CLAUDE.md paragraph, hooks |
| `docs/decisions/` | ADRs — one file per decision that shaped the code |
| `src/archview/` | The tool: `extract/` (grimp + ast → model), `model/` (tree, view, cycles, layers, metrics, JSON), `rules/` (config, check, init, baseline), `render/` (DOT, Mermaid, check output), `server/` + `ui/` (viewer), `cli.py` |
| `tests/` | Unit tests, a fixture project covering the awkward import shapes, and golden JSON/DOT |
| `spike/` | `arch_graph.py`: the original one-file spike. `viewer/view.py`: a drill-down HTML viewer for any repo |

## Try it

```bash
uv tool install --editable .                              # once: `archview` on the PATH
cd ~/git/some-repo && archview .                          # interactive viewer in the browser
uv run archview serve ~/git/some-repo --watch             # same, redrawing on file changes
uv run archview init ~/git/some-repo && uv run archview check ~/git/some-repo
uv run archview graph ~/git/some-repo --root pkg --json   # machine-readable view
uv run archview metrics ~/git/some-repo
```

## Continue in Claude Code

```bash
cd ~/git/arch-viewer
claude
```

A good next prompt:

> Read AGENTS.md and the docs in the order it lists. Then start milestone M6 from docs/05-approach-and-roadmap.md: a spike comparing tree-sitter-typescript and the TypeScript compiler API on a real frontend repo, ending in an ADR, and keep `archview check` passing on this repo.

Suggested working style, borrowed from Bob (35:46–41:36): do a story or two, look at the result, reorganise, repeat — not a big up-front plan.
