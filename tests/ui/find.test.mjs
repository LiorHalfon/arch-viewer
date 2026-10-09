import assert from "node:assert/strict";
import { test } from "node:test";

import { flatten, rank } from "../../src/archview/ui/find.js";

const pkg = (id, children = []) => ({ id, name: id.split(/[./]/).pop(), kind: "package", children });
const mod = (id) => ({ id, name: id.split(/[./]/).pop(), kind: "module", children: [] });

test("a name that starts with the query comes first", () => {
  const tree = pkg("src", [pkg("src.story", [pkg("src.story.providers", [mod("src.story.providers.openai")]), mod("src.story.openai_provider")])]);
  assert.deepEqual(rank(flatten(tree), "prov").map((e) => e.name), ["providers", "openai_provider", "openai"]);
  assert.deepEqual(rank(flatten(tree), "PROV").map((e) => e.name), ["providers", "openai_provider", "openai"]);
});

test("ties go shallow, then packages, then id", () => {
  const tree = pkg("src", [pkg("src.models"), pkg("src.b", [pkg("src.b.models")]), pkg("src.a", [mod("src.a.models"), mod("src.a.models_x")])]);
  assert.deepEqual(rank(flatten(tree), "models").map((e) => e.id), ["src.models", "src.b.models", "src.a.models", "src.a.models_x"]);
});

test("parents come from the nesting, not a separator", () => {
  const tree = pkg("src", [pkg("src/a", [mod("src/a/b.ts")])]);
  const [entry] = rank(flatten(tree), "b.ts");
  assert.deepEqual([entry.id, entry.parent, entry.kind, entry.depth], ["src/a/b.ts", "src/a", "module", 2]);
  const [folder] = rank(flatten(tree), "a");
  assert.deepEqual([folder.id, folder.items, folder.parent], ["src/a", 1, "src"]);
  assert.equal(flatten(tree)[0].parent, null);
});

test("workspace members are searched together", () => {
  const entries = [...flatten(pkg("core", [mod("core.ports")]), "core"), ...flatten(pkg("plugin", [mod("plugin.ports_adapter")]), "plugin")];
  assert.deepEqual(rank(entries, "ports").map((e) => [e.id, e.member]), [["core.ports", "core"], ["plugin.ports_adapter", "plugin"]]);
});

test("ten results at most, none for a blank query", () => {
  const tree = pkg("src", Array.from({ length: 12 }, (_, i) => mod(`src.thing_${String(i).padStart(2, "0")}`)));
  assert.equal(rank(flatten(tree), "thing").length, 10);
  assert.deepEqual(rank(flatten(tree), "   "), []);
  assert.deepEqual(rank(flatten(tree), ""), []);
});
