# 17. The viewer draws its own SVG from Graphviz's layout

Date: 2026-10-09 (M13)

## Status

Accepted. Implements `docs/superpowers/specs/2026-10-09-viewer-drawing-design.md`.
Amends ADR 0007: the DOT stays the single *layout* spec, and the UI no longer restyles
Graphviz's own SVG.

## Context

Until M13 the viewer called `viz.renderSVGElement(view.dot)` and restyled Graphviz's SVG
through the `class` attributes `render/dot.py` sets. That SVG is fixed once drawn: a box
cannot be moved and its lines routed again, and a line's width cannot follow its import
count without a DOT attribute per edge.

Four changes came out of a page of live mockups on tiny-tale-backend's views. The other
archview on PyPI (lm17918/archview, Cytoscape.js and dagre) prompted the first two:

1. Colour boxes by role, instability or zone, with a legend that picks out a group, and
   a panel that explains the metrics.
2. Drag boxes, with the layout kept per view.
3. Weigh lines by import count, colour their direction on hover, and show a hover card.
4. Find any package or module with `/`.

ADR 0007 and `docs/05` named ELK and React Flow as the step to take when interactions
needed it.

## Decision

Keep Graphviz for layout and draw the SVG in the UI from its JSON output.

- **Layout.** `draw()` calls `viz.renderJSON(view.dot)` on the same DOT as before.
  `layout.js` reads box centres and sizes, cluster frames with their members, and each
  edge's spline, arrow tip and label position, in points with y pointing down. The first
  frame is the layout `archview graph --dot` gives.
- **Drawing.** `draw.js` builds the SVG markup. It keeps the DOM contract the rest of
  the UI relies on, one `g.node[data-id]` per box and one
  `g.edge[data-source][data-target]` per edge, so focus, pinning, selection and the
  panels kept working unchanged. Colours are CSS variables on screen. An export writes
  the light colours into the elements and adds a legend for the colour scheme.
- **Re-routing on drop.** A small DOT with every box pinned (`pos="x,y!"`,
  `fixedsize=true`) goes to `neato`, which routes the edges only. neato shifts the whole
  drawing by a constant, which is undone with one box's offset. It places no labels, so
  a count goes halfway along its re-routed line. A view of more than 100 boxes draws the
  moved box's lines straight instead and keeps the other routes. Routing cost follows
  the number of boxes, not lines:

  | View | Boxes | Lines | neato, every line |
  |---|---|---|---|
  | tiny-tale `src` | 8 | 13 | 1.5 ms (Node), 5-6 ms in the browser |
  | tiny-tale `src.story_generator.providers` | 15 | 41 | 3.7 ms (Node) |
  | synthetic | 100 | 300 | 227 ms (Node) |
  | synthetic | 300 | 1000 | 4.9 s (Node); 808 ms for one box's 15 lines |

- **Saved layouts.** Moved boxes are kept in the browser's `localStorage` under
  `archview.layout.v1`, keyed by repo, project, workspace member, root and the two
  filters. The viewer still writes nothing into the analysed repo. Storage that is
  missing or blocked only means nothing is kept.
- **Server.** `/api/view` gains one field, `threshold`, the zone threshold the metrics
  chart shades by. `render/dot.py`, `archview graph --json` and their goldens are
  unchanged.
- **Code.** The UI stays plain ES modules with no build step. The modules with no DOM
  (`layout.js`, `draw.js`, `colour.js`, `chart.js`, `find.js`, the storage half of
  `drag.js`) have Node tests under `tests/ui/`, which `tests/test_ui_js.py` runs from
  pytest.

## Rejected approaches

- **Cytoscape.js and dagre**, as the other archview does. Dragging comes built in, but
  the screen would no longer match `archview graph --dot`, dagre's compound layout gives
  the spread-out first frame that archview shows (closed folders keep the spacing they
  had open), and it adds about 400 KB of vendored JavaScript.
- **ELK and React Flow.** They need a build step the UI has avoided, for interactions
  Graphviz already gives.

## Consequences

- SVG and PNG exports come from the drawing: the dragged layout and the colour scheme,
  in light colours, with a legend. Mermaid and DOT exports are unchanged.
- Abstract boxes show an italic name under every scheme; the green fill stays only under
  the None scheme.
- A box that a reanalysis adds takes Graphviz's position and can land on a moved box.
  Reset layout is the remedy.
- `localStorage` belongs to the browser and the address, so a saved layout follows the
  port, as the existing options do.
- Collapse in place (the rest of V10) can now be built on the same drawing, with
  Graphviz clusters, rather than waiting for ELK.
- Next: comparing the structure with a git ref and an `archview diff` command (idea 7
  of the mockups), as its own milestone.
