// Resizing the side panel by the handle on its left edge.

export const PANEL_MIN = 280;
export const PANEL_DEFAULT = 360;
const SHARE = 0.6;  // of the window the panel may take, so the diagram keeps the rest
const STEP = 16;    // pixels per arrow key

// The panel's width for a wanted one: at least the minimum, at most its share of
// `room` (the width of the page under the toolbar), the default if not a number.
export function panelWidth(wanted, room) {
  if (!Number.isFinite(wanted)) return PANEL_DEFAULT;
  return Math.round(Math.min(Math.max(wanted, PANEL_MIN), Math.max(PANEL_MIN, room * SHARE)));
}

// The panel sits on the right, so moving the handle left widens it. `onResize` gets
// the wanted width; `onDone` follows a drag or a key, to keep the width.
export function enableResize(handle, { width, onResize, onDone, onReset }) {
  let drag = null;
  const end = () => {
    drag = null;
    onDone();
  };
  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    drag = { x: e.clientX, width: width(), pointer: e.pointerId };
    try {
      handle.setPointerCapture(e.pointerId);
    } catch {
      // the pointer is already gone
    }
  });
  handle.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.pointer) return;
    // The button is up: a quick trackpad release sends this before the pointerup.
    if (!(e.buttons & 1)) return end();
    onResize(drag.width - (e.clientX - drag.x));
  });
  const release = (e) => {
    if (drag && e.pointerId === drag.pointer) end();
  };
  handle.addEventListener("pointerup", release);
  handle.addEventListener("pointercancel", release);
  handle.addEventListener("keydown", (e) => {
    const by = { ArrowLeft: STEP, ArrowRight: -STEP }[e.key];
    if (!by) return;
    e.preventDefault();
    onResize(width() + by);
    onDone();
  });
  handle.addEventListener("dblclick", () => onReset());
}
