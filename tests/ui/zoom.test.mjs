import assert from "node:assert/strict";
import { test } from "node:test";

import { enablePan, KEEP, keepOneBox, panRoom, wheelFactor, zoomAround } from "../../src/archview/ui/zoom.js";

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
  // the drawing's corner at (100, 50), doubled around (200, 100): that point stays
  assert.deepEqual(zoomAround({ x: 100, y: 50 }, { x: 200, y: 100 }, 2), { x: 0, y: 0 });
  assert.deepEqual(zoomAround({ x: 100, y: 50 }, { x: 100, y: 50 }, 2), { x: 100, y: 50 });
});

// A 400 x 300 drawing on an 800 x 600 stage: one box at the top right, one at the
// bottom left.
const stage = { w: 800, h: 600 };
const size = { w: 400, h: 300 };
const topRight = { left: 300, top: 0, right: 400, bottom: 40 };
const bottomLeft = { left: 0, top: 260, right: 100, bottom: 300 };

test("the drawing pans until its last box is whole against the far edge", () => {
  const room = panRoom([topRight, bottomLeft], size, stage);
  // panned right: the bottom-left box ends KEEP short of the stage's right edge
  assert.equal(room.left + bottomLeft.right, stage.w - KEEP);
  // panned left: the top-right box starts KEEP into the stage
  assert.equal(room.left + size.w + room.right - stage.w, room.left + topRight.left - KEEP);
  // panned down: the top-right box ends KEEP short of the bottom
  assert.equal(room.top + topRight.bottom, stage.h - KEEP);
  // panned up: the bottom-left box starts KEEP into the stage
  assert.equal(room.top + size.h + room.bottom - stage.h, room.top + bottomLeft.top - KEEP);
});

test("one box can go to any corner of the stage", () => {
  const room = panRoom([topRight], size, stage);
  // bottom left: scrolled to the far left and the far bottom
  const scroll = { x: room.left + size.w + room.right - stage.w, y: 0 };
  assert.equal(room.left + topRight.left - scroll.x, KEEP);
  assert.equal(room.top + topRight.bottom - scroll.y, stage.h - KEEP);
});

test("the drawing stays where it is while a box is whole on the stage", () => {
  const at = { x: 200, y: 150 };
  assert.equal(keepOneBox(at, [topRight, bottomLeft], stage), at);
});

test("a corner with no whole box on it goes back to the nearest one that has one", () => {
  // far left and down: the top-right box is cut by the left edge, the bottom-left
  // one is below the stage
  const at = { x: -340, y: 560 };
  assert.deepEqual(keepOneBox(at, [topRight, bottomLeft], stage), { x: KEEP - topRight.left, y: stage.h - KEEP - topRight.bottom });
});

test("a box bigger than the stage counts while it covers it", () => {
  const huge = { left: 0, top: 0, right: 2000, bottom: 2000 };
  const at = { x: -500, y: -500 };
  assert.equal(keepOneBox(at, [huge], stage), at);
  assert.deepEqual(keepOneBox({ x: 100, y: -500 }, [huge], stage), { x: KEEP, y: -500 });
});

test("a drawing bigger than the stage still gets a little room", () => {
  const room = panRoom([{ left: 0, top: 0, right: 2000, bottom: 2000 }], { w: 2000, h: 2000 }, stage);
  assert.deepEqual(room, { left: 24, right: 24, top: 24, bottom: 24 });
});

test("nothing drawn, a little room", () => {
  assert.deepEqual(panRoom([], size, stage), { left: 24, right: 24, top: 24, bottom: 24 });
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
