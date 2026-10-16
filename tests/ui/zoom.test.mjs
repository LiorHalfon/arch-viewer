import assert from "node:assert/strict";
import { test } from "node:test";

import { enablePan, keepUnder, wheelFactor } from "../../src/archview/ui/zoom.js";

const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-3, `${actual} is not ${expected}`);

test("a wheel notch zooms by about a fifth, up in and down out", () => {
  close(wheelFactor({ deltaY: -100, deltaMode: 0, ctrlKey: false }), Math.exp(0.2));
  close(wheelFactor({ deltaY: 100, deltaMode: 0, ctrlKey: false }), Math.exp(-0.2));
  assert.equal(wheelFactor({ deltaY: 0, deltaMode: 0, ctrlKey: false }), 1);
});

test("a pinch arrives as small wheel steps with ctrl and follows the fingers", () => {
  close(wheelFactor({ deltaY: -5, deltaMode: 0, ctrlKey: true }), Math.exp(0.05));
});

test("wheels that count lines zoom as much as one that counts pixels", () => {
  close(wheelFactor({ deltaY: 3, deltaMode: 1, ctrlKey: false }), wheelFactor({ deltaY: 48, deltaMode: 0, ctrlKey: false }));
});

test("one wheel event never zooms by more than half", () => {
  assert.equal(wheelFactor({ deltaY: -5000, deltaMode: 0, ctrlKey: false }), 1.5);
  assert.equal(wheelFactor({ deltaY: 5000, deltaMode: 0, ctrlKey: false }), 1 / 1.5);
});

test("the point under the pointer stays under it", () => {
  const before = { left: 100, top: 50, width: 200, height: 100 };
  const after = { left: 100, top: 50, width: 400, height: 200 };
  assert.deepEqual(keepUnder(before, after, { x: 200, y: 100 }), { x: 100, y: 50 });
  assert.deepEqual(keepUnder(before, after, { x: 100, y: 50 }), { x: 0, y: 0 });
});

// Just enough of the stage for enablePan: listeners, scroll offsets and a class list.
function fakeStage() {
  const listeners = {};
  const classes = new Set();
  return {
    scrollLeft: 100, scrollTop: 100,
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
    addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
    removeEventListener: () => {},
    setPointerCapture: () => {},
    fire: (type, e) => { for (const fn of listeners[type] || []) fn(e); },
  };
}
const background = { closest: () => null };
const onBox = { closest: (selector) => (selector.includes("g.node") ? {} : null) };
const at = (x, y, buttons = 1, target = background) => ({ target, button: 0, buttons, pointerId: 1, clientX: x, clientY: y });

let swallowed = 0;
globalThis.window ??= {};
window.addEventListener = (type) => { if (type === "click") swallowed += 1; };
window.removeEventListener = () => {};

test("dragging the background pans the diagram", () => {
  const stage = fakeStage();
  enablePan(stage);
  stage.fire("pointerdown", at(50, 50));
  stage.fire("pointermove", at(80, 40));
  assert.deepEqual([stage.scrollLeft, stage.scrollTop], [70, 110]);
  assert.equal(stage.classList.contains("panning"), true);
  swallowed = 0;
  stage.fire("pointerup", at(80, 40, 0));
  assert.equal(stage.classList.contains("panning"), false);
  assert.equal(swallowed, 1, "the click after a pan is swallowed");
});

test("a press on a box is the box's, not a pan", () => {
  const stage = fakeStage();
  enablePan(stage);
  stage.fire("pointerdown", at(50, 50, 1, onBox));
  stage.fire("pointermove", at(90, 90, 1, onBox));
  assert.deepEqual([stage.scrollLeft, stage.scrollTop], [100, 100]);
});

test("a press that barely moves stays a click", () => {
  const stage = fakeStage();
  enablePan(stage);
  stage.fire("pointerdown", at(50, 50));
  stage.fire("pointermove", at(52, 51));
  swallowed = 0;
  stage.fire("pointerup", at(52, 51, 0));
  assert.deepEqual([stage.scrollLeft, stage.scrollTop], [100, 100]);
  assert.equal(swallowed, 0);
});

test("a pan ends when the button is up, however the release arrives", () => {
  const stage = fakeStage();
  enablePan(stage);
  stage.fire("pointerdown", at(50, 50));
  stage.fire("pointermove", at(80, 50));
  stage.fire("pointermove", at(90, 50, 0));  // a quick trackpad release
  stage.fire("pointermove", at(200, 200, 0));
  assert.deepEqual([stage.scrollLeft, stage.scrollTop], [70, 100]);
  assert.equal(stage.classList.contains("panning"), false);
});
