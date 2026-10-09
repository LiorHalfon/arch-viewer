# M13 implementation plan: the viewer draws its own diagram

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `archview serve` colours boxes by role, instability or zone with a clickable legend and a metrics panel, lets you drag boxes with Graphviz re-routing and saved layouts, weights lines by import count with direction on hover and a hover card, and finds any package or module with `/`.

**Architecture:** Graphviz still lays out every view from the server's DOT. The UI calls `viz.renderJSON(dot)` and builds its own SVG from the positions, clusters and splines (`layout.js` + `draw.js`), keeping today's DOM contract (`g.node[data-id]`, `g.edge[data-source][data-target]`) so focus, pinning and panels keep working. On drop, a small DOT with every box pinned goes to `neato` to route the lines again.

**Tech Stack:** Plain JavaScript ES modules, no build step; vendored `@viz-js/viz` 3.30.0; Node 24's built-in test runner (`node:test`) for the modules without DOM, wrapped in pytest; Python 3.12+/FastAPI for the one server field.

**Spec:** `docs/superpowers/specs/2026-10-09-viewer-drawing-design.md`. Read it alongside this plan; § numbers refer to it.

## Global Constraints

- No build step and no new dependency, Python or JavaScript. `viz-global.js` and `highlight.min.js` stay classic scripts; every new UI file is an ES module under `src/archview/ui/`.
- The page makes no request beyond `/api/*` and `/ui/*` (N3).
- `render/dot.py`, `archview graph --json|--dot` and every golden file stay unchanged. The only server change is `threshold` in `/api/view` (Task 7).
- Modules without DOM (`layout.js`, `draw.js`, `colour.js`, `find.js`, `chart.js`, and the pure exports of `drag.js`) touch no `document` or `window` at import time, so Node can import them.
- Values the spec pins: `REROUTE_LIMIT = 100` boxes; drag starts past 4 px; line width `min(6, 1 + log2(count) / 1.8)`, at least 2 for cycle and rule-break edges; storage key `archview.layout.v1`, view key `repo|project|package|root|externals|hide_tests`; options key `archview.options` field `colour`, default `"role"`; 10 quick-find results; flash is two 1.1 s pulses, or a steady 1.5 s ring under `prefers-reduced-motion`.
- Colours (light / dark): role entry `#2a78d6`/`#3987e5`, between `#1baf7a`/`#199e70`, foundation `#eda100`/`#c98500`; instability ramp light `#b7d3f6 #86b6ef #3987e5 #256abf #104281`, dark `#184f95 #256abf #3987e5 #6da7ec #b7d3f6`; incoming `#8b3fd1`/`#b48cf2`; "on its own" and "no dependencies" grey `#d9dee5`/`#2e353d`. Task 5's contrast test may force a step lighter or darker; re-run the `dataviz` skill's validator (`scripts/validate_palette.js`, `--mode light` and `--mode dark`) on any change and keep orange and red for rule breaks and cycles.
- Label ink is dark `#1d232b` or white `#ffffff`, whichever contrasts more with the fill.
- Before every commit all four pass: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check .`, `uv run archview check`. Never edit `archview.toml` to make a check pass.
- Deterministic: sort ties by id.
- Prose (docs, ADR, UI copy): the `unslop` skill; no em dashes.
- Version stays 0.5.0 (already bumped on main, not tagged). No bump in this plan.
- Commit messages: imperative mood, no `feat:`/`fix:` prefixes, ending with:

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01G7LKazDMBNjRuV8AY7UnUo
```

## Review Focus

1. Ids with characters that DOT, SVG attributes or CSS treat specially (TypeScript ids such as `src/@types/a.d.ts`, a quote or a backslash): the drawing, the pinned DOT and `CSS.escape` selectors must all survive them. Tests in Task 2 (markup) and Task 8 (pinned DOT).
2. A click right after a drag: releasing a dragged package must not drill into it, and a dragged module must not open its source. Test of the threshold in Task 9, plus its browser check.
3. Browser storage that is missing, full, throws, or holds corrupt JSON: no error, dragging still works, nothing saved. Tests in Task 9.
4. Views with no edges (tiny-tale's `src.common`: 8 boxes, 0 lines), a single box, or no box with an instability: drawing, re-routing and the chart must not fail. Tests in Task 2, Task 8 and Task 7.
5. Label contrast on every scheme fill in both themes: a box name must stay readable on the yellow and the middle blues. Test in Task 5.

## File structure

| File | Change |
|---|---|
| `src/archview/ui/layout.js` (new) | Graphviz JSON → layout; pinned DOT and re-route; straight routes; cluster frames; bounds |
| `src/archview/ui/draw.js` (new) | view + layout → SVG markup, screen or export |
| `src/archview/ui/colour.js` (new) | schemes, roles, classes, legend rows, label ink, light palette, option migration |
| `src/archview/ui/chart.js` (new) | the metrics chart and its label placement |
| `src/archview/ui/find.js` (new) | flatten trees, rank matches |
| `src/archview/ui/drag.js` (new) | drag threshold, saved layouts, pointer handling |
| `src/archview/ui/widgets.js` (new) | hover card, legend, metrics panel, find box |
| `src/archview/ui/app.js` | module; draws through the new files; state for layout, moved boxes, routes |
| `src/archview/ui/index.html`, `app.css` | module script, toolbar buttons, View menu radios, tokens, styles for the new SVG |
| `src/archview/server/state.py` | `threshold` in both view payloads |
| `tests/ui/*.test.mjs` (new), `tests/ui/support.mjs` (new) | Node unit tests |
| `tests/test_ui_js.py` (new), `tests/test_server.py` | the Node wrapper; page and threshold tests |
| docs | ADR 0017, `docs/metrics.md`, requirements, roadmap, docs/06, AGENTS.md |

---

### Task 1: Node tests, and Graphviz JSON → layout

**Files:**
- Create: `src/archview/ui/layout.js`, `tests/ui/support.mjs`, `tests/ui/layout.test.mjs`, `tests/test_ui_js.py`

**Interfaces:**
- Produces, in `layout.js`:
  - `edgeKey(source: string, target: string) -> string`, `` `${source}>${target}` ``.
  - `parseLayout(json) -> Layout`, where `Layout = {w, h, nodes: {[id]: {x, y, w, h}}, clusters: Cluster[], routes: {[edgeKey]: Route}}`, `Cluster = {id, members: string[], x, y, w, h, pad: {l, t, r, b}}` (`x, y` top-left; `pad` is the frame's margin around its members' bounding box), `Route = {points: [x, y][], tip: [x, y] | null, label: [x, y] | null}`. All in points, y pointing down, origin at the top-left of `bb`. `width`/`height` arrive as strings in inches.
  - `layoutView(viz, dot: string) -> Layout`, `parseLayout(viz.renderJSON(dot))`.
- Produces, in `support.mjs`: `loadViz() -> Promise<Viz>` (the vendored UMD file through `createRequire`), `SAMPLE_DOT` (below), `sampleView()` returning a view payload for it: `app` package (2 modules, `in_cycle: false`), `core` package (3 modules, `tangled: true`), `core.api` module (`abstract: true`), edges `app→core.api` (count 4, `abstract: true`) and `app→core` (count 1).

```
digraph "t" {
  rankdir=TB; newrank=true; splines=true; nodesep=0.5; ranksep=0.9;
  node [shape=box style="rounded,filled" fontname="Helvetica"];
  subgraph "cluster_core" { style="rounded"; label=""; "core" [label="core\n(3 modules)" shape=component]; "core.api" [label="api"]; }
  "app" [label="app\n(2 modules)" shape=component];
  "app" -> "core.api" [label="4" arrowhead=onormal];
  "app" -> "core" [label="1"];
}
```

- [ ] **Step 1: Write the failing tests** in `tests/ui/layout.test.mjs` (`node:test`, `node:assert/strict`, a `near(a, b, tol = 0.1)` helper). Expected values come from Graphviz's output for `SAMPLE_DOT` (bb `0,0,212,182`):

```js
test("boxes are flipped to screen coordinates and sized in points", async () => {
  const l = layoutView(await loadViz(), SAMPLE_DOT);
  assert.deepEqual([l.w, l.h], [212, 182]);
  near(l.nodes.core.x, 61); near(l.nodes.core.y, 145.2); near(l.nodes.core.w, 89.9); near(l.nodes.app.y, 20.8);
});
test("a cluster knows its frame, members and margin", async () => {
  const [c] = layoutView(await loadViz(), SAMPLE_DOT).clusters;
  assert.equal(c.id, "cluster_core"); assert.deepEqual(c.members.sort(), ["core", "core.api"]);
  near(c.x, 8); near(c.y, 116.4); near(c.w, 196); near(c.pad.l, 8); near(c.pad.b, 8);
});
test("every edge has a route with its arrow tip and label", async () => {
  const r = layoutView(await loadViz(), SAMPLE_DOT).routes[edgeKey("app", "core.api")];
  assert.equal(r.points.length % 3, 1); near(r.tip[0], 161.3); near(r.tip[1], 126.7); near(r.label[1], 83);
});
```

- [ ] **Step 2: Write `tests/test_ui_js.py`**: one test, `test_the_ui_modules_pass_their_node_tests`, marked `requires_node` (from `tests.typescript_support`), that runs `["node", "--test", "tests/ui/*.test.mjs"]` from the repo root (Node expands the glob) and asserts return code 0, showing stdout and stderr on failure.

- [ ] **Step 3: Run** `node --test "tests/ui/*.test.mjs"`. Expected: fails, `layout.js` not found.

- [ ] **Step 4: Implement** `layout.js`. Objects before nodes in `objects[]` are subgraphs; map `_gvid` to name for `cluster.nodes` and for edge `tail`/`head`. In an edge's `pos`, an `e,x,y` item is the tip, an `s,` item is skipped, and the rest are spline points.

- [ ] **Step 5: Run** `uv run pytest tests/test_ui_js.py -q`. Expected: PASS.

- [ ] **Step 6: Commit** "Read Graphviz's JSON layout in the viewer, with Node tests".

---

### Task 2: `draw.js`, today's look

**Files:**
- Create: `src/archview/ui/draw.js`, `tests/ui/draw.test.mjs`

**Interfaces:**
- Consumes: `Layout`, `Route`, `edgeKey` (Task 1).
- Produces:
  - `drawSvg(view, layout, opts = {}) -> string`, an `<svg>` element's markup. `opts`: `positions` (`{[id]: {x, y}}`, default the layout's), `routes` (default `layout.routes`), `clusters` (default `layout.clusters`), `box` (`{x, y, w, h}`, default `{0, 0, layout.w, layout.h}`, becomes the `viewBox`), `scheme` (default `"none"`), `weighted` (default `false`), `mode` (`"screen"` | `"export"`, default `"screen"`), `palette` (`{[token]: hex}`). This task implements `scheme: "none"`, unweighted, screen.
  - `edgeGeometry(route: Route, width: number) -> {d: string, arrow: string, label: [x, y] | null}`: `d` is `M p0 C p1 p2 p3 …`; `arrow` is the polygon's points, from the last spline point to the tip, half-width `3.4 + width * 0.55`.
  - The DOM contract, in drawing order: `g.cluster` (a `rect`), then per edge `<g class="edge [cycle] [violation] [typing] [abstract]" data-source data-target><title>source->target</title><path class="hit"/><path class="line"/><polygon class="arrow"/><text class="count"/></g>`, then per box `<g class="node {kind} [cycle] [tangled] [abstract]" data-id><title>{id}</title><rect class="ring"/>{shape with class "shape"}<text class="name"/>[<text class="sub"/>]</g>`. A package's shape is a rounded rect with two 8×5 tabs on its left edge, a module a rounded rect, an external a dashed rounded rect. A package's name gets ` ⟲` when tangled and its `sub` line reads `(1 module)` or `(N modules)`; modules and members of a cluster other than its package show the name only (as `render/dot.py`'s `_label`). Text is Helvetica 14px, centred.
  - Every attribute value is escaped (`& < > " '`).

- [ ] **Step 1: Write the failing tests** using `sampleView()` and the sample layout:

```js
test("one node group per box, with its id and classes", ...);  // 3 × class="node ; data-id="core.api"; class="node module abstract"; class="node package tangled"
test("one edge group per edge, hit path under the line", ...);  // data-source="app" data-target="core"; "hit" index < "line" index within the group
test("an abstract edge gets a hollow arrow class", ...);         // the app>core.api group has class "edge abstract"
test("package labels carry the module count and the tangle mark", ...);  // "core ⟲" and "(3 modules)"
test("a view with no edges draws its boxes only", ...);         // Review Focus 4: drop both edges; no class="edge
test("ids with quotes and slashes are escaped", ...);           // Review Focus 1: id `src/@types/a"b.ts` → data-id="src/@types/a&quot;b.ts"
```

- [ ] **Step 2: Run** `node --test "tests/ui/*.test.mjs"`. Expected: the new tests fail.

- [ ] **Step 3: Implement** `drawSvg` and `edgeGeometry`. Fills and strokes are left to `app.css` classes in this task.

- [ ] **Step 4: Run** the Node tests. Expected: PASS.

- [ ] **Step 5: Commit** "Draw a view's SVG from the Graphviz layout".

---

### Task 3: the viewer draws through `draw.js` (the checkpoint)

**Files:**
- Modify: `src/archview/ui/app.js` (`draw`, `wire`, `start`), `src/archview/ui/index.html`, `src/archview/ui/app.css` (the "diagram" block), `tests/test_server.py` (`test_serves_the_page_and_its_vendored_scripts`)

**Interfaces:**
- Consumes: `layoutView`, `drawSvg`.
- Produces: `state.layout` (the current view's `Layout`); `draw(view)` sets it and `state.natural` from the drawn `box`. `wire()` reads `data-id` / `data-source` / `data-target` instead of parsing `<title>`, and still writes today's tooltip texts into the titles.

- [ ] **Step 1: Update the page test**: the page has `<script type="module" src="/ui/app.js"></script>`, and `/ui/layout.js` and `/ui/draw.js` return 200 with a JavaScript content type.

- [ ] **Step 2: Run** `uv run pytest tests/test_server.py -q`. Expected: the page test fails.

- [ ] **Step 3: Implement.** `index.html` loads `app.js` as a module after the two classic scripts. `app.js` imports from `./layout.js` and `./draw.js`; `draw()` replaces `renderSVGElement` with `layoutView` + `drawSvg` inserted through `innerHTML`. Rewrite the CSS diagram rules for `.shape`, `.line`, `.arrow`, `.count`, `.ring` and `.cluster rect` with today's colours, dashes and hover/selected/focusing behaviour; drop the rules that target Graphviz's own `polygon`/`path` markup. Export keeps `renderString` until Task 11.

- [ ] **Step 4: Run** all four checks. Expected: pass.

- [ ] **Step 5: Check parity in the browser** on `uv run archview serve ~/git/tiny-tale-backend --no-open`, `tests/fixtures/workspace` (clusters, the top level) and `tests/fixtures/nested` (a rule-break edge), light and dark. Every one of these must behave as on main: drill down and crumbs; Back restores zoom and scroll; click a module (source), an edge (imports), shift-click a box (details); hover focus; Focus neighbours, What it reaches; a cycle in the notes highlights; red cycle edges and names; orange dashed rule break; dotted type-checking edge; dashed third-party boxes with "Show third-party packages"; zoom −, +, Fit; Esc. Take screenshots with Claude in Chrome. Fix any difference before going on.

- [ ] **Step 6: Commit** "Draw the viewer from Graphviz's JSON, with today's look".

---

### Task 4: line weight, direction, hover card

**Files:**
- Create: `src/archview/ui/widgets.js`
- Modify: `src/archview/ui/draw.js`, `src/archview/ui/app.js` (`focusOn`, `wire`, `tooltip`), `src/archview/ui/app.css`, `tests/ui/draw.test.mjs`

**Interfaces:**
- Produces:
  - `edgeWidth(count: number, {cycle = false, violation = false} = {}) -> number` in `draw.js`. `drawSvg(…, {weighted: true})` writes it as the line's `stroke-width` (two decimals) and sizes the arrow from it.
  - `showCard(host: HTMLElement, node, view, anchor: DOMRect, {drag = false} = {})` and `hideCard()` in `widgets.js`. The card is absolutely positioned in `host` (`.stage-wrap`): right of `anchor`, or left when it would overflow, clamped inside `host`.
  - `focusOn` adds `out` to edges whose source is the focused box and `in` to edges whose target is it. The focused box is the hovered id when one box is focused, else `pinned.root`.
  - Token `--in`: `#8b3fd1` light, `#b48cf2` dark.

- [ ] **Step 1: Write the failing tests:** `edgeWidth(1) === 1`; `near(edgeWidth(10), 2.85, 0.01)`; `near(edgeWidth(94), 4.64, 0.01)`; `edgeWidth(1e6) === 6`; `edgeWidth(1, {cycle: true}) === 2`; a weighted drawing of the sample has `stroke-width="2.11"` on the count-4 line and `stroke-width="1.00"` on the count-1 line.

- [ ] **Step 2: Run** the Node tests. Expected: FAIL.

- [ ] **Step 3: Implement.** `app.js` draws with `weighted: true`. A box's `<title>` goes; `wire` sets its `aria-label` to the old tooltip text and shows the card on `mouseenter`, hides it on `mouseleave` and on every redraw. Card copy (§5): the name, `abstract` when it is, `package, N modules` or `module`, `layer N`; `imports` / `imported by` rows reading `N boxes · M imports` (the label in `--accent` and `--in`); bars for `instability`, `abstractness`, `distance` with two-decimal values, `–` when undefined; the zone chip from `ZONE_NAMES`; a hint joining `click to open` or `click for source`, `drag to move` when `drag`, and `shift-click for details` with ` · `. A third-party box shows its name, `third-party package` and the two import rows. CSS: `.edge.out` lines and arrows `--accent`, `.edge.in` `--in`, counts bold, except `.edge.cycle` and `.edge.violation`, which keep their colours; hover and selected rules on edges change colour only, not width.

- [ ] **Step 4: Run** all four checks, then in the browser on tiny-tale `src`: hovering `webapp` shows `5 boxes · 200 imports` under imports and blue lines; hovering `common` shows violet lines; on `tests/fixtures/sample` a cycle edge stays red while hovered.

- [ ] **Step 5: Commit** "Weigh lines by import count, colour direction on hover, add a hover card".

---

### Task 5: colour schemes

**Files:**
- Create: `src/archview/ui/colour.js`, `tests/ui/colour.test.mjs`
- Modify: `src/archview/ui/draw.js`, `src/archview/ui/app.js`, `src/archview/ui/app.css` (tokens)

**Interfaces:**
- Produces, in `colour.js`:
  - `SCHEMES = ["role", "instability", "zone", "none"]`.
  - `CLASSES = {role, instability, zone}`, each an ordered list of `{key, name, note, token, focus}`. Keys: role `entry`, `between`, `foundation`, `alone`; instability `i0`…`i4`, `isolated`; zone `main_sequence`, `pain`, `useless`, `isolated`. Names and notes as §2 (`entry point` / `nothing here imports it`, …; `0 to 0.2` / `stable, others lean on it` … `0.8 to 1` / `unstable, leans on others`, `no dependencies`; `main sequence` / `balanced`, `zone of pain` / `stable and concrete`, `zone of uselessness` / `abstract and unstable`). `focus` is the pinned focus label: `entry points`, `boxes in between`, `foundations`, `boxes on their own`, `instability 0 to 0.2` …, `boxes on the main sequence`, `zone of pain`, `zone of uselessness`, `boxes with no dependencies`.
  - `roles(view) -> Map<id, key>`: external boxes absent, and edges touching one ignored.
  - `classOf(view, scheme) -> Map<id, key>`; empty for `"none"`; instability bin `min(4, floor(I * 5))`, `null` → `isolated`.
  - `legendRows(view, scheme) -> {key, name, note, token, focus, count}[]`.
  - `fillToken(node, scheme, key) -> string | null`: `null` for externals; under `"none"` `--abs-fill`, `--pkg-fill` or `--mod-fill`; `main_sequence` takes the kind's plain fill.
  - `contrast(hexA, hexB) -> number` (WCAG) and `inkFor(fillHex) -> "#1d232b" | "#ffffff"`.
  - `LIGHT: {[token]: hex}`: the light value of every token `draw.js` writes.
  - `schemeFromOptions(saved) -> scheme`: a valid `saved.colour`; else `"zone"` when `saved.zones === true`; else `"role"`.
- New tokens in `app.css` (light and dark): `--role-entry`, `--role-between`, `--role-foundation`, `--isolated`, `--seq-1` … `--seq-5`.
- `drawSvg` with a scheme: shape fill `var(token)` in screen mode; the name and sub lines in `inkFor(palette[token])` (sub at 75% opacity); `font-style: italic` on an abstract box's name under every scheme.

- [ ] **Step 1: Write the failing tests:**

```js
test("roles come from the lines in this view", ...);
// nodes a, b, c, d, e, x (external); edges a→b, b→c, a→x, e→x
// → a entry, b between, c foundation, d alone, e alone, x absent
test("instability bins include their lower edge", ...);   // 0→i0, 0.2→i1, 0.79→i3, 0.8→i4, 1→i4, null→isolated
test("zone classes leave out third-party boxes", ...);
test("legend rows count the boxes in each class", ...);  // a class with none has count 0
test("an old zones option becomes the Zone scheme", ...); // {zones: true}→"zone"; {colour: "instability"}→"instability"; {colour: "bogus"}→"role"; {}→"role"
test("every scheme fill keeps its label readable in both themes", ...);
// Review Focus 5: read app.css; for each CLASSES token and --pkg-fill, --mod-fill, --abs-fill,
// in the light and dark blocks: contrast(inkFor(hex), hex) >= 4.5
test("the light palette matches app.css", ...);           // every LIGHT entry equals its :root value
test("an abstract box's name is italic under every scheme", ...);
```

- [ ] **Step 2: Run** the Node tests. Expected: FAIL.

- [ ] **Step 3: Implement** `colour.js`, the tokens and the scheme in `drawSvg`. `app.js` keeps `state.options.colour` (loaded through `schemeFromOptions`), builds `palette` from `getComputedStyle` for every `LIGHT` key, and redraws on a `prefers-color-scheme` change. If the contrast test fails for a token, move that step along its ramp until it passes, then re-run the dataviz validator in both modes.

- [ ] **Step 4: Run** all four checks; look at tiny-tale `src` in both themes (3 entry points, 2 in between, 3 foundations).

- [ ] **Step 5: Commit** "Colour boxes by role, instability or zone".

---

### Task 6: the legend and the View menu

**Files:**
- Modify: `src/archview/ui/widgets.js`, `src/archview/ui/app.js` (`applyOptions`, `bind`, `show`, `notes`), `src/archview/ui/index.html` (legend, View menu), `src/archview/ui/app.css` (legend)

**Interfaces:**
- Consumes: `legendRows`, `SCHEMES`, `CLASSES` (Task 5); `pin`, `clearFocus` (app.js).
- Produces: `renderLegend(el, view, scheme, {picked: key | null, onScheme(scheme), onPick(row), onExplain?()})` in `widgets.js`. `state.sticky.pick` holds the picked class key.

- [ ] **Step 1: Implement the markup.** The View menu's "Colour by metric zone" checkbox becomes four radios `name="colour"` (Role, Instability, Zone, None). `#legend` is emptied and filled by `renderLegend`: four buttons (`aria-pressed` on the current one), the rows (swatch, name, note, count; `zero` class at count 0; `aria-pressed` when picked), the link `What is instability?` or `What are the zones?` only under those schemes and only when `onExplain` is given, and a closed `<details>` "Lines" with today's line rows plus `thicker: more imports`.

- [ ] **Step 2: Wire it.** Changing the scheme from either place saves `colour`, redraws and re-renders the legend, and clears a pick. A row click calls `pin(ids of that class, row.focus, true)` and sets `state.sticky.pick`; clicking the picked row again calls `clearFocus()`. Navigation re-renders the legend. View → Legend still hides it.

- [ ] **Step 3: Run** all four checks; in the browser, pick "foundation" on tiny-tale `src` (notes bar `Focus: foundations [Clear]`, three boxes lit), Clear, Esc, switch schemes from the legend and from the menu, reload (the scheme is kept), and set `localStorage["archview.options"] = '{"zones":true}'` then reload (Zone is chosen).

- [ ] **Step 4: Commit** "Choose the colouring in the legend, and pick out a group".

---

### Task 7: the metrics panel

**Files:**
- Create: `src/archview/ui/chart.js`, `tests/ui/chart.test.mjs`, `docs/metrics.md`
- Modify: `src/archview/server/state.py` (`_payload`, `_top_payload`), `tests/test_server.py`, `src/archview/ui/widgets.js`, `src/archview/ui/app.js` (`openMetricsTable`, `openNode`, `wire`, `openPanel`, `closePanel`, new `flash`), `src/archview/ui/app.css` (`.node.flash .ring`)

**Interfaces:**
- Produces:
  - `/api/view` → `threshold: float`: `analysis.project.config.metrics.threshold` in `_payload`, `DEFAULT_THRESHOLD` (`archview.model.metrics`) in `_top_payload`.
  - `chartSvg(view, threshold) -> {svg: string, dots: Dot[]}` in `chart.js`, `Dot = {ids: string[], I, A, x, y, text, label: {x, y, anchor: "start" | "end", leader: boolean} | null}`. Plot area: left 44, top 12, width 268, height 232, bottom 40, right 18. Pain triangle `(0,0) (1−t,0) (0,1−t)`, uselessness `(1,1) (t,1) (1,t)`, dashed diagonal `(0,1)→(1,0)`. Boxes at one point share a dot, text `name +N`.
  - `placeLabels(dots, area) -> dots`: sides right then left (left first when the dot is past 62% of the width), offsets `0, −12, 12, −24, 24, −36, −48`, 6.2 px per character + 2, labels 12 px apart, 7 px clear of other dots, inside the chart; no fit → `label: null`.
  - `renderMetricsPanel(body, view, threshold, {onHoverBox(id | null), onClickBox(id)}) -> {mark(id | null)}` in `widgets.js`.
  - `openMetricsPanel()` in `app.js`; `state.metricsPanel` holds the handle while that panel is open, `null` otherwise.
  - `flash(id)` in `app.js`: adds `flash` to the box's group and removes it on `animationend`. CSS `.node.flash .ring`: two 1.1 s pulses of an `--accent` stroke; under `prefers-reduced-motion`, a steady ring for 1.5 s.

- [ ] **Step 1: Write the failing server test** `test_the_view_carries_the_zone_threshold`: 0.3 with no metrics table; 0.4 after `[archview.metrics] threshold = 0.4` is in the repo's rules file and the state reloads (read the existing rules tests for how they write the file); 0.3 at the workspace top level.

- [ ] **Step 2: Write the failing chart tests:**

```js
test("boxes at one point share a dot", ...);           // three at (0,0) → one dot, text "font_loading +2", ids sorted
test("labels stay inside and apart", ...);             // tiny-tale story_generator's nine (I, A) pairs, listed below
test("a crowded label shows on hover only", ...);      // ten boxes within 0.01 of (0.5, 0.5): some label === null
test("third-party boxes and undefined I are left out", ...);
test("an empty chart says so", ...);                   // Review Focus 4: svg contains "No box in this view has an instability to plot."
test("the zones follow the threshold", ...);           // t = 0.4: the pain triangle reaches x = 44 + 0.6 × 268
```

story_generator's points (I, A): cover (1, 0.143), cover_photo_generator (0.5, 0), font_loading (0, 0), image_storage (0, 1), llm_generated (1, 0), models (0, 0), prompts (0, 0), providers (0.429, 0.147), template_rendered (0.714, 0.069).

- [ ] **Step 3: Run** both. Expected: FAIL.

- [ ] **Step 4: Implement** the field, `chart.js` and the panel. The panel opens through `openPanel` with the title `What instability, abstractness and zones mean` and the root as its sub line; its body is the chart, the zone key, the counts line (`N boxes in the zone of pain, N in the zone of uselessness, N near the main sequence.`), and the Instability, Abstractness and Zones sections with §3's wording; the last line names `docs/metrics.md` as text. Dot hover calls `focusOn` on its first box (`unfocus` on leave unless a focus is pinned), dot click flashes the boxes. Hovering a box calls `state.metricsPanel?.mark(id)`. Navigating with the panel open redraws it. Entry points: the legend's link (pass `onExplain` from Task 6), a `What do these mean?` link in the metrics table's sub line, and the same link after the Zone row of a box's details.

- [ ] **Step 5: Write `docs/metrics.md`:** what `archview metrics` prints (run it on tiny-tale and paste the real table), I, A, D and the zones as in the panel, how to read the chart, `[archview.metrics] threshold`, and the note that a module counts as abstract when one class in it is (ADR 0008), coarser than Bob's count of classes.

- [ ] **Step 6: Run** all four checks; in the browser compare the chart's dots with the metrics table on tiny-tale `src` and `src.story_generator`.

- [ ] **Step 7: Commit** "Explain instability, abstractness and zones in a panel".

---

### Task 8: re-routing around moved boxes

**Files:**
- Modify: `src/archview/ui/layout.js`, `tests/ui/layout.test.mjs`

**Interfaces:**
- Produces, in `layout.js`:
  - `REROUTE_LIMIT = 100`.
  - `pinnedDot(layout, positions, edges: {source, target}[]) -> string`: graph attributes `splines=true; overlap=true; inputscale=72; esep="+4";`, nodes `shape=box fixedsize=true label=""`, each `pos="x,y!"` in Graphviz's y-up points with `width`/`height` in inches. Ids quoted, with `\` and `"` escaped.
  - `rerouteLayout(viz, layout, positions, edges) -> Layout` (neato's output, shifted back by the first box's offset) and `reroute(…) -> routes` (its `routes`).
  - `straightRoute(a: {x, y}, boxA: {w, h}, b, boxB) -> Route`: from border to border; `points` is `[p0, p0, p3, p3]` so it draws as one cubic; `tip` 1 pt outside `b`'s border; `label` at the midpoint, 9 pt to the left of the direction of travel.
  - `routesAfterMove(viz, layout, positions, edges, previous, moved: Set<string>) -> routes`: at most `REROUTE_LIMIT` boxes, `reroute` of every edge; more, `previous` with each edge touching `moved` replaced by `straightRoute`.
  - `clusterFrames(layout, positions) -> Cluster[]`: each frame is its members' bounding box plus its `pad`.
  - `bounds(layout, positions, routes, clusters, margin = 24) -> {x, y, w, h}`.

- [ ] **Step 1: Write the failing tests:**

```js
test("a pinned re-route keeps every box where it was put", ...);  // move app by (+60, +10); every node of rerouteLayout within 0.5 of positions; a route with a tip per edge
test("no edges re-route to nothing", ...);                         // Review Focus 4
test("ids with quotes and backslashes survive the pinned DOT", ...); // Review Focus 1: ids a"b and c\\d; neato succeeds; route key present
test("a big view draws only the moved box's lines straight", ...);   // hand-built layout of 101 boxes, no viz; edges off the moved box keep the same object
test("straight routes start and end on the borders", ...);
test("a cluster frame follows its members", ...);
test("the bounds include a box dragged past the edge", ...);       // x < 0 → bounds.x <= x − w/2 − 24
```

- [ ] **Step 2: Run** the Node tests. Expected: FAIL.

- [ ] **Step 3: Implement** the functions.

- [ ] **Step 4: Run** the Node tests. Expected: PASS.

- [ ] **Step 5: Commit** "Route lines again around pinned boxes".

---

### Task 9: dragging, saved layouts, Reset layout

**Files:**
- Create: `src/archview/ui/drag.js`, `tests/ui/drag.test.mjs`
- Modify: `src/archview/ui/app.js` (`show`, `draw`, `refresh`, `bind`), `src/archview/ui/index.html` (`#reset-layout` after Fit), `src/archview/ui/app.css`

**Interfaces:**
- Consumes: `routesAfterMove`, `straightRoute`, `clusterFrames`, `bounds` (Task 8); `edgeGeometry`, `drawSvg` (Task 2).
- Produces, in `drag.js`:
  - `DRAG_THRESHOLD = 4`; `isDrag(start: {x, y}, now: {x, y}) -> boolean`, true past 4 px.
  - `STORE_KEY = "archview.layout.v1"`; `layoutKey({repo, project, package, root, externals, hideTests}) -> string`, `` `${repo}|${project}|${package ?? ""}|${root}|${externals ? 1 : 0}|${hideTests ? 1 : 0}` ``.
  - `loadMoved(storage, key, ids: Set<string>) -> Map<id, {x, y}>` and `saveMoved(storage, key, moved: Map) -> void`. The stored value is `{[viewKey]: {[id]: [x, y]}}`; an empty map deletes its view key.
  - `enableDrag(svg, {toSvgPoint(event) -> {x, y}, onMove(id, point), onDrop(id, point)})`: pointer handlers on `g.node`, pointer capture, `dragging` class on the svg, and one capture-phase click swallowed after a drag.
- Produces, in `app.js`: `state.moved` (Map) and `state.routes` for the current view; `redraw()` (draw with positions, routes, cluster frames and bounds; update `state.natural`; keep zoom and scroll; re-wire; re-apply a pinned focus).

- [ ] **Step 1: Write the failing tests:**

```js
test("a drag starts past four pixels", ...);                       // Review Focus 2: (0,0)→(3,0) false, (0,0)→(3,3) true
test("the view key names everything that changes the boxes", ...); // "repo|src||src.webapp|0|1"
test("saved boxes that are gone are ignored", ...);
test("storage that throws or holds junk loads nothing", ...);      // Review Focus 3: getItem throws; "{not json"; null
test("saving nothing removes the view and keeps the others", ...);
test("storage that refuses a write does not throw", ...);          // Review Focus 3: setItem throws
```

- [ ] **Step 2: Run** the Node tests. Expected: FAIL.

- [ ] **Step 3: Implement.** `show()` loads `state.moved` for the view (`repo` from the summary) and, when it is not empty, computes `state.routes` with `routesAfterMove(…, layout.routes, moved ids)`. While dragging, the box's group gets a `translate` and each of its edges is redrawn from `straightRoute` with a `preview` class (dashed). On drop: `state.moved.set`, `saveMoved`, `routesAfterMove`, `redraw()`. `#reset-layout` ("Reset layout") is disabled unless `state.moved.size`; it saves an empty map and redraws Graphviz's layout. `refresh()` keeps working through `show()`. The hover card hides while dragging and passes `drag: true`. Log the drop's routing time with `console.debug("archview: rerouted in", ms)` for the browser check.

- [ ] **Step 4: Run** all four checks, then in the browser on tiny-tale `src`: drag `config` left (lines re-route on drop); releasing a dragged `story_generator` does not drill in; reload keeps the layout; Reset layout restores it; a box dragged past the left edge stays reachable by scrolling; in `tests/fixtures/workspace`, a member's cluster frame follows it; Reanalyze keeps the moved box; with devtools' Application tab blocking storage, dragging still works. Record the routing times from the console.

- [ ] **Step 5: Commit** "Drag boxes, keep the layout per view, reset it".

---

### Task 10: quick find

**Files:**
- Create: `src/archview/ui/find.js`, `tests/ui/find.test.mjs`
- Modify: `src/archview/ui/widgets.js`, `src/archview/ui/app.js` (`bind`, `show`), `src/archview/ui/index.html` (`#find` button, `#finder` in `.stage-wrap`), `src/archview/ui/app.css` (finder)

**Interfaces:**
- Produces:
  - `flatten(tree, member = null) -> Entry[]` in `find.js`, `Entry = {id, name, kind, parent: string | null, member: string | null, depth, items}`; `parent` comes from the nesting, `items` is a package's child count (0 for modules).
  - `rank(entries, query, limit = 10) -> Entry[]`: case-insensitive; name starts with the query, then name contains it, then id contains it; ties by `depth`, then packages first, then id. A blank query returns `[]`.
  - `createFinder(host, {load: () => Promise<Entry[]>, onPick(entry)}) -> {open(), close()}` in `widgets.js`: input, list of `name` (match bold), parent path, `package, N items` or `module`; ↑ ↓ Enter, click, Esc.
  - `state.pendingFlash` in `app.js`, consumed at the end of `show()` by `flash(id)` (Task 7).

- [ ] **Step 1: Write the failing tests:**

```js
test("a name that starts with the query comes first", ...);   // "prov": providers, then openai_provider, then providers.openai (only its path matches)
test("ties go shallow, then packages, then id", ...);
test("parents come from the nesting, not a separator", ...);  // a TypeScript tree with ids "src/a/b.ts"
test("workspace members are searched together", ...);         // two flattened trees; each entry carries its member
test("ten results at most, none for a blank query", ...);
```

- [ ] **Step 2: Run** the Node tests. Expected: FAIL.

- [ ] **Step 3: Implement.** `load` fetches `/api/tree?root=<project>` (with `package` inside a workspace member) or, at a workspace's top level, `/api/tree?package=<member>` for each name in the summary's `packages`, through the drawer's `state.trees` cache, so Hide tests applies. A pick sets `state.pendingFlash` and goes to the entry's `parent` (with `member` as the package); with no parent it goes to the top level and flashes the member there, or the project root shows as is. If the target root is the one shown, flash at once. A match that is the root being shown leaves the view as it is. `/` in `bind()`'s key map opens the finder; the toolbar `Find` button has the title `Find a package or module (/)`.

- [ ] **Step 4: Run** all four checks; in the browser on tiny-tale: `/`, type `openai`, Enter opens `providers` and flashes `openai`; Hide tests drops test modules from the results; on `tests/fixtures/workspace`, a match in one member opens inside that member.

- [ ] **Step 5: Commit** "Find any package or module with /".

---

### Task 11: export what is on screen

**Files:**
- Modify: `src/archview/ui/draw.js`, `src/archview/ui/app.js` (`exportView`), `tests/ui/draw.test.mjs`

**Interfaces:**
- Consumes: `LIGHT`, `legendRows`, `inkFor` (Task 5); positions, routes, frames, bounds (Task 9).
- Produces: `drawSvg(…, {mode: "export"})`: `xmlns`, a white background, every fill, stroke and text colour written as a hex from `LIGHT`, the font family on the root, no `class`-dependent styling, no focus state, and under any scheme but `"none"` a legend block (swatch and name per class with boxes) below the drawing, the `viewBox` grown to hold it.

- [ ] **Step 1: Write the failing tests:** an export has `xmlns="http://www.w3.org/2000/svg"` and no `var(`; under `"role"` it contains `entry point`; under `"none"` it has no legend; a weighted export keeps the line widths.

- [ ] **Step 2: Run** the Node tests. Expected: FAIL.

- [ ] **Step 3: Implement** export mode and switch SVG and PNG in `exportView` to it, with the current scheme, positions, routes, frames and bounds. PNG keeps today's 2× canvas.

- [ ] **Step 4: Run** all four checks; export SVG and PNG of a dragged tiny-tale `src` in the dark theme and open both: light colours, the dragged layout, a role legend.

- [ ] **Step 5: Commit** "Export the view as drawn, with its legend".

---

### Task 12: docs, ADR, and the full browser pass

**Files:**
- Create: `docs/decisions/0017-viewer-draws-its-own-svg.md`
- Modify: `docs/decisions/0007-viewer-server-and-ui.md` (status line), `docs/02-requirements.md` (V8, V11, new V16–V19, status table "after M13" with `V1–V9, V11–V13, V15–V19`), `docs/05-approach-and-roadmap.md` (M13 row; the viewer section's upgrade-path paragraph), `docs/06-using-archview-in-a-repo.md` (Colour by, drag and Reset layout, `/`), `AGENTS.md` (state line M1–M13; viewer line under "Decisions already made"; ADR list to 0017), the spec's status line ("implemented in M13 (ADR 0017)")

- [ ] **Step 1: Full browser pass** on tiny-tale-backend, this repo, `tests/fixtures/workspace` and `tests/fixtures/ts-sample` (after `npm ci --prefix tests/fixtures/ts-sample`), light and dark, through every check in §Testing "In the browser". Note the drop routing times.

- [ ] **Step 2: Write the docs.** ADR 0017 follows 0016's shape: context (the mockups, the four ideas, ADR 0007's restyled Graphviz SVG), decision (§Approach, §1, §4's routing rule with the Node timings and the browser times from Step 1), the rejected Cytoscape + dagre and ELK + React Flow, and consequences (one new `/api/view` field; exports now come from the drawing; idea 7 next). V16–V19 use the spec's summaries. Apply the `unslop` skill.

- [ ] **Step 3: Run** all four checks. Expected: pass.

- [ ] **Step 4: Commit** "M13: ADR 0017 and docs".

After the merge to main, and with the user's go-ahead, the release is only `git tag -a v0.5.0` and pushing the tag (spec §Release).
