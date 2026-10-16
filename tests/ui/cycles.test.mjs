import assert from "node:assert/strict";
import { test } from "node:test";

import { loopsIn } from "../../src/archview/ui/cycles.js";

const edges = (...pairs) => pairs.map((p) => { const [source, target] = p.split(">"); return { source, target }; });

test("two boxes that import each other are one loop", () => {
  assert.deepEqual(loopsIn(["b", "a"], edges("a>b", "b>a")), { loops: [["a", "b"]], more: false });
});

test("a tangle breaks into its loops, shortest first, each from its first name", () => {
  // tiny-tale-backend's services tangle
  const members = ["bespoke", "fulfillment", "next_ideas", "print", "stories", "story_generation"];
  const tangle = edges(
    "bespoke>print", "print>next_ideas", "next_ideas>bespoke", "bespoke>story_generation", "fulfillment>print",
    "next_ideas>fulfillment", "stories>print", "story_generation>next_ideas", "story_generation>print", "story_generation>stories",
    "print>users", "users>print",  // outside the tangle: not its loops
  );
  assert.deepEqual(loopsIn(members, tangle).loops, [
    ["bespoke", "print", "next_ideas"],
    ["bespoke", "story_generation", "next_ideas"],
    ["fulfillment", "print", "next_ideas"],
    ["bespoke", "story_generation", "print", "next_ideas"],
    ["bespoke", "story_generation", "stories", "print", "next_ideas"],
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
