# M13 design: the viewer draws its own diagram

Date: 2026-10-09. Status: implemented in M13 (ADR 0017).

Four changes to `archview serve`, picked from a page of live mockups built on
tiny-tale-backend's real views (ideas 1, 2, 4 and 6 of seven):

1. **Colour by**: boxes are coloured by role (the default), instability or zone, and
   the legend says what each colour means. Clicking a legend row picks out that group.
   A panel explains instability, abstractness and the zones.
2. **Drag boxes**: any box can be moved. On drop, Graphviz routes the lines again around
   the boxes where they now stand. Positions are remembered per view, and Reset layout
   puts the Graphviz layout back.
3. **Line weight and direction**: a line's width grows with its import count. Hovering
   a box colours what it imports blue and what imports it violet, and a hover card
   replaces the browser tooltip.
4. **Quick find**: `/` searches every package and module, opens the level that draws the
   match and flashes it.

The other archview on PyPI (lm17918/archview, Cytoscape.js + dagre) has colour by role
and dragging. Its first frame is spread out because dagre lays out every folder open and
then folds them, so closed folders keep the spacing they had when open. Our first frame
stays Graphviz's compact layout.

Idea 7, "what changed since main" with an `archview diff` command, is the next
milestone, with its own spec. Ideas 3 (open a package in place) and 5 (layer bands) were
not taken.

## Decisions taken in brainstorming

- Role is the default colouring. The choices are Role, Instability, Zone and None. None
  is today's look. Layer was in the mockup and is dropped: it did not help.
- Role names: entry point, in between, foundation, on its own.
- An abstract box shows its name in italics under every scheme. The green fill stays
  only under None, since under the other schemes the fill carries the scheme's colour.
- Instability and Zone get an explanation: a link under the legend's buttons opens a
  panel with the view's boxes plotted by instability and abstractness, and what each
  number means. The same text, longer and with examples, goes into `docs/metrics.md`.
- Dragged positions live in the browser's `localStorage`, per project and view. The
  viewer never writes files into the repo it analyses.
- SVG and PNG exports draw what is on screen: the dragged layout and the colour scheme,
  in light colours. DOT and Mermaid exports do not change.
- Lines keep their count labels, since width only shows rough size.
- In quick find, Enter shows the box. A module's source stays one click away.
- One server change: `/api/view` gains a `threshold` field, the zone threshold the
  metrics chart shades by. `render/dot.py`, `archview graph --json` and their goldens
  do not change.

## Approach

Keep Graphviz for layout and draw the SVG ourselves from its JSON output.

Today `draw()` calls `viz.renderSVGElement(view.dot)` and restyles Graphviz's SVG through
the `class` attributes `render/dot.py` sets. That SVG cannot be re-routed after a drag,
and a line's width cannot follow its count without new DOT attributes per edge. The new
`draw()` calls `viz.renderJSON(view.dot)` with the same DOT. That gives each box's centre
and size, each cluster's bounding box, and each edge's spline, arrow tip and label
position. The UI then builds its own SVG. On drop, the UI builds a second, small DOT with
every box pinned where it stands and asks `neato` to route the edges only.

The first frame is the same Graphviz layout as today, and the DOT stays the single
layout spec: `archview graph --dot` and the viewer still lay out from the same text.

Two alternatives were rejected:

- **Cytoscape.js + dagre**, as the other archview does. Dragging comes built in, but the
  screen would no longer match `archview graph --dot`, the spread-out first frame is a
  dagre compound-layout problem we would inherit, and it adds about 400 KB of vendored
  JavaScript.
- **ELK + React Flow**, the upgrade path ADR 0007 and `docs/05` named for V10. It needs
  a build step, which the UI has avoided so far, for features this milestone gets from
  Graphviz.

ADR 0017 records the decision and amends ADR 0007.

## 1. Drawing from Graphviz's layout

`layout.js` turns `viz.renderJSON(dot)` into plain data, with y flipped to screen
coordinates:

- `nodes[id] = {x, y, w, h}`, centre and size in points (`width`/`height` × 72).
- `clusters[] = {id, x, y, w, h}` for the `cluster_*` subgraphs `render/dot.py` emits
  around a package and its published components (ADR 0013).
- `routes["source>target"] = {points, tip, label}`: the B-spline control points, the
  arrow tip (`e,` point) and the count label's position (`lp`).
- `w, h` from `bb`.

`draw.js` turns a view payload plus a layout into SVG markup:

- A package is a UML component (a rounded box with two small tabs on its left edge), a
  module a rounded box and a third-party package a dashed box, as today. Name and module
  count are two lines of text. Red names for `in_cycle` and `tangled`, and the `⟲` mark,
  as today.
- An edge is a cubic Bézier path through the route's points, an arrowhead built from
  the tip and the last control point (solid, or hollow for `abstract`), and its count.
  Cycle edges are red, rule breaks orange and dashed, type-checking-only edges dotted, as
  today.
- Clusters are rounded frames drawn under the boxes.
- The DOM keeps today's contract, so focus, pinning, selection and the panels keep
  working: one `g.node` per box with `data-id`, one `g.edge` per edge with `data-source`
  and `data-target`, a wider transparent `path.hit` under each edge for clicking, and the
  same class names (`package`, `module`, `external`, `cycle`, `tangled`, `abstract`,
  `violation`, `typing`).
- Colours are CSS variables, so the dark theme works as today. A label's colour is
  whichever of dark ink `#1d232b` and white has the higher contrast with its box's fill.
  (`--text` is light in the dark theme, so it cannot be one of the two.) A theme
  change redraws, since that choice is made in code.

The edge `<title>` tooltips stay. A box's `<title>` becomes an `aria-label`, since the
hover card (section 5) replaces it.

Zoom keeps working as today: the SVG has a `viewBox`, and `setZoom()` sets its width and
height.

## 2. Colour by

`colour.js` holds the schemes. Each scheme sorts a box into one class and gives the
class a name, a note and a fill token.

**Role** comes from the edges drawn in the current view, so it changes as you drill down.

| Class | Rule | Light | Dark |
|---|---|---|---|
| entry point | imports a box in this view; no box in this view imports it | `#2a78d6` | `#3987e5` |
| in between | imports and is imported, within this view | `#1baf7a` | `#199e70` |
| foundation | is imported; imports no box in this view | `#eda100` | `#c98500` |
| on its own | no lines either way | grey (`--border`) | grey (`--border`) |

Edges to and from third-party boxes do not count for roles. "On its own" is a grey fill
rather than the mockup's dashed border, so it cannot be mistaken for a third-party box.
Instability's and Zone's "no dependencies" use the same grey.

**Instability**: five bins, 0 to 0.2 up to 0.8 to 1, on one blue ramp (light
`#b7d3f6 #86b6ef #3987e5 #256abf #104281`, dark `#184f95 #256abf #3987e5 #6da7ec
#b7d3f6`), plus "no dependencies" for a box whose I is undefined. The first and last
rows carry the notes "stable, others lean on it" and "unstable, leans on others".

**Zone**: main sequence (plain fill), zone of pain (`--pain`), zone of uselessness
(`--useless`), no dependencies. Today zone colouring reaches packages only. It now
reaches modules too, since they have the same metrics.

**None**: today's fills. Package blue, module white, abstract green.

Third-party boxes keep their dashed look under every scheme, and no legend row counts
them.

The role and ramp colours passed the dataviz palette validator against both surfaces
during brainstorming. The final set, zone fills included, is validated again during
implementation. Orange and red stay reserved for rule breaks and cycles.

**The legend** stays in the canvas's bottom-right corner and keeps the View → Legend
switch. From top to bottom:

- "Colour by" as four buttons: Role, Instability, Zone, None.
- One row per class: swatch, name, note, and how many boxes in this view have it. A
  class with none is greyed. Clicking a row pins a focus on that group through the
  existing `pin()`, so the notes bar reads "Focus: entry points [Clear]" and Esc clears
  it.
- Under Instability or Zone, a link: "What is instability?" or "What are the zones?"
  (section 3).
- "Lines", collapsed, holding today's line legend plus "thicker: more imports".

The View menu's "Colour by metric zone" checkbox becomes a "Colour by" radio group
that mirrors the legend's buttons, so the scheme can change while the legend is hidden.
The choice is saved in `archview.options` as `colour`. A saved `zones: true` from an
older version reads as `colour: "zone"`.

## 3. The metrics panel

The panel opens in the existing side panel, where the metrics table and node details
already open. The mockup showed it under the diagram; the side panel keeps the diagram
fully visible and gives the panel's text room. Three ways in: the legend link, a "What
do these mean?" link in the metrics table's header, and the same link beside the I/A/D
rows of a box's details.

Contents, top to bottom:

- **A chart of the current view.** Instability across and abstractness up, both 0 to 1.
  The zone of pain (A + I < 1 − threshold) and the zone of uselessness (A + I > 1 +
  threshold) are shaded. The main sequence is a dashed diagonal. The threshold is the one
  the model used (`[archview.metrics] threshold`, default 0.3), sent as the view
  payload's `threshold`. Each box is a dot; boxes
  at the same point share one dot labelled "name +N". Labels sit beside their dot,
  nudged up or down past earlier labels with a leader line, and a label with no free
  spot shows on hover only. Third-party boxes and boxes with undefined I are left out.
- **The counts**: how many boxes in this view are in each zone.
- **Instability, I.** I = Ce ÷ (Ca + Ce): Ce counts the modules outside the box that it
  imports, Ca the modules outside it that import it, over the whole project, not just
  this view. 0 means others import it and it imports nothing, so a change can break
  everything that depends on it. 1 means nothing imports it, so nothing breaks when it
  changes.
- **Abstractness, A.** The share of a box's modules that are abstract. A Python module
  counts when it defines a class that subclasses `Protocol` or `ABC`, uses
  `metaclass=ABCMeta`, or has an `@abstractmethod`. A TypeScript file counts when it has
  an `abstract class` or exports only types. One such class is enough.
- **Zones.** Code much else depends on should be abstract, so a change lands behind an
  interface; code nothing depends on can be concrete. Healthy boxes sit near the
  diagonal, D = |A + I − 1| measures the distance, and past the threshold a box is in a
  zone. The zone of pain (stable and concrete) is fine for code that rarely changes, such
  as config or data models. The zone of uselessness is abstract code little or nothing
  uses.
- One line naming `docs/metrics.md` for the longer version. It is not a link: the page
  works the same offline (N3).

Hovering a dot focuses its box in the diagram, as hovering the box does, and hovering a
box marks its dot. Clicking a dot flashes the box. The chart redraws when the view
changes while the panel is open.

## 4. Dragging

**Interaction.** Pointer down on a box and move more than 4 px, and it is a drag;
anything less is a click, which keeps today's meaning (open a package, open a module's
source, shift-click for details). While dragging, the box follows the pointer
(`getScreenCTM()` handles the zoom) and its own lines follow as straight dashed lines.
The other lines stay. The hover card hides during a drag.

**On drop**, the lines are routed again:

- A view of at most 100 boxes re-routes every line with `neato`: every box pinned with
  `pos="x,y!"` at its current place and size (`fixedsize=true`, `label=""`), graph
  attributes `splines=true overlap=true inputscale=72 esep="+4"`. neato shifts the whole
  drawing by a constant, so the result is moved back by the difference between one
  box's output and input positions.
- A bigger view draws the moved box's lines as straight lines from border to border, in
  JavaScript. The other lines keep their routes.

The limit comes from timing the vendored viz 3.30.0 in Node:

| View | Boxes | Lines | neato, all lines | Straight lines |
|---|---|---|---|---|
| `src` (tiny-tale) | 8 | 13 | 1.5 ms | 1.1 ms |
| `src.story_generator.providers` | 15 | 41 | 3.7 ms | 2.4 ms |
| synthetic | 100 | 300 | 227 ms | 14 ms |
| synthetic | 300 | 1000 | 4.9 s | 48 ms |

Routing only the moved box's lines does not save the large case (808 ms for 15 lines
among 300 boxes): the cost follows the number of boxes. tiny-tale's largest view has 15
boxes.

**The view grows to fit.** After a drop the `viewBox` is the bounding box of every box,
frame and line plus a margin, so a box dragged past the edge stays reachable by
scrolling. A cluster frame follows its members: its rectangle is their bounding box
plus Graphviz's cluster margin. Members move one at a time; a frame cannot be dragged
as a whole.

**Saved layouts.** `localStorage["archview.layout.v1"]` maps a view key to the moved boxes
only, `{id: [x, y]}` in layout points. The key is
`repo|project|package|root|externals|hide_tests`, since the last two change which boxes
the view has. When a view is drawn, saved positions replace Graphviz's for the boxes that
still exist, saved boxes that no longer exist are ignored, and the lines are routed as
on a drop. Storage that is missing or throws (private windows, blocked site data) means
nothing is saved, and dragging still works.

`localStorage` belongs to the browser and the address, so a layout follows the port. The
server keeps 8765 unless it is taken, and the existing options behave the same way.

**Reset layout** is a toolbar button, enabled when the current view has moved boxes. It
deletes that view's entry and draws Graphviz's layout again.

**Reanalysis** (the button, `r`, or `--watch`) lays the view out again with `dot` and
re-applies the saved positions. A box the analysis added takes Graphviz's position, and
it can land on a moved box. Reset layout is the remedy; the spec does not try to avoid
that overlap.

## 5. Line weight, direction, hover card

**Width**: `min(6, 1 + log2(count) / 1.8)` px at zoom 1. One import is 1 px, 10 imports
about 2.8 px, 94 about 4.6 px. Cycle and rule-break edges are at least 2 px, as today.

**Direction**: while one box is focused (the hovered box, or the box Focus neighbours
was pinned on), the lines it imports through turn `--accent` blue and the lines that import it turn violet (`--in`:
light `#8b3fd1`, dark `#b48cf2`). Their counts turn bold. A cycle edge stays red and a
rule-break edge stays orange, so neither warning is hidden by the direction colour.

**Hover card**: shown beside the hovered box, on its right or its left if there is no
room, inside the canvas. Contents:

- name, "abstract" when it is, kind and module count, layer;
- imports: N boxes · M imports (blue label), imported by: N boxes · M imports (violet);
- instability, abstractness and distance as small bars with their values;
- the zone as a chip;
- one hint line: "click to open" or "click for source", "drag to move", "shift-click
  for details".

A third-party box's card shows the name, "third-party package" and the import counts.

## 6. Quick find

`/` or a toolbar "Find" button opens a search box floating at the canvas's top left.
Esc or a pick closes it. The `/` key is ignored while typing in a field, as the other
shortcuts are.

**Data.** The trees the file drawer already fetches. The project's whole tree is
`/api/tree?root=<project>`. At a workspace's top level, which has no tree, the box
searches each member's tree (`/api/tree?package=<member>`). Trees follow Hide tests and
are fetched once per setting, then cached with the drawer's trees. `find.js` flattens a
tree to `{id, name, kind, parent, package}` from the nesting itself, so Python's `.` and
TypeScript's `/` need no separator logic.

**Ranking.** A name that starts with the query first, then a name that contains it,
then a dotted path that contains it. Ties go to the shallower item, then packages before
modules, then the id in alphabetical order. Ten results show, each with its name (the
match in bold), its parent path, and "package, N items" or "module". ↑ ↓ move, Enter or a
click picks.

**A pick** opens the level that draws the match, which is the match's parent (with its
member's `package` in a workspace), and flashes the box: two pulses of an accent ring,
or a steady ring for 1.5 s under `prefers-reduced-motion`. If the match is the root
being shown, the view stays put. A match with no parent (the project package, or a
workspace member's own package) opens the top level and flashes there.

## 7. Export

SVG and PNG come from `draw.js` in export mode. It produces the same drawing as the
screen with the light palette written into each element, so the file needs no
stylesheet. It uses the current positions, routes and colour scheme, and adds a compact
legend for the scheme under the drawing unless the scheme is None. Focus and dimming
are not exported. PNG renders that SVG to a canvas at 2× as today. Mermaid and DOT are
unchanged, still from `/api/export`.

## 8. Code layout

The UI stays plain files with no build step. `app.js` becomes an ES module
(`<script type="module">`) that imports the new modules. `viz-global.js` and highlight.js
stay classic scripts with their globals.

| File | Holds | DOM |
|---|---|---|
| `ui/layout.js` | Graphviz JSON → layout data; the pinned DOT; neato's offset correction | no |
| `ui/draw.js` | view + layout → SVG markup, for the screen or for export | no |
| `ui/colour.js` | schemes, roles, bins, legend rows and counts | no |
| `ui/find.js` | flatten trees, rank matches | no |
| `ui/chart.js` | the metrics chart's markup and label placement | no |
| `ui/drag.js` | pointer handling, straight-line preview, drop, saved layouts | yes |
| `ui/widgets.js` | the legend, the hover card, the find box and the metrics panel | yes |
| `ui/app.js` | today's wiring, navigation and panels, calling the modules above | yes |

The modules without DOM work on plain data and return data or markup strings, so Node
can test them. `app.js` is 927 lines today; the new UI goes in `widgets.js` and
`drag.js` so it does not grow much past that.

## 9. Order of work

1. Draw from Graphviz's JSON with today's look and behaviour, and nothing else. This is
   the checkpoint: every existing interaction works on the new drawing before a feature
   lands on it.
2. Line weight, direction colours and the hover card.
3. Colour by, the legend and the metrics panel, then `docs/metrics.md`.
4. Dragging, saved layouts and Reset layout.
5. Quick find.
6. Export from the drawing.
7. Docs and the ADR.

## 10. Docs

- ADR 0017: the viewer draws its own SVG from Graphviz's layout. It amends ADR 0007's
  "the DOT stays the single drawing spec" to "the DOT stays the single layout spec", and
  its consequence that dragging needs ELK and React Flow. ADR 0007's status line points
  to it.
- `docs/02-requirements.md`: V8 (abstract boxes: italic name, and the green fill under
  None) and V11 (colour by zone becomes one scheme; the metrics panel) change. New:
  V16 colour by with a clickable legend, V17 drag with saved layouts and Reset, V18 line
  weight, direction and the hover card, V19 quick find. The implementation status
  table moves to "after M13".
- `docs/05-approach-and-roadmap.md`: the M13 row, and the viewer section's upgrade-path
  paragraph.
- `docs/metrics.md`, new: what `archview metrics` prints, and how to read I, A, D and
  the zones, with tiny-tale-backend's `src` as the example.
- `docs/06-using-archview-in-a-repo.md`: the viewer's new controls (Colour by, drag and
  Reset layout, `/`).
- `AGENTS.md`: the state line, and the viewer line under "Decisions already made".

## Testing

- **JavaScript units**, run with `node --test tests/ui/` and wrapped in a pytest test
  marked `requires_node`, so `uv run pytest` runs them and CI (Node 24) always does:
  - `layout.js`: a small DOT with a cluster, rendered by the vendored `viz-global.js` in
    Node. Positions are flipped, sizes are in points, the cluster frame is found, and
    every edge has a route, tip and label. A pinned re-route keeps every box within
    0.5 pt of where it was put and returns a route for every edge.
  - `colour.js`: each role on a hand-built edge list, third-party edges ignored; the
    instability bins at their edges (0.2 goes to the second bin, 1 to the last, undefined
    to "no dependencies"); zone classes; legend counts.
  - `find.js`: ranking order and every tie-break; a TypeScript tree with `/` ids; a
    workspace's members searched together, each match carrying its member.
  - `chart.js`: shared points grouped, labels inside the chart and not overlapping, an
    unplaceable label marked hover-only.
  - `draw.js`: one `g.node` and `g.edge` per box and edge with the right data
    attributes and classes, widths rising with count, the italic name for abstract boxes,
    and an export with no `var(` in it.
  - Saved layouts: a saved box that no longer exists is ignored, and storage that throws
    does not break drawing.
- **Server**: `test_serves_the_page_and_its_vendored_scripts` checks for the module
  script tag and that every new module is served. `/api/view` carries `threshold`: the
  rules file's value, 0.3 without one, and 0.3 at a workspace's top level.
- **In the browser**, before calling it done: tiny-tale-backend, this repo, the
  `workspace` fixture (clusters, quick find across members) and a TypeScript project, in
  light and dark. Check the role colours and legend counts, a pick-out and Clear, a drag
  and its re-route, a reload keeping the layout, Reset layout, the hover card and
  direction colours, `/` and a pick, the metrics panel's chart against the metrics table,
  and an SVG and a PNG export of a dragged view.
- `tests/test_self_check.py` and `archview check` still pass. No Python package
  dependency changes, so `archview.toml` needs no edit.

## Release

`pyproject.toml` already says 0.5.0 (commit 8e7bfef, after the M12 merge), and `v0.5.0`
is not tagged yet. M13 ships in that release: after the merge, tag `v0.5.0` and push the
tag. No second version bump.

## Not in this milestone

- Idea 7, what changed since a git ref, and `archview diff`: the next milestone.
- Opening a package in place (idea 3, the rest of V10) and layer bands (idea 5).
- Moving a box with the keyboard.
- Saving a layout into the repo, or sharing one between browsers.
- Dragging a cluster frame as a whole.
- Routing in a Web Worker. The 100-box limit keeps a drop under about 250 ms in Node;
  the browser check measures it again.
- A hover card for edges. Edges keep their tooltips and the click-through panel.
