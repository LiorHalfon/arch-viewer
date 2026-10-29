# 22. The public demo is a static snapshot of the viewer

Date: 2026-10-28

## Status

Accepted. Adds V21.

## Context

The README shows the viewer as a GIF. To try it, a visitor has to install archview and
clone the repo. A link that opens the real viewer on `examples/pizzeria`, with nothing to
install, shows more than the GIF can: every box can be clicked, every line opened.

The viewer is plain ES modules with Graphviz in the browser (ADR 0017). Its one moving
part is the local FastAPI server, which answers six GET requests from the analysed
model: `project`, `view`, `tree`, `check`, `source` and `export`. For one project those
answers are a finite set. The pizzeria has 8 packages, each drawn four ways (Hide tests
and third-party packages on or off), 23 source files and one check report: 137 answers,
about 190 KB of JSON.

## Decision

- **The demo is a static site, built from the code on every push to `main`.**
  `server/snapshot.py` asks `ViewerState`, the object `archview serve` uses, for every
  answer and writes them to `snapshot.json` beside a copy of `ui/`.
  `scripts/build_pages.py` builds the pizzeria's, and `.github/workflows/pages.yml`
  publishes it to GitHub Pages. What the server would refuse with a 404 is left out:
  the check without a usable rules file, or the tree of a package that holds only tests
  once tests are hidden. So any single project bakes, tests and all.

- **An answer's key is its endpoint and parameters, sorted by name and unencoded:**
  `view?hide_tests=true&root=pizzeria.kitchen`. Sorting frees the key from the order the
  UI happens to set parameters in. Leaving it unencoded frees it from the ways Python
  and the browser percent-encode differently, which matters once a TypeScript id with
  `/` or `@` is in a key. `server/snapshot.py` and `ui/snapshot.js` each build the key,
  and their tests pin the same strings.

- **A meta tag switches the viewer into snapshot mode.** The built `index.html` carries
  `<meta name="archview-snapshot" content="snapshot.json">`. With it, `app.js` loads the
  file once and `api()` answers from it; a request it lacks says it is "not part of this
  demo". Reanalyze is hidden. The page served by `archview serve` has no tag and works
  as before. Its paths are now relative (`ui/app.js`), because Pages serves the site
  under `/arch-viewer/`.

- **The demo's note lives in the snapshot and opens in the existing side panel.** The
  text is `scripts/pages/about.html`. It opens at start, stays open while its links move
  between views, and the header's About button brings it back.

## Rejected approaches

- **The FastAPI server on a free host** (Render, Hugging Face Spaces). No snapshot to
  build, but the free tiers put the server to sleep, so the first visitor waits tens of
  seconds, and the server was written for localhost: `POST /api/reanalyze` would be
  open to anyone.
- **Cloudflare Pages or Netlify.** The same static build, plus an account outside
  GitHub, for nothing GitHub Pages lacks here.
- **One file per answer, at a path built from the query.** Many files for no gain at
  this size, and the path scheme would have to solve the same encoding question.

## Consequences

- A new endpoint or parameter in the UI needs a line in `answers()`, or the demo answers
  it with "not part of this demo". `tests/test_snapshot.py` pins the full set for the
  pizzeria and checks that the note's links name baked views.
- A workspace cannot be baked yet: `answers()` refuses one. The pieces would carry a
  general `archview` command that publishes any repo's viewer, which is not built.
- The demo follows `main`, so it can show a feature before the release that ships it.
- Pages has to be switched on once in the repo's settings, with GitHub Actions as the
  source.
