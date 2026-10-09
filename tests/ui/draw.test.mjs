import assert from "node:assert/strict";
import { test } from "node:test";

import { drawSvg } from "../../src/archview/ui/draw.js";
import { layoutView } from "../../src/archview/ui/layout.js";
import { loadViz, SAMPLE_DOT, sampleView } from "./support.mjs";

const sample = async () => ({ view: sampleView(), layout: layoutView(await loadViz(), SAMPLE_DOT) });
const count = (text, needle) => text.split(needle).length - 1;
const group = (svg, attrs) => {
  const start = svg.indexOf(attrs);
  return svg.slice(start, svg.indexOf("</g>", start));
};

test("one node group per box, with its id and classes", async () => {
  const { view, layout } = await sample();
  const svg = drawSvg(view, layout);
  assert.equal(count(svg, 'class="node '), 3);
  assert.ok(svg.includes('data-id="core.api"'));
  assert.ok(svg.includes('class="node module abstract"'));
  assert.ok(svg.includes('class="node package tangled"'));
});

test("one edge group per edge, hit path under the line", async () => {
  const { view, layout } = await sample();
  const svg = drawSvg(view, layout);
  assert.equal(count(svg, 'class="edge'), 2);
  const g = group(svg, 'data-source="app" data-target="core"');
  assert.ok(g.length > 0);
  assert.ok(g.indexOf('class="hit"') < g.indexOf('class="line"'));
  assert.ok(g.includes('class="arrow"') && g.includes('class="count"'));
});

test("an abstract edge gets a hollow arrow class", async () => {
  const { view, layout } = await sample();
  const svg = drawSvg(view, layout);
  assert.ok(svg.includes('<g class="edge abstract" data-source="app" data-target="core.api"'));
});

test("package labels carry the module count and the tangle mark", async () => {
  const { view, layout } = await sample();
  const svg = drawSvg(view, layout);
  assert.ok(svg.includes(">core ⟲</text>"));
  assert.ok(svg.includes(">(3 modules)</text>"));
  assert.ok(svg.includes(">api</text>"));
  assert.ok(!svg.includes("(1 module)"));
});

test("a view with no edges draws its boxes only", async () => {
  const { view, layout } = await sample();
  const svg = drawSvg({ ...view, edges: [] }, { ...layout, routes: {} });
  assert.equal(count(svg, 'class="edge'), 0);
  assert.equal(count(svg, 'class="node '), 3);
});

test("ids with quotes and slashes are escaped", () => {
  const id = 'src/@types/a"b.ts';
  const view = { root: "src", nodes: [{ ...sampleView().nodes[2], id, name: 'a"b.ts', parent: null }], edges: [], cycles: [] };
  const layout = { w: 100, h: 50, nodes: { [id]: { x: 50, y: 25, w: 60, h: 30 } }, clusters: [], routes: {} };
  const svg = drawSvg(view, layout);
  assert.ok(svg.includes('data-id="src/@types/a&quot;b.ts"'));
  assert.ok(!svg.includes('a"b'));
});
