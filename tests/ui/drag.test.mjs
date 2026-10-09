import assert from "node:assert/strict";
import { test } from "node:test";

import { isDrag, layoutKey, loadMoved, saveMoved, STORE_KEY } from "../../src/archview/ui/drag.js";

function memory(initial = {}) {
  const data = { ...initial };
  return { getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); }, removeItem: (k) => { delete data[k]; }, data };
}

test("a drag starts past four pixels", () => {
  assert.equal(isDrag({ x: 0, y: 0 }, { x: 3, y: 0 }), false);
  assert.equal(isDrag({ x: 0, y: 0 }, { x: 4, y: 0 }), false);
  assert.equal(isDrag({ x: 0, y: 0 }, { x: 3, y: 3 }), true);
});

test("the view key names everything that changes the boxes", () => {
  assert.equal(layoutKey({ repo: "repo", project: "src", package: null, root: "src.webapp", externals: false, hideTests: true }), "repo|src||src.webapp|0|1");
  assert.equal(layoutKey({ repo: "ws", project: "ws", package: "core", root: "core", externals: true, hideTests: false }), "ws|ws|core|core|1|0");
});

test("saved boxes that are gone are ignored", () => {
  const storage = memory({ [STORE_KEY]: JSON.stringify({ v: { a: [1, 2], gone: [3, 4] } }) });
  const moved = loadMoved(storage, "v", new Set(["a", "b"]));
  assert.deepEqual([...moved], [["a", { x: 1, y: 2 }]]);
});

test("storage that throws or holds junk loads nothing", () => {
  const throwing = { getItem: () => { throw new Error("blocked"); } };
  assert.equal(loadMoved(throwing, "v", new Set(["a"])).size, 0);
  assert.equal(loadMoved(memory({ [STORE_KEY]: "{not json" }), "v", new Set(["a"])).size, 0);
  assert.equal(loadMoved(memory({ [STORE_KEY]: "null" }), "v", new Set(["a"])).size, 0);
  assert.equal(loadMoved(memory({ [STORE_KEY]: JSON.stringify({ v: { a: "x" } }) }), "v", new Set(["a"])).size, 0);
  assert.equal(loadMoved(null, "v", new Set(["a"])).size, 0);
});

test("saving nothing removes the view and keeps the others", () => {
  const storage = memory({ [STORE_KEY]: JSON.stringify({ v: { a: [1, 2] }, w: { b: [5, 6] } }) });
  saveMoved(storage, "v", new Map());
  assert.deepEqual(JSON.parse(storage.data[STORE_KEY]), { w: { b: [5, 6] } });
  saveMoved(storage, "v", new Map([["c", { x: 7, y: 8 }]]));
  assert.deepEqual(JSON.parse(storage.data[STORE_KEY]), { w: { b: [5, 6] }, v: { c: [7, 8] } });
});

test("storage that refuses a write does not throw", () => {
  const full = { getItem: () => null, setItem: () => { throw new Error("quota"); } };
  assert.doesNotThrow(() => saveMoved(full, "v", new Map([["a", { x: 1, y: 2 }]])));
  assert.doesNotThrow(() => saveMoved(null, "v", new Map()));
});
