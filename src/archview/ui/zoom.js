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

// The scroll that puts the point under the pointer back under it, given the
// drawing's screen rectangle before and after it was resized.
export function keepUnder(before, after, pointer) {
  const fx = (pointer.x - before.left) / before.width;
  const fy = (pointer.y - before.top) / before.height;
  return { x: after.left + fx * after.width - pointer.x, y: after.top + fy * after.height - pointer.y };
}

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
