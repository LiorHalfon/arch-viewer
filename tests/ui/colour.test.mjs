import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CLASSES, classOf, contrast, inkFor, legendRows, LIGHT, roles, schemeFromOptions } from "../../src/archview/ui/colour.js";
import { drawSvg } from "../../src/archview/ui/draw.js";
import { sampleView } from "./support.mjs";

const box = (id, fields = {}) => ({ ...sampleView().nodes[0], id, name: id, ...fields });
const line = (source, target) => ({ source, target, count: 1, in_cycle: false, abstract: false, type_checking: false, violation: false, imports: [] });

function rolesView() {
  return {
    root: "r",
    nodes: ["a", "b", "c", "d", "e"].map((id) => box(id)).concat(box("x", { kind: "external", zone: "external", instability: null })),
    edges: [line("a", "b"), line("b", "c"), line("a", "x"), line("e", "x")],
    cycles: [],
  };
}

test("roles come from the lines in this view", () => {
  const r = roles(rolesView());
  assert.deepEqual(Object.fromEntries(r), { a: "entry", b: "between", c: "foundation", d: "alone", e: "alone" });
});

test("instability bins include their lower edge", () => {
  const values = [0, 0.2, 0.79, 0.8, 1, null];
  const view = { root: "r", nodes: values.map((I, i) => box(`n${i}`, { instability: I })), edges: [], cycles: [] };
  assert.deepEqual([...classOf(view, "instability").values()], ["i0", "i1", "i3", "i4", "i4", "isolated"]);
});

test("zone classes leave out third-party boxes", () => {
  const view = rolesView();
  view.nodes[0].zone = "pain";
  const zones = classOf(view, "zone");
  assert.equal(zones.get("a"), "pain");
  assert.equal(zones.has("x"), false);
  assert.equal(classOf(view, "none").size, 0);
});

test("legend rows count the boxes in each class", () => {
  const rows = legendRows(rolesView(), "role");
  assert.deepEqual(rows.map((r) => [r.key, r.count]), [["entry", 1], ["between", 1], ["foundation", 1], ["alone", 2]]);
  assert.equal(rows[0].name, "entry point");
  assert.equal(rows[0].focus, "entry points");
  assert.equal(legendRows(rolesView(), "zone").find((r) => r.key === "pain").count, 0);
});

test("an old zones option becomes the Zone scheme", () => {
  assert.equal(schemeFromOptions({ zones: true }), "zone");
  assert.equal(schemeFromOptions({ colour: "instability", zones: true }), "instability");
  assert.equal(schemeFromOptions({ colour: "bogus" }), "role");
  assert.equal(schemeFromOptions({}), "role");
});

// The light :root block and the dark block of app.css, as {token: value}.
function cssTokens() {
  const css = readFileSync(new URL("../../src/archview/ui/app.css", import.meta.url), "utf8");
  const block = (start) => {
    const open = css.indexOf("{", css.indexOf(":root", start));
    return Object.fromEntries([...css.slice(open, css.indexOf("}", open)).matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
  };
  return { light: block(0), dark: block(css.indexOf("prefers-color-scheme: dark")) };
}

test("every scheme fill keeps its label readable in both themes", () => {
  const tokens = new Set(["--pkg-fill", "--mod-fill", "--abs-fill"]);
  for (const list of Object.values(CLASSES)) for (const c of list) tokens.add(c.token);
  const { light, dark } = cssTokens();
  for (const [theme, values] of Object.entries({ light, dark })) {
    for (const token of tokens) {
      const fill = values[token];
      assert.ok(fill, `${token} is missing from the ${theme} block`);
      const ratio = contrast(inkFor(fill), fill);
      assert.ok(ratio >= 4.5, `${theme} ${token} ${fill}: label contrast ${ratio.toFixed(2)}`);
    }
  }
});

test("the halo behind a red cycle name keeps it readable in both themes", () => {
  const { light, dark } = cssTokens();
  for (const red of [light["--danger"], dark["--danger"]]) {
    assert.ok(contrast(inkFor(red), red) >= 4.5, `${red}: halo contrast ${contrast(inkFor(red), red).toFixed(2)}`);
  }
});

test("the light palette matches app.css", () => {
  const { light } = cssTokens();
  for (const [token, value] of Object.entries(LIGHT)) assert.equal(value, light[token], token);
});

test("an abstract box's name is italic under every scheme", () => {
  const view = sampleView();
  const layout = { w: 300, h: 200, nodes: Object.fromEntries(view.nodes.map((n, i) => [n.id, { x: 50 + i * 90, y: 50, w: 80, h: 40 }])), clusters: [], routes: {} };
  for (const scheme of ["role", "instability", "zone", "none"]) {
    const svg = drawSvg(view, layout, { scheme });
    const start = svg.indexOf('data-id="core.api"');
    assert.ok(svg.slice(start, svg.indexOf("</g>", start)).includes('font-style="italic"'), scheme);
  }
});

test("a scheme fills each box with its class colour", () => {
  const view = sampleView();
  const layout = { w: 300, h: 200, nodes: Object.fromEntries(view.nodes.map((n, i) => [n.id, { x: 50 + i * 90, y: 50, w: 80, h: 40 }])), clusters: [], routes: {} };
  const svg = drawSvg(view, layout, { scheme: "role" });
  assert.ok(svg.includes("fill:var(--role-entry)"));
  assert.ok(!drawSvg(view, layout, { scheme: "none" }).includes("fill:var("));
});
