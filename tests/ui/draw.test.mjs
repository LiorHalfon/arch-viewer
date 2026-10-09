import assert from "node:assert/strict";
import { test } from "node:test";

import { drawSvg, edgeWidth } from "../../src/archview/ui/draw.js";
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
  assert.ok(svg.includes('class="node package tangled zone-pain"'));
  assert.ok(svg.includes('class="node package" data-id="app"'));
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

const near = (a, b, tol) => assert.ok(Math.abs(a - b) <= tol, `${a} is not within ${tol} of ${b}`);

test("a line's width grows with its import count, up to 6", () => {
  assert.equal(edgeWidth(1), 1);
  near(edgeWidth(10), 2.85, 0.01);
  near(edgeWidth(94), 4.64, 0.01);
  assert.equal(edgeWidth(1e6), 6);
});

test("cycle and rule-break lines are at least 2 wide", () => {
  assert.equal(edgeWidth(1, { cycle: true }), 2);
  assert.equal(edgeWidth(1, { violation: true }), 2);
  near(edgeWidth(94, { cycle: true }), 4.64, 0.01);
});

test("a weighted drawing writes each line's width", async () => {
  const { view, layout } = await sample();
  const svg = drawSvg(view, layout, { weighted: true });
  assert.ok(group(svg, 'data-target="core.api"').includes('class="line" d="') && group(svg, 'data-target="core.api"').includes('stroke-width="2.11"'));
  assert.ok(group(svg, 'data-source="app" data-target="core"').includes('stroke-width="1.00"'));
  assert.ok(!drawSvg(view, layout).includes("stroke-width"));
});

test("an export stands alone: light colours written in, no stylesheet needed", async () => {
  const { view, layout } = await sample();
  for (const scheme of ["role", "instability", "zone", "none"]) {
    const svg = drawSvg(view, layout, { mode: "export", scheme, weighted: true });
    assert.ok(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"'), scheme);
    assert.ok(!svg.includes("var("), `${scheme} export still uses a CSS variable`);
    assert.match(svg, /<svg [^>]*width="[\d.]+" height="[\d.]+"/);
    assert.ok(svg.includes('fill="#ffffff"'), "white background");
    assert.ok(!svg.includes('class="hit"'), "no hit paths");
  }
});

test("an export carries the scheme's legend, except under None", async () => {
  const { view, layout } = await sample();
  assert.ok(drawSvg(view, layout, { mode: "export", scheme: "role" }).includes(">entry point</text>"));
  assert.ok(!drawSvg(view, layout, { mode: "export", scheme: "role" }).includes(">on its own</text>"), "a class with no boxes is left out");
  assert.ok(!drawSvg(view, layout, { mode: "export", scheme: "none" }).includes('class="legend"'));
});

test("a weighted export keeps the line widths", async () => {
  const { view, layout } = await sample();
  const svg = drawSvg(view, layout, { mode: "export", weighted: true });
  assert.ok(group(svg, 'data-target="core.api"').includes('stroke-width="2.11"'));
});

test("a red cycle name on a scheme fill gets a halo to be read against", async () => {
  const { view, layout } = await sample();
  view.nodes[0].in_cycle = true;  // app: an entry point, so a blue fill under Role
  const name = (svg) => {
    const g = group(svg, 'data-id="app"');
    return g.slice(g.indexOf('<text class="name"'), g.indexOf(">", g.indexOf('<text class="name"')));
  };
  assert.ok(name(drawSvg(view, layout, { scheme: "role" })).includes("stroke:#ffffff"), "screen: white halo behind light-theme red");
  assert.ok(name(drawSvg(view, layout, { scheme: "role", palette: { "--danger": "#ff6b6b" } })).includes("stroke:#1d232b"), "screen: dark halo behind dark-theme red");
  const exported = name(drawSvg(view, layout, { scheme: "role", mode: "export" }));
  assert.ok(exported.includes('stroke="#ffffff"') && exported.includes('paint-order="stroke"'));
  assert.ok(!name(drawSvg(view, layout, { scheme: "none" })).includes("stroke"), "no halo on today's pale fills");
});

test("boxes carry no title, since the hover card replaces it", async () => {
  const { view, layout } = await sample();
  assert.ok(!group(drawSvg(view, layout), 'data-id="app"').includes("<title>"));
});

test("ids with quotes and slashes are escaped", () => {
  const id = 'src/@types/a"b.ts';
  const view = { root: "src", nodes: [{ ...sampleView().nodes[2], id, name: 'a"b.ts', parent: null }], edges: [], cycles: [] };
  const layout = { w: 100, h: 50, nodes: { [id]: { x: 50, y: 25, w: 60, h: 30 } }, clusters: [], routes: {} };
  const svg = drawSvg(view, layout);
  assert.ok(svg.includes('data-id="src/@types/a&quot;b.ts"'));
  assert.ok(!svg.includes('a"b'));
});
