import assert from "node:assert/strict";
import { test } from "node:test";

import { edgeKey, layoutView } from "../../src/archview/ui/layout.js";
import { loadViz, SAMPLE_DOT } from "./support.mjs";

const near = (a, b, tol = 0.1) => assert.ok(Math.abs(a - b) <= tol, `${a} is not within ${tol} of ${b}`);

test("boxes are flipped to screen coordinates and sized in points", async () => {
  const l = layoutView(await loadViz(), SAMPLE_DOT);
  assert.deepEqual([l.w, l.h], [212, 182]);
  near(l.nodes.core.x, 61);
  near(l.nodes.core.y, 145.2);
  near(l.nodes.core.w, 89.9);
  near(l.nodes.app.y, 20.8);
});

test("a cluster knows its frame, members and margin", async () => {
  const [c] = layoutView(await loadViz(), SAMPLE_DOT).clusters;
  assert.equal(c.id, "cluster_core");
  assert.deepEqual([...c.members].sort(), ["core", "core.api"]);
  near(c.x, 8);
  near(c.y, 116.4);
  near(c.w, 196);
  near(c.pad.l, 8);
  near(c.pad.b, 8);
});

test("every edge has a route with its arrow tip and label", async () => {
  const r = layoutView(await loadViz(), SAMPLE_DOT).routes[edgeKey("app", "core.api")];
  assert.equal(r.points.length % 3, 1);
  near(r.tip[0], 161.3);
  near(r.tip[1], 126.7);
  near(r.label[1], 83);
});
