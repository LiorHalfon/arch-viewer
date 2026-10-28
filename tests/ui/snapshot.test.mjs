import assert from "node:assert/strict";
import { test } from "node:test";

import { answerFrom, snapshotKey } from "../../src/archview/ui/snapshot.js";

test("a key is the endpoint and its parameters sorted by name, unencoded", () => {
  assert.equal(snapshotKey("/api/view?root=pizzeria&hide_tests=true"), "view?hide_tests=true&root=pizzeria");
  assert.equal(snapshotKey("/api/source?module=src%2Fa%2Fb.ts"), "source?module=src/a/b.ts");
  assert.equal(snapshotKey("/api/project"), "project");
});

test("an answer comes from the snapshot, and a missing one says so", () => {
  const answers = { "tree?root=a": { id: "a" }, "export?format=dot&root=a": "digraph" };
  assert.deepEqual(answerFrom(answers, "/api/tree?root=a"), { id: "a" });
  assert.equal(answerFrom(answers, "/api/export?root=a&format=dot"), "digraph");
  assert.throws(() => answerFrom(answers, "/api/tree?root=b"), /tree\?root=b is not part of this demo/);
});
