import assert from "node:assert/strict";
import { test } from "node:test";

import { AREA, chartSvg } from "../../src/archview/ui/chart.js";
import { sampleView } from "./support.mjs";

const box = (name, I, A, fields = {}) => ({ ...sampleView().nodes[0], id: `p.${name}`, name, instability: I, abstractness: A, ...fields });
const view = (nodes) => ({ root: "p", nodes, edges: [], cycles: [] });

// tiny-tale-backend's src.story_generator: instability and abstractness per box.
const STORY_GENERATOR = [
  ["cover", 1, 0.143], ["cover_photo_generator", 0.5, 0], ["font_loading", 0, 0], ["image_storage", 0, 1],
  ["llm_generated", 1, 0], ["models", 0, 0], ["prompts", 0, 0], ["providers", 0.429, 0.147], ["template_rendered", 0.714, 0.069],
].map(([name, I, A]) => box(name, I, A));

test("boxes at one point share a dot", () => {
  const { dots } = chartSvg(view(STORY_GENERATOR), 0.3);
  const origin = dots.find((d) => d.ids.includes("p.models"));
  assert.deepEqual(origin.ids, ["p.font_loading", "p.models", "p.prompts"]);
  assert.equal(origin.text, "font_loading +2");
  assert.equal(dots.length, 7);
});

test("labels stay inside and apart", () => {
  const { dots } = chartSvg(view(STORY_GENERATOR), 0.3);
  const width = AREA.left + AREA.width + AREA.right;
  const boxes = dots.filter((d) => d.label).map((d) => {
    const w = d.text.length * 6.2 + 2;
    const x0 = d.label.anchor === "start" ? d.label.x : d.label.x - w;
    return { x0, x1: x0 + w, y: d.label.y };
  });
  assert.equal(boxes.length, dots.length, "every dot here finds room for its label");
  for (const b of boxes) {
    assert.ok(b.x0 >= 0 && b.x1 <= width, `label ${b.x0}..${b.x1} leaves the chart`);
    assert.ok(b.y >= AREA.top + 9 && b.y <= AREA.top + AREA.height + 4);
  }
  for (const [i, a] of boxes.entries()) {
    for (const b of boxes.slice(i + 1)) {
      assert.ok(!(a.x0 < b.x1 && b.x0 < a.x1 && Math.abs(a.y - b.y) < 12), "two labels overlap");
    }
  }
});

test("a crowded label shows on hover only", () => {
  // Around one point there are 14 label spots (7 offsets on each side), so 20 boxes cannot all fit.
  const crowd = Array.from({ length: 20 }, (_, i) => box(`crowded_name_${i}`, 0.5 + (i % 5) * 0.002, 0.5 + Math.floor(i / 5) * 0.002));
  const { dots } = chartSvg(view(crowd), 0.3);
  assert.ok(dots.some((d) => d.label === null));
});

test("third-party boxes and undefined I are left out", () => {
  const nodes = [box("a", 0.5, 0.5), box("lonely", null, 0, { zone: "isolated" }), box("requests", null, 0, { kind: "external", zone: "external" })];
  assert.deepEqual(chartSvg(view(nodes), 0.3).dots.map((d) => d.ids), [["p.a"]]);
});

test("an empty chart says so", () => {
  const { svg, dots } = chartSvg(view([box("lonely", null, 0, { zone: "isolated" })]), 0.3);
  assert.equal(dots.length, 0);
  assert.ok(svg.includes("No box in this view has an instability to plot."));
});

test("the zones follow the threshold", () => {
  const { svg } = chartSvg(view(STORY_GENERATOR), 0.4);
  const x = AREA.left + 0.6 * AREA.width;
  assert.ok(svg.includes(`${Number(x.toFixed(2))},${AREA.top + AREA.height}`), "the pain triangle reaches I = 0.6 on the axis");
});
