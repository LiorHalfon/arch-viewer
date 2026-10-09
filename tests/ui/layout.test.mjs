import assert from "node:assert/strict";
import { test } from "node:test";

import {
  bounds, clusterFrames, edgeKey, layoutView, REROUTE_LIMIT, reroute, rerouteLayout, routesAfterMove, straightRoute,
} from "../../src/archview/ui/layout.js";
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

const SAMPLE_EDGES = [{ source: "app", target: "core.api" }, { source: "app", target: "core" }];
const positionsOf = (layout) => Object.fromEntries(Object.entries(layout.nodes).map(([id, n]) => [id, { x: n.x, y: n.y }]));

test("a pinned re-route keeps every box where it was put", async () => {
  const viz = await loadViz();
  const layout = layoutView(viz, SAMPLE_DOT);
  const positions = positionsOf(layout);
  positions.app = { x: positions.app.x + 60, y: positions.app.y + 10 };
  const out = rerouteLayout(viz, layout, positions, SAMPLE_EDGES);
  for (const [id, p] of Object.entries(positions)) {
    near(out.nodes[id].x, p.x, 0.5);
    near(out.nodes[id].y, p.y, 0.5);
  }
  for (const e of SAMPLE_EDGES) assert.ok(out.routes[edgeKey(e.source, e.target)].tip, `${e.source}>${e.target} has no arrow tip`);
});

test("no edges re-route to nothing", async () => {
  const viz = await loadViz();
  const layout = layoutView(viz, SAMPLE_DOT);
  assert.deepEqual(reroute(viz, layout, positionsOf(layout), []), {});
});

test("ids with quotes and backslashes survive the pinned DOT", async () => {
  const [a, b] = ['a"b', "c\\d"];
  const layout = { w: 200, h: 200, nodes: { [a]: { x: 50, y: 50, w: 60, h: 30 }, [b]: { x: 150, y: 150, w: 60, h: 30 } }, clusters: [], routes: {} };
  const routes = reroute(await loadViz(), layout, positionsOf(layout), [{ source: a, target: b }]);
  assert.ok(routes[edgeKey(a, b)]?.points.length);
});

test("a big view draws only the moved box's lines straight", () => {
  const nodes = Object.fromEntries(Array.from({ length: REROUTE_LIMIT + 1 }, (_, i) => [`n${i}`, { x: i * 100, y: (i % 3) * 80, w: 60, h: 30 }]));
  const layout = { w: 10200, h: 300, nodes, clusters: [], routes: {} };
  const edges = [{ source: "n0", target: "n1" }, { source: "n2", target: "n0" }, { source: "n3", target: "n4" }];
  const previous = Object.fromEntries(edges.map((e) => [edgeKey(e.source, e.target), { points: [[0, 0], [1, 1], [2, 2], [3, 3]], tip: [4, 4], label: null }]));
  const routes = routesAfterMove(null, layout, positionsOf(layout), edges, previous, new Set(["n0"]));
  assert.equal(routes["n3>n4"], previous["n3>n4"]);
  assert.notEqual(routes["n0>n1"], previous["n0>n1"]);
  assert.notEqual(routes["n2>n0"], previous["n2>n0"]);
  assert.deepEqual(routes["n0>n1"].points[0], routes["n0>n1"].points[1]);
});

test("straight routes start and end on the borders", () => {
  const r = straightRoute({ x: 0, y: 0 }, { w: 40, h: 20 }, { x: 100, y: 0 }, { w: 40, h: 20 });
  assert.deepEqual(r.points[0], [21, 0]);
  assert.deepEqual(r.tip, [79, 0]);
  assert.equal(r.points.length, 4);
  assert.deepEqual(r.label, [50, -9]);
});

test("a cluster frame follows its members", async () => {
  const layout = layoutView(await loadViz(), SAMPLE_DOT);
  const positions = positionsOf(layout);
  positions["core.api"] = { x: positions["core.api"].x + 100, y: positions["core.api"].y };
  const [before] = layout.clusters;
  const [after] = clusterFrames(layout, positions);
  near(after.x, before.x);
  near(after.w, before.w + 100);
});

test("the bounds include a box dragged past the edge", async () => {
  const layout = layoutView(await loadViz(), SAMPLE_DOT);
  const positions = positionsOf(layout);
  positions.app = { x: -50, y: positions.app.y };
  const box = bounds(layout, positions, layout.routes, clusterFrames(layout, positions));
  assert.ok(box.x <= -50 - layout.nodes.app.w / 2 - 24);
  assert.ok(box.x + box.w >= layout.w);
});
