import assert from "node:assert/strict";
import { test } from "node:test";

import { enableResize, PANEL_DEFAULT, PANEL_MIN, panelWidth } from "../../src/archview/ui/resize.js";

test("the panel is never narrower than its minimum", () => {
  assert.equal(panelWidth(100, 1600), PANEL_MIN);
  assert.equal(panelWidth(500, 1600), 500);
});

test("the panel leaves the diagram at least two fifths of the window", () => {
  assert.equal(panelWidth(1400, 1600), 960);
  assert.equal(panelWidth(1400, 300), PANEL_MIN, "the minimum wins on a narrow window");
});

test("a width that is not a number is the default", () => {
  assert.equal(panelWidth(undefined, 1600), PANEL_DEFAULT);
  assert.equal(panelWidth("wide", 1600), PANEL_DEFAULT);
});

// Just enough of the handle for enableResize: listeners and pointer capture.
function fakeHandle() {
  const listeners = {};
  return {
    addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
    setPointerCapture: () => {},
    fire: (type, e) => { for (const fn of listeners[type] || []) fn({ preventDefault: () => {}, ...e }); },
  };
}
const at = (x, buttons = 1) => ({ button: 0, buttons, pointerId: 1, clientX: x });

function resizer() {
  const handle = fakeHandle();
  const seen = { widths: [], done: 0, reset: 0 };
  enableResize(handle, {
    width: () => 400,
    onResize: (w) => seen.widths.push(w),
    onDone: () => { seen.done += 1; },
    onReset: () => { seen.reset += 1; },
  });
  return { handle, seen };
}

test("dragging the handle left widens the panel, right narrows it", () => {
  const { handle, seen } = resizer();
  handle.fire("pointerdown", at(1000));
  handle.fire("pointermove", at(950));
  handle.fire("pointermove", at(1100));
  handle.fire("pointerup", at(1100, 0));
  assert.deepEqual(seen.widths, [450, 300]);
  assert.equal(seen.done, 1);
  handle.fire("pointermove", at(900));
  assert.deepEqual(seen.widths, [450, 300], "nothing moves once the button is up");
});

test("a quick trackpad release ends the resize", () => {
  const { handle, seen } = resizer();
  handle.fire("pointerdown", at(1000));
  handle.fire("pointermove", at(980));
  handle.fire("pointermove", at(970, 0));
  handle.fire("pointermove", at(900, 0));
  assert.deepEqual(seen.widths, [420]);
  assert.equal(seen.done, 1);
});

test("arrow keys resize, and a double-click puts the default back", () => {
  const { handle, seen } = resizer();
  handle.fire("keydown", { key: "ArrowLeft" });
  handle.fire("keydown", { key: "ArrowRight" });
  handle.fire("keydown", { key: "Enter" });
  assert.deepEqual(seen.widths, [416, 384]);
  assert.equal(seen.done, 2);
  handle.fire("dblclick", {});
  assert.equal(seen.reset, 1);
});
