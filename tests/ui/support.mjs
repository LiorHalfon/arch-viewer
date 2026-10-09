// Shared fixtures for the UI's Node tests: the vendored Graphviz build and a small view.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const Viz = require("../../src/archview/ui/vendor/viz-global.js");

let instance = null;
export async function loadViz() {
  instance ??= await Viz.instance();
  return instance;
}

// A package published inside a cluster (ADR 0013), a module, and two edges, one abstract.
export const SAMPLE_DOT = `digraph "t" {
  rankdir=TB; newrank=true; splines=true; nodesep=0.5; ranksep=0.9;
  node [shape=box style="rounded,filled" fontname="Helvetica"];
  subgraph "cluster_core" { style="rounded"; label=""; "core" [label="core\\n(3 modules)" shape=component]; "core.api" [label="api"]; }
  "app" [label="app\\n(2 modules)" shape=component];
  "app" -> "core.api" [label="4" arrowhead=onormal];
  "app" -> "core" [label="1"];
}`;

const node = (id, fields) => ({
  id, name: id.split(".").pop(), kind: "package", parent: null, module_count: 1, layer: 0,
  fan_in: 0, fan_out: 0, in_cycle: false, abstract: false, instability: 0.5, abstractness: 0,
  distance: 0.5, zone: "main_sequence", has_children: true, tangled: false, ...fields,
});

const edge = (source, target, count, fields = {}) => ({
  source, target, count, in_cycle: false, abstract: false, type_checking: false, violation: false, imports: [], ...fields,
});

// The view payload that SAMPLE_DOT draws, shaped like /api/view.
export function sampleView() {
  return {
    root: "t",
    nodes: [
      node("app", { module_count: 2, fan_out: 2, instability: 1, zone: "main_sequence" }),
      node("core", { module_count: 3, layer: 1, fan_in: 1, tangled: true, instability: 0, zone: "pain" }),
      node("core.api", { kind: "module", parent: "core", layer: 1, fan_in: 1, abstract: true, has_children: false, instability: 0, abstractness: 1, distance: 0 }),
    ],
    edges: [edge("app", "core.api", 4, { abstract: true }), edge("app", "core", 1)],
    cycles: [],
  };
}
