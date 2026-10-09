import assert from "node:assert/strict";
import { test } from "node:test";

import { legendHtml } from "../../src/archview/ui/widgets.js";
import { sampleView } from "./support.mjs";

const pressed = (html, attr) => {
  const start = html.indexOf(attr);
  return html.slice(start, html.indexOf(">", start)).includes('aria-pressed="true"');
};

test("the legend lists the scheme's classes with their counts", () => {
  const html = legendHtml(sampleView(), "role", {});
  assert.ok(pressed(html, 'data-scheme="role"'));
  assert.ok(!pressed(html, 'data-scheme="zone"'));
  assert.ok(html.includes('data-key="entry"') && html.includes("entry point"));
  assert.match(html, /data-key="entry"[^]*?<span class="ct">1<\/span>/);
});

test("a class with no boxes is greyed", () => {
  assert.ok(legendHtml(sampleView(), "zone", {}).includes('class="item zero" data-key="useless"'));
});

test("the picked row is pressed", () => {
  const html = legendHtml(sampleView(), "role", { picked: "foundation" });
  assert.ok(pressed(html, 'data-key="foundation"'));
  assert.ok(!pressed(html, 'data-key="entry"'));
});

test("the explanation link shows under Instability and Zone when asked", () => {
  assert.ok(legendHtml(sampleView(), "instability", { explain: true }).includes("What is instability?"));
  assert.ok(legendHtml(sampleView(), "zone", { explain: true }).includes("What are the zones?"));
  assert.ok(!legendHtml(sampleView(), "role", { explain: true }).includes('class="about"'));
  assert.ok(!legendHtml(sampleView(), "zone", {}).includes('class="about"'));
});

test("None shows today's box key and nothing to pick", () => {
  const html = legendHtml(sampleView(), "none", {});
  assert.ok(!html.includes("data-key="));
  assert.ok(html.includes("package") && html.includes("abstract"));
});

test("the lines key says thicker means more imports", () => {
  assert.ok(legendHtml(sampleView(), "role", {}).includes("thicker: more imports"));
});
