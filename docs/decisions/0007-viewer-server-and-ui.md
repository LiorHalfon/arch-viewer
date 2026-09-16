# 7. Viewer: FastAPI server, plain-JS UI, Graphviz in the browser

Date: 2026-09-16 (M3)

## Status

Accepted.

## Context

M3 needs `archview serve`: a local page that draws one root at a time, drills down,
shows the imports behind an edge and opens source. `docs/05` left open whether to
use the stdlib `http.server` or FastAPI, and how the browser gets its libraries
without network access at runtime (N3).

## Decision

- **Server: FastAPI + uvicorn** (Lior, 2026-09-16: new dependencies are fine). It is
  bound to `127.0.0.1` by default, and a free port is picked if 8765 is taken.
  `server/workspace.py` holds one analysed project and caches the view for each
  root. `server/app.py` is a thin HTTP layer over it:
  `GET /api/project`, `GET /api/view?root=`, `GET /api/source?module=`,
  `POST /api/reanalyze`, and `/` + `/ui/*` for static files.
- **Source is served only for modules in the model.** A module name that is not in
  the model returns 404, so there is no path from a query string to an arbitrary file.
- **UI: static HTML/CSS/JS, no build step.** `@viz-js/viz` 3.30.0 (MIT) and
  highlight.js 11.11.1 (BSD-3) are vendored in `ui/vendor/` (see `VERSIONS`), so the
  page makes no network requests.
- **The DOT stays the single drawing spec.** `render/dot.py` adds `class` attributes
  (`package`, `module`, `cycle`, `tangled`). The UI restyles the SVG through them
  for light and dark themes, and `archview graph --dot | dot -Tsvg` keeps its own
  colours. Packages are drawn as UML components.
- **"Cycle somewhere inside"** (V6: red names for subtrees containing a cycle) comes
  from `model/view.tangled_packages`. It builds the view of every package once
  per analysis: 0.04 s on `tiny-tale-backend` (281 modules, 1040 imports).
- **Navigation lives in the URL hash** (`#/pkg.sub`), so browser Back/Forward work.
  Each root remembers its zoom and scroll position (V4). Click a package to drill
  down, click a module for its source, click an edge for its imports.
  Click an import to open the file at that line. In the source panel, click a
  highlighted line number to jump to the imported module.

## Consequences

The `server` component depends on `model`, `project` and `render`, and `cli`
depends on `server`. `archview.toml` declares both. When ELK/React Flow is needed
(V10 interactions), the `/api` JSON stays and only `ui/` is replaced.
