import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// Every selector in app.css, comments dropped, at-rule preludes included.
function selectors() {
  const css = readFileSync(new URL("../../src/archview/ui/app.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  return [...css.matchAll(/([^{}]+)\{/g)].flatMap((m) => m[1].split(",")).map((s) => s.trim());
}

test("the header's rules stay off the hover card's metric bars", () => {
  // The header and the hover card's bars both carry class="bar"; a bare .bar
  // gives each bar the header's padding and flex, and the fill draws 0px tall.
  assert.deepEqual(selectors().filter((s) => /^\.bar(?![\w-])/.test(s)), []);
});
