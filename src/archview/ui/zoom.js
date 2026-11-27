// Zooming with the wheel or a pinch, around the pointer, and panning by dragging
// the diagram's background. The zoom itself (sizing the svg) stays in app.js.

import { isDrag, swallowClick } from "./drag.js";

const LINE = 16;    // pixels in a line, for wheels that count lines
const PAGE = 400;   // and in a page

// How much one wheel event zooms: a mouse notch (100 px) by about a fifth, a pinch
// (Chrome and Firefox send it as wheel events with ctrl held) in the small steps of
// the fingers. Never more than half at once.
export function wheelFactor({ deltaY, deltaMode, ctrlKey }) {
  const px = deltaY * (deltaMode === 1 ? LINE : deltaMode === 2 ? PAGE : 1);
  const factor = Math.exp(-px * (ctrlKey ? 0.01 : 0.002));
  return Math.min(1.5, Math.max(1 / 1.5, factor));
}

// Where the drawing's top-left corner goes, in the stage's own pixels, when it is
// scaled by `ratio` around `anchor` and the point under the anchor stays put.
export function zoomAround(at, anchor, ratio) {
  return { x: anchor.x - (anchor.x - at.x) * ratio, y: anchor.y - (anchor.y - at.y) * ratio };
}

export const KEEP = 16;  // how far from the stage's edge the last box on it stops
const EDGE = 24;         // the room left around a drawing that has none to spare

// The room around the drawing that lets it pan until one box is left on the stage:
// the box nearest an edge, whole, KEEP pixels from the opposite edge. `boxes` are the
// boxes' rectangles in pixels from the drawing's top-left corner; `size` is the
// drawing's and `stage` the stage's, in pixels.
export function panRoom(boxes, size, stage) {
  if (!boxes.length) return { left: EDGE, right: EDGE, top: EDGE, bottom: EDGE };
  const most = (key, pick) => pick(...boxes.map((b) => b[key]));
  const room = (v) => Math.max(EDGE, v);
  return {
    left: room(stage.w - KEEP - most("right", Math.min)),
    right: room(stage.w - KEEP - (size.w - most("left", Math.max))),
    top: room(stage.h - KEEP - most("bottom", Math.min)),
    bottom: room(stage.h - KEEP - (size.h - most("top", Math.max))),
  };
}

// The nearest place for the drawing's top-left corner that leaves at least one box
// whole on the stage, KEEP pixels in from its edges. panRoom gives the scroll range
// around all of them; this keeps a corner of that range from showing none of them.
// A box bigger than the stage counts as on it while it covers the stage.
export function keepOneBox(at, boxes, stage) {
  let best = at, far = Infinity;
  for (const b of boxes) {
    const x = within(at.x, KEEP - b.left, stage.w - KEEP - b.right);
    const y = within(at.y, KEEP - b.top, stage.h - KEEP - b.bottom);
    const d = Math.hypot(x - at.x, y - at.y);
    if (d === 0) return at;
    if (d < far) [best, far] = [{ x, y }, d];
  }
  return best;
}

const within = (v, a, b) => Math.min(Math.max(v, Math.min(a, b)), Math.max(a, b));

// A press on the background that moves past the drag threshold scrolls the stage
// with the pointer; one that does not stays a click. Boxes keep their own dragging.
export function enablePan(stage) {
  let pan = null;
  const end = () => {
    stage.classList.remove("panning");
    pan = null;
  };
  stage.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("g.node")) return;
    pan = { start: { x: e.clientX, y: e.clientY }, left: stage.scrollLeft, top: stage.scrollTop, moving: false, pointer: e.pointerId };
  });
  stage.addEventListener("pointermove", (e) => {
    if (!pan || e.pointerId !== pan.pointer) return;
    if (!(e.buttons & 1)) {
      // The button is up: a quick trackpad release, or one the stage never saw.
      if (pan.moving) swallowClick(window);
      end();
      return;
    }
    if (!pan.moving) {
      if (!isDrag(pan.start, { x: e.clientX, y: e.clientY })) return;
      pan.moving = true;
      stage.classList.add("panning");
      try {
        stage.setPointerCapture(e.pointerId);
      } catch {
        // the pointer is already gone; the stage still gets its moves
      }
    }
    stage.scrollLeft = pan.left - (e.clientX - pan.start.x);
    stage.scrollTop = pan.top - (e.clientY - pan.start.y);
  });
  const release = (e) => {
    if (!pan || e.pointerId !== pan.pointer) return;
    // A pan must not clear the focus or open the line it started on.
    if (pan.moving) swallowClick(window);
    end();
  };
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointercancel", release);
}
