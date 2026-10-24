import assert from "node:assert/strict";
import { test } from "node:test";

import { loopsIn } from "../../src/archview/ui/cycles.js";

const edges = (...pairs) => pairs.map((p) => { const [source, target] = p.split(">"); return { source, target }; });

test("two boxes that import each other are one loop", () => {
  assert.deepEqual(loopsIn(["b", "a"], edges("a>b", "b>a")), { loops: [["a", "b"]], more: false });
});

test("a tangle breaks into its loops, shortest first, each from its first name", () => {
  // a real backend's services tangle
  const members = ["auth", "billing", "catalog", "orders", "search", "shipping"];
  const tangle = edges(
    "auth>orders", "orders>catalog", "catalog>auth", "auth>shipping", "billing>orders",
    "catalog>billing", "search>orders", "shipping>catalog", "shipping>orders", "shipping>search",
    "orders>users", "users>orders",  // outside the tangle: not its loops
  );
  assert.deepEqual(loopsIn(members, tangle).loops, [
    ["auth", "orders", "catalog"],
    ["auth", "shipping", "catalog"],
    ["billing", "orders", "catalog"],
    ["auth", "shipping", "orders", "catalog"],
    ["auth", "shipping", "search", "orders", "catalog"],
  ]);
});

test("a big tangle lists the first loops and says there are more", () => {
  // every box imports every other: 4 boxes have 20 loops
  const members = ["a", "b", "c", "d"];
  const all = members.flatMap((s) => members.filter((t) => t !== s).map((t) => ({ source: s, target: t })));
  assert.equal(loopsIn(members, all, 100).loops.length, 20);
  const first = loopsIn(members, all, 7);
  assert.equal(first.loops.length, 7);
  assert.equal(first.more, true);
  assert.deepEqual(first.loops.map((loop) => loop.length), [2, 2, 2, 2, 2, 2, 3], "the six pairs come first");
});
