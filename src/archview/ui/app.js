// archview viewer: one root at a time, laid out by Graphviz (viz-js) and drawn by
// draw.js, drill down by click. Every root keeps its own zoom and scroll position,
// so Back returns to where you were.

import { classOf, LIGHT, schemeFromOptions } from "./colour.js";
import { enableDrag, layoutKey, loadMoved, saveMoved } from "./drag.js";
import { drawSvg, edgeGeometry } from "./draw.js";
import { flatten } from "./find.js";
import { bounds, clusterFrames, layoutView, routesAfterMove, straightRoute } from "./layout.js";
import { createFinder, hideCard, renderLegend, renderMetricsPanel, showCard, ZONE_NAMES } from "./widgets.js";

const $ = (id) => document.getElementById(id);
const state = {
  viz: null,
  project: null,
  isWorkspace: false,   // the server has a [archview.workspace] table
  package: null,        // the workspace member currently drilled into, or null at its top
  root: null,
  view: null,
  layout: null,         // Graphviz's layout of the current view (layout.js)
  moved: new Map(),     // boxes moved by hand in the current view: id -> {x, y}
  routes: {},           // the current view's edge routes (Graphviz's, or routed again after a drop)
  views: new Map(),     // "root=..&package=..&externals=..&hide_tests=.." -> view payload
  places: new Map(),    // "package|root" -> {zoom, left, top}
  zoom: 1,
  natural: { w: 0, h: 0 },
  sticky: null,         // {ids, label} while a focus is pinned
  metricsPanel: null,   // the metrics panel's handle while it is open
  pendingFlash: null,   // a box quick find picked, flashed once its level is shown
  trees: new Map(),     // "package|root|tests" -> tree payload
  expanded: new Set(),  // package ids opened in place in the file drawer
  source: null,         // module whose source is in the panel
  options: { tests: false, externals: false, colour: "role", legend: true, tree: true },
  palette: null,        // the theme's colour tokens, read from app.css, for label ink
};

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
// A view payload carries its own project/separator/language (M8: each workspace
// member, or the workspace itself, has its own) - fall back to the plain project
// summary before the first view has loaded.
const sep = () => (state.view ? state.view.separator : state.project.separator) || ".";
const fileSuffix = () => ((state.view ? state.view.language : state.project.language) === "python" ? ".py" : "");
const inProject = (id) => {
  const project = state.view ? state.view.project : state.project.project;
  return id === project || id.startsWith(project + sep());
};
const short = (id) => (inProject(id) ? id.split(sep()).pop() : id);
const placeKey = (pkg, root) => `${pkg || ""}|${root}`;
const hrefFor = (root, pkg) => `#/${encodeURIComponent(root)}${pkg ? `?package=${encodeURIComponent(pkg)}` : ""}`;
// At the workspace's own top level (no package drilled into yet), every node is a
// sibling package: clicking one enters it rather than drilling within the same model.
const enterOrOpen = (id) => go(id, state.isWorkspace && !state.package ? id : state.package);
const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;
const num = (v) => (v === null || v === undefined ? "–" : Number(v).toFixed(2));
const parentOf = (id) => (inProject(id) && id.includes(sep()) ? id.slice(0, id.lastIndexOf(sep())) : null);
const WARNING_LABELS = { dynamic_import: "dynamic import", unresolved_import: "unresolved import" };
const GRAMMARS = { ts: "typescript", tsx: "typescript", mts: "typescript", cts: "typescript", js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript" };
// The highlight.js grammar for one file; an unknown one would throw, so fall back.
const grammarOf = (file) => {
  const name = GRAMMARS[String(file || "").split(".").pop().toLowerCase()] || "python";
  return window.hljs && hljs.getLanguage(name) ? name : "plaintext";
};

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return response.headers.get("content-type")?.includes("json") ? response.json() : response.text();
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.hidden = true; }, 2400);
}

// ---------- options (remembered per browser) ----------

function loadOptions() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("archview.options") || "{}") || {}; } catch { /* storage unavailable */ }
  Object.assign(state.options, saved);
  state.options.colour = schemeFromOptions(saved);
  delete state.options.zones;  // before M13 this was a checkbox; schemeFromOptions reads it
}

function paletteFromCss() {
  const css = getComputedStyle(document.documentElement);
  return Object.fromEntries(Object.keys(LIGHT).map((token) => [token, css.getPropertyValue(token).trim()]));
}

function saveOptions() {
  try { localStorage.setItem("archview.options", JSON.stringify(state.options)); } catch { /* storage unavailable */ }
}

function applyOptions() {
  $("opt-tests").checked = state.options.tests;
  $("opt-externals").checked = state.options.externals;
  document.querySelectorAll('input[name="colour"]').forEach((r) => { r.checked = r.value === state.options.colour; });
  $("opt-legend").checked = state.options.legend;
  $("legend").hidden = !state.options.legend;
  $("tree").hidden = !state.options.tree;
  $("main").classList.toggle("with-tree", state.options.tree);
  $("tree-toggle").setAttribute("aria-expanded", String(state.options.tree));
  $("tree-toggle").classList.toggle("on", state.options.tree);
}

function viewQuery(root, pkg = state.package) {
  const q = new URLSearchParams({ root });
  if (pkg) q.set("package", pkg);
  if (state.options.externals) q.set("externals", "true");
  if (state.options.tests) q.set("hide_tests", "true");
  return q.toString();
}

// ---------- navigation ----------

// The hash is `#/<root>` or, once inside a workspace package, `#/<root>?package=<pkg>`.
function placeFromHash() {
  const hash = location.hash.replace(/^#\/?/, "");
  const [rootPart, query] = hash.split("?");
  const root = decodeURIComponent(rootPart || "");
  if (!root) return { root: state.project.project, package: null };
  return { root, package: new URLSearchParams(query || "").get("package") };
}

function go(root, pkg = state.package) {
  const target = hrefFor(root, pkg);
  if (location.hash === target) show(root, pkg);
  else location.hash = target;
}

function rememberPlace() {
  if (!state.root) return;
  const stage = $("stage");
  state.places.set(placeKey(state.package, state.root), { zoom: state.zoom, left: stage.scrollLeft, top: stage.scrollTop });
}

async function loadView(root, pkg = state.package) {
  const key = viewQuery(root, pkg);
  if (!state.views.has(key)) state.views.set(key, await api(`/api/view?${key}`));
  return state.views.get(key);
}

async function show(root, pkg = state.package, { keepPanel = false, refit = false } = {}) {
  const key = placeKey(pkg, root);
  if (refit) state.places.delete(key);
  else rememberPlace();
  let view;
  try {
    view = await loadView(root, pkg);
  } catch (error) {
    $("graph").innerHTML = `<p class="hint">${esc(error.message)}</p>`;
    return;
  }
  if (state.root !== root || state.package !== pkg) state.sticky = null;
  state.root = root;
  state.package = pkg;
  state.view = view;
  document.title = `${root} · archview`;
  crumbs(root);
  stats(view);
  rulesButton();
  // The metrics panel stays open across navigation and redraws for the new view.
  const metricsOpen = !!state.metricsPanel;
  if (!keepPanel && !metricsOpen) closePanel();
  layOut(view);
  draw(view);
  resetButton();
  notes();
  legend();
  if (metricsOpen) openMetricsPanel();
  drawTree();
  const place = state.places.get(key);
  setZoom(place ? place.zoom : fitZoom(), false);
  const stage = $("stage");
  stage.scrollLeft = place ? place.left : 0;
  stage.scrollTop = place ? place.top : 0;
  $("up").disabled = !view.parent;
  if (state.sticky) focusOn(state.sticky.ids, state.sticky);
  if (state.pendingFlash) {
    flashInView(state.pendingFlash);
    state.pendingFlash = null;
  }
}

function crumbs(root) {
  const el = $("crumbs");
  el.innerHTML = "";
  if (state.isWorkspace) {
    if (!state.package) {
      el.insertAdjacentHTML("beforeend", `<span class="here">${esc(state.project.project)}</span>`);
      return;
    }
    const a = document.createElement("a");
    a.textContent = state.project.project;
    a.href = hrefFor(state.project.project, null);
    el.append(a);
    el.insertAdjacentHTML("beforeend", '<span class="sep">/</span>');
  }
  const parts = root.split(sep());
  parts.forEach((part, i) => {
    const id = parts.slice(0, i + 1).join(sep());
    if (i) el.insertAdjacentHTML("beforeend", '<span class="sep">/</span>');
    if (id === root) {
      el.insertAdjacentHTML("beforeend", `<span class="here">${esc(part)}</span>`);
    } else {
      const a = document.createElement("a");
      a.textContent = part;
      a.href = hrefFor(id, state.package);
      el.append(a);
    }
  });
}

function warningSummary(warnings) {
  const byKind = {};
  warnings.forEach((w) => { byKind[w.kind] = (byKind[w.kind] || 0) + 1; });
  return Object.keys(byKind)
    .sort()
    .map((kind) => plural(byKind[kind], WARNING_LABELS[kind] || kind.replace(/_/g, " ")))
    .join(" · ");
}

// `state.project`'s counts (failing rules, warnings) are always workspace-wide once
// inside a workspace - `/api/project` has no `package=` (M8) - so `rulesButton()`
// and `stats()` use this to say so plainly while browsing one package, rather than
// reading as if the numbers were scoped to it.
function insideAPackage() {
  return state.isWorkspace && !!state.package;
}

function stats(view) {
  const parts = [plural(view.nodes.length, "box", "boxes"), plural(view.edges.length, "dependency", "dependencies")];
  parts.push(view.cycles.length ? `<span class="bad">${plural(view.cycles.length, "cycle")}</span>` : "no cycles");
  const violations = view.edges.filter((e) => e.violation).length;
  if (violations) parts.push(`<span class="bad">${plural(violations, "rule break")}</span>`);
  const warnings = state.project.warnings;
  if (warnings.length) {
    const scoped = insideAPackage();
    const title = "Imports the analysis could not resolve or follow" + (scoped ? " - workspace-wide, not just this package" : "");
    parts.push(`<button class="link" id="show-warnings" title="${esc(title)}">⚠ ${scoped ? "workspace: " : ""}${warningSummary(warnings)}</button>`);
  }
  $("stats").innerHTML = parts.join(" · ");
  const button = $("show-warnings");
  if (button) button.onclick = openWarnings;
}

function cycleText(cycle) {
  const names = cycle.map(short);
  return names.length === 2 ? `${names[0]} → ${names[1]} → ${names[0]}` : `tangle of ${names.length}: ${names.join(", ")}`;
}

function notes() {
  const view = state.view;
  const el = $("notes");
  const sections = [];
  if (state.sticky) {
    sections.push(`<section class="focus-bar">Focus: <strong>${esc(state.sticky.label)}</strong> <button id="clear-focus">Clear</button></section>`);
  }
  if (view.cycles.length) {
    sections.push(`<section><h2>Cycles at this level</h2><ul>${view.cycles
      .map((c, i) => `<li data-cycle="${i}" title="Highlight">${esc(cycleText(c))}</li>`).join("")}</ul></section>`);
  }
  el.hidden = sections.length === 0;
  el.innerHTML = sections.join("");
  el.querySelectorAll("li[data-cycle]").forEach((li) => {
    const cycle = view.cycles[Number(li.dataset.cycle)];
    li.onclick = () => pin(new Set(cycle), cycleText(cycle), false);
  });
  const clear = $("clear-focus");
  if (clear) clear.onclick = clearFocus;
}

// ---------- drawing ----------

function draw(view) {
  const graph = $("graph");
  graph.innerHTML = "";
  hideCard();
  if (!state.layout) {
    graph.innerHTML = '<p class="hint">Nothing to show at this level.</p>';
    return;
  }
  const at = positions();
  const clusters = clusterFrames(state.layout, at);
  const box = drawingBox(at, clusters);
  graph.innerHTML = drawSvg(view, state.layout, {
    positions: at, routes: state.routes, clusters, box, weighted: true, scheme: state.options.colour, palette: state.palette,
  });
  state.natural = { w: box.w, h: box.h };
  const svg = graph.querySelector("svg");
  wire(svg, view);
  enableDrag(svg, { toSvgPoint: (e) => svgPoint(svg, e), onMove: previewMove, onDrop: dropBox, onCancel: redraw });
}

// ---------- layout and dragging ----------

const storage = (() => {
  try { return window.localStorage; } catch { return null; }
})();

const viewKey = () => layoutKey({
  repo: state.project.repo, project: state.view.project, package: state.package,
  root: state.root, externals: state.options.externals, hideTests: state.options.tests,
});

// Lay the view out with Graphviz, then put back the boxes moved in it before.
function layOut(view) {
  state.layout = view.nodes.length ? layoutView(state.viz, view.dot) : null;
  state.moved = state.layout ? loadMoved(storage, viewKey(), new Set(Object.keys(state.layout.nodes))) : new Map();
  state.routes = state.layout ? state.layout.routes : {};
  if (state.moved.size) state.routes = routesFor(new Set(state.moved.keys()), state.layout.routes);
}

const positions = () => Object.fromEntries(state.moved);
const centre = (id) => state.moved.get(id) || state.layout.nodes[id];

function routesFor(moved, previous) {
  const started = performance.now();
  const edges = state.view.edges.map(({ source, target }) => ({ source, target }));
  const routes = routesAfterMove(state.viz, state.layout, positions(), edges, previous, moved);
  console.debug("archview: rerouted in", Math.round(performance.now() - started), "ms");
  return routes;
}

// Graphviz's own SVG pads the drawing by 4 points; a box dragged past that grows it.
function drawingBox(at, clusters) {
  const pad = { x: -4, y: -4, w: state.layout.w + 8, h: state.layout.h + 8 };
  if (!state.moved.size) return pad;
  const b = bounds(state.layout, at, state.routes, clusters, 4);
  const x = Math.min(pad.x, b.x), y = Math.min(pad.y, b.y);
  return { x, y, w: Math.max(pad.x + pad.w, b.x + b.w) - x, h: Math.max(pad.y + pad.h, b.y + b.h) - y };
}

function svgPoint(svg, e) {
  const p = svg.createSVGPoint();
  p.x = e.clientX;
  p.y = e.clientY;
  return p.matrixTransform(svg.getScreenCTM().inverse());
}

// While a box moves, its own lines follow as straight dashes; the rest stay.
function previewMove(id, by) {
  hideCard();
  const svg = $("graph").querySelector("svg");
  svg.querySelector(`g.node[data-id="${CSS.escape(id)}"]`).setAttribute("transform", `translate(${by.x} ${by.y})`);
  const from = centre(id);
  const at = (other) => (other === id ? { x: from.x + by.x, y: from.y + by.y } : centre(other));
  svg.querySelectorAll("g.edge").forEach((g) => {
    const { source, target } = g.dataset;
    if (source !== id && target !== id) return;
    const line = g.querySelector(".line");
    const route = straightRoute(at(source), state.layout.nodes[source], at(target), state.layout.nodes[target]);
    const geo = edgeGeometry(route, Number.parseFloat(line.getAttribute("stroke-width")) || 1);
    line.setAttribute("d", geo.d);
    g.querySelector(".hit").setAttribute("d", geo.d);
    g.querySelector(".arrow")?.setAttribute("points", geo.arrow);
    const count = g.querySelector(".count");
    if (count && geo.label) {
      count.setAttribute("x", geo.label[0]);
      count.setAttribute("y", geo.label[1]);
    }
    g.classList.add("preview");
  });
}

function dropBox(id, by) {
  const from = centre(id);
  state.moved.set(id, { x: from.x + by.x, y: from.y + by.y });
  saveMoved(storage, viewKey(), state.moved);
  state.routes = routesFor(new Set([id]), state.routes);
  redraw();
  resetButton();
}

function resetLayout() {
  state.moved = new Map();
  saveMoved(storage, viewKey(), state.moved);
  state.routes = state.layout ? state.layout.routes : {};
  redraw();
  resetButton();
}

function resetButton() {
  $("reset-layout").disabled = !state.moved.size;
}

// Draw the current view again in place: same zoom, scroll and pinned focus.
function redraw() {
  if (!state.view) return;
  const stage = $("stage");
  const { scrollLeft, scrollTop } = stage;
  draw(state.view);
  setZoom(state.zoom, false);
  stage.scrollLeft = scrollLeft;
  stage.scrollTop = scrollTop;
  if (state.sticky) focusOn(state.sticky.ids, state.sticky);
}

function nodeById(id) {
  return state.view.nodes.find((n) => n.id === id);
}

function wire(svg, view) {
  svg.querySelectorAll("g.node").forEach((g) => {
    const id = g.dataset.id;
    const node = nodeById(id);
    g.setAttribute("aria-label", tooltip(node));
    g.onclick = (e) => {
      if (e.shiftKey || e.altKey || node.kind === "external") return openNode(node);
      return node.has_children ? enterOrOpen(id) : openSource(id);
    };
    g.oncontextmenu = (e) => { e.preventDefault(); openNode(node); };
    g.onmouseenter = () => {
      if (svg.classList.contains("dragging")) return;
      if (!state.sticky) focusOn(new Set([id]));
      showCard($("stage").parentElement, node, state.view, g.getBoundingClientRect(), { drag: true });
      state.metricsPanel?.mark(id);
    };
    g.onmouseleave = () => {
      if (!state.sticky) unfocus();
      hideCard();
      state.metricsPanel?.mark(null);
    };
  });
  svg.querySelectorAll("g.edge").forEach((g) => {
    const { source, target } = g.dataset;
    const edge = view.edges.find((e) => e.source === source && e.target === target);
    const flags = [edge.violation && "breaks a rule", edge.in_cycle && "in a cycle", edge.abstract && "to an abstraction", edge.type_checking && "type checking only"].filter(Boolean);
    g.querySelector("title").textContent = `${short(source)} → ${short(target)}: ${plural(edge.count, "import")}${flags.length ? ` (${flags.join(", ")})` : ""}`;
    g.onclick = () => openEdge(edge);
  });
}

function tooltip(node) {
  const lines = [node.id];
  if (node.kind === "package") lines.push(plural(node.module_count, "module"));
  if (node.kind === "external") lines.push("third-party package");
  else lines.push(`I ${num(node.instability)} · A ${num(node.abstractness)} · D ${num(node.distance)} · ${ZONE_NAMES[node.zone]}`);
  lines.push(`imports ${node.fan_out} · imported ${node.fan_in} · layer ${node.layer}`);
  if (node.abstract) lines.push("abstract");
  if (node.in_cycle) lines.push("part of a cycle at this level");
  if (node.tangled) lines.push("has a cycle inside");
  lines.push(node.kind === "external" ? "click for details" : node.has_children ? "click to open · shift-click for details" : "click for source · shift-click for details");
  return lines.join("\n");
}

// ---------- focus (V10) ----------

function focusOn(ids, pinned = null) {
  const svg = $("graph").querySelector("svg");
  if (!svg) return;
  svg.classList.add("focusing");
  const single = ids.size === 1 && !(pinned && pinned.strict);
  // Direction colours follow one box: the hovered one, or the one a focus was pinned on.
  const focus = !pinned && ids.size === 1 ? [...ids][0] : pinned?.root ?? null;
  const shown = new Set(ids);
  svg.querySelectorAll("g.edge").forEach((g) => {
    const related = single
      ? ids.has(g.dataset.source) || ids.has(g.dataset.target)
      : ids.has(g.dataset.source) && ids.has(g.dataset.target);
    g.classList.toggle("related", related);
    g.classList.toggle("out", focus !== null && g.dataset.source === focus);
    g.classList.toggle("in", focus !== null && g.dataset.target === focus);
    if (related && single) { shown.add(g.dataset.source); shown.add(g.dataset.target); }
  });
  svg.querySelectorAll("g.node").forEach((g) => {
    g.classList.toggle("related", shown.has(g.dataset.id));
    g.classList.toggle("focus-root", !!pinned && pinned.root === g.dataset.id);
  });
}

function unfocus() {
  const svg = $("graph").querySelector("svg");
  if (svg) svg.classList.remove("focusing");
}

// `pick`: the legend class this focus picks out, so its row shows as pressed.
function pin(ids, label, strict = true, root = null, pick = null) {
  state.sticky = { ids, label, strict, root, pick };
  focusOn(ids, state.sticky);
  notes();
  legend();
}

function clearFocus() {
  state.sticky = null;
  unfocus();
  notes();
  legend();
}

// ---------- colour and legend ----------

function setScheme(scheme) {
  if (state.sticky?.pick) clearFocus();
  state.options.colour = scheme;
  saveOptions();
  applyOptions();
  redraw();
  legend();
}

function pickClass(row) {
  if (state.sticky?.pick === row.key) return clearFocus();
  if (!row.count) return;
  const ids = [...classOf(state.view, state.options.colour)].filter(([, key]) => key === row.key).map(([id]) => id);
  pin(new Set(ids), row.focus, true, null, row.key);
}

function legend() {
  if (!state.view) return;
  renderLegend($("legend"), state.view, state.options.colour, {
    picked: state.sticky?.pick ?? null,
    onScheme: setScheme,
    onPick: pickClass,
    onExplain: openMetricsPanel,
  });
}

// ---------- the metrics panel ----------

function openMetricsPanel() {
  $("view-menu").open = false;
  const body = openPanel(`<h2>What instability, abstractness and zones mean</h2><div class="sub">${esc(state.root)}</div>`, "");
  state.metricsPanel = renderMetricsPanel(body, state.view, state.view.threshold ?? 0.3, {
    onHoverBox: (id) => {
      if (state.sticky) return;
      if (id) focusOn(new Set([id]));
      else unfocus();
    },
    onClickBox: flash,
  });
}

// Two pulses of a ring around the box (a steady ring with reduced motion).
function flash(id) {
  const g = document.querySelector(`#graph g.node[data-id="${CSS.escape(id)}"]`);
  if (!g) return;
  g.classList.remove("flash");
  void g.getBoundingClientRect();  // restart the animation
  g.classList.add("flash");
  g.addEventListener("animationend", () => g.classList.remove("flash"), { once: true });
}

function reach(start, forward) {
  const seen = new Set([start]);
  const queue = [start];
  while (queue.length) {
    const id = queue.shift();
    for (const e of state.view.edges) {
      const [from, to] = forward ? [e.source, e.target] : [e.target, e.source];
      if (from === id && !seen.has(to)) { seen.add(to); queue.push(to); }
    }
  }
  return seen;
}

// ---------- file drawer (V15) ----------

// The packages and modules under a root (all of a member's when `root` is null),
// cached per Hide tests setting; the file drawer and quick find share it.
async function treeFor(pkg, root) {
  const key = `${placeKey(pkg, root)}|${state.options.tests}`;
  if (!state.trees.has(key)) {
    const q = new URLSearchParams(root ? { root } : {});
    if (pkg) q.set("package", pkg);
    if (state.options.tests) q.set("hide_tests", "true");
    state.trees.set(key, await api(`/api/tree?${q}`));
  }
  return state.trees.get(key);
}

async function drawTree() {
  if (!state.options.tree || !state.root) return;
  const root = state.root;
  const pkg = state.package;
  let tree;
  try {
    tree = await treeFor(pkg, root);
  } catch (error) {
    $("tree-head").innerHTML = "";
    $("tree-body").innerHTML = `<p class="hint">${esc(error.message)}</p>`;
    return;
  }
  if (root !== state.root || pkg !== state.package) return;
  renderTree(tree);
}

// ---------- quick find ----------

let finder = null;

async function findEntries() {
  if (state.isWorkspace && !state.package) {
    const members = state.project.packages;
    const trees = await Promise.all(members.map((member) => treeFor(member, null)));
    return trees.flatMap((tree, i) => flatten(tree, members[i]));
  }
  const project = state.view ? state.view.project : state.project.project;
  return flatten(await treeFor(state.package, project), state.package);
}

// Open the level that draws the match and flash it there.
function pickFound(entry) {
  const pkg = entry.member ?? state.package;
  if (entry.id === state.root && pkg === state.package) return;
  if (entry.parent === null) {
    if (!state.isWorkspace) return go(entry.id, null);
    state.pendingFlash = entry.member;
    return go(state.project.project, null);
  }
  if (entry.parent === state.root && pkg === state.package) return flashInView(entry.id);
  state.pendingFlash = entry.id;
  go(entry.parent, pkg);
}

function flashInView(id) {
  document.querySelector(`#graph g.node[data-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  flash(id);
}

function treeRows(nodes, depth) {
  return nodes.map((node) => {
    const pkg = node.kind === "package";
    const open = pkg && state.expanded.has(node.id);
    const classes = ["row", node.kind, node.abstract && "abstract", node.tangled && "tangled", node.id === state.source && "current"].filter(Boolean).join(" ");
    const twisty = pkg
      ? `<span class="twisty" data-toggle="${esc(node.id)}" role="button" aria-label="${open ? "Collapse" : "Expand"} ${esc(node.name)}">${open ? "▾" : "▸"}</span>`
      : '<span class="twisty"></span>';
    const hint = pkg ? `open ${node.id}` : `source of ${node.id}`;
    return `<li role="treeitem"${pkg ? ` aria-expanded="${open}"` : ""}>
      <div class="${classes}" style="--depth:${depth}" data-id="${esc(node.id)}" data-kind="${node.kind}" title="${esc(hint)}">${twisty}<span class="sw sw-${pkg ? "pkg" : "mod"}"></span><span class="name">${esc(node.name)}${pkg ? "/" : fileSuffix()}</span></div>
      ${open ? `<ul role="group">${treeRows(node.children, depth + 1)}</ul>` : ""}
    </li>`;
  }).join("");
}

function renderTree(tree) {
  const body = $("tree-body");
  const scroll = body.scrollTop;
  $("tree-head").innerHTML = `<span class="name" title="${esc(tree.id)}">${esc(tree.name)}/</span>`;
  const up = tree.parent
    ? `<li><div class="row up" style="--depth:0" data-up="${esc(tree.parent)}" title="Up to ${esc(tree.parent)} (u)"><span class="twisty"></span><span class="name">..</span></div></li>`
    : "";
  body.innerHTML = tree.children.length || up
    ? `<ul role="tree">${up}${treeRows(tree.children, 0)}</ul>`
    : '<p class="hint">Empty.</p>';
  body.scrollTop = scroll;
  body.onclick = (e) => {
    const toggle = e.target.closest("[data-toggle]");
    if (toggle) {
      const id = toggle.dataset.toggle;
      if (!state.expanded.delete(id)) state.expanded.add(id);
      return renderTree(tree);
    }
    const row = e.target.closest(".row");
    if (!row) return;
    if (row.dataset.up) return go(row.dataset.up);
    return row.dataset.kind === "package" ? go(row.dataset.id) : openSource(row.dataset.id);
  };
}

function toggleTree() {
  state.options.tree = !state.options.tree;
  saveOptions();
  applyOptions();
  drawTree();
}

// ---------- zoom ----------

function fitZoom() {
  const stage = $("stage");
  const { w, h } = state.natural;
  if (!w || !h) return 1;
  const fit = Math.min((stage.clientWidth - 48) / w, (stage.clientHeight - 48) / h);
  return Math.max(0.2, Math.min(1.5, fit));
}

function setZoom(zoom, keepCentre = true) {
  const svg = $("graph").querySelector("svg");
  if (!svg) return;
  const stage = $("stage");
  const next = Math.max(0.1, Math.min(4, zoom));
  const ratio = next / state.zoom;
  const cx = stage.scrollLeft + stage.clientWidth / 2;
  const cy = stage.scrollTop + stage.clientHeight / 2;
  state.zoom = next;
  svg.style.width = `${state.natural.w * next}px`;
  svg.style.height = `${state.natural.h * next}px`;
  if (keepCentre) {
    stage.scrollLeft = cx * ratio - stage.clientWidth / 2;
    stage.scrollTop = cy * ratio - stage.clientHeight / 2;
  }
}

// ---------- panel ----------

function openPanel(titleHtml, bodyHtml, code = false) {
  if (!code && state.source) { state.source = null; drawTree(); }
  state.metricsPanel = null;  // any panel replaces the metrics panel; openMetricsPanel sets it again
  $("main").classList.add("with-panel");
  $("panel").hidden = false;
  $("panel-title").innerHTML = titleHtml;
  const body = $("panel-body");
  body.className = `panel-body${code ? " code" : ""}`;
  body.innerHTML = bodyHtml;
  body.scrollTop = 0;
  return body;
}

function closePanel() {
  state.metricsPanel = null;
  $("main").classList.remove("with-panel");
  $("panel").hidden = true;
  if (state.source) { state.source = null; drawTree(); }
  document.querySelectorAll("#graph .selected").forEach((g) => g.classList.remove("selected"));
}

function select(selector) {
  document.querySelectorAll("#graph .selected").forEach((g) => g.classList.remove("selected"));
  if (selector) document.querySelectorAll(selector).forEach((g) => g.classList.add("selected"));
}

function importItems(imports, showTarget) {
  return imports.map((i, n) => {
    const flags = [i.violation && '<span class="badge warn">breaks a rule</span>', i.type_checking && '<span class="badge flag">type checking</span>', i.lazy && '<span class="badge flag">inside a function</span>'].filter(Boolean).join(" ");
    return `<li data-n="${n}" class="${i.violation ? "violation" : ""}">
      <div class="where">${esc(i.file)}:${i.line} ${flags}</div>
      <div class="text">${esc(i.text.trim())}</div>
      ${showTarget ? `<div class="target">${esc(i.importer)} → ${esc(i.imported)}</div>` : ""}
    </li>`;
  }).join("");
}

function wireImports(container, imports) {
  container.querySelectorAll(".imports li").forEach((li) => {
    const imp = imports[Number(li.dataset.n)];
    li.onclick = () => openSource(imp.importer, imp.line);
  });
}

function openEdge(edge) {
  select(`#graph g.edge[data-source="${CSS.escape(edge.source)}"][data-target="${CSS.escape(edge.target)}"]`);
  const badges = [
    edge.violation && '<span class="badge warn">breaks a rule</span>',
    edge.in_cycle && '<span class="badge">cycle</span>',
    edge.abstract && '<span class="badge abs">abstraction</span>',
  ].filter(Boolean).join(" ");
  const body = openPanel(
    `<h2>${esc(short(edge.source))} → ${esc(short(edge.target))} ${badges}</h2>
     <div class="sub">${plural(edge.count, "import")}</div>`,
    `<ul class="imports">${importItems(edge.imports, true)}</ul>`,
  );
  wireImports(body, edge.imports);
}

function linkList(edges, pick) {
  if (!edges.length) return '<p class="hint">none</p>';
  return `<ul class="links">${edges.map((e) => `<li data-s="${esc(e.source)}" data-t="${esc(e.target)}">${esc(short(pick(e)))} <span class="n">(${e.count})</span>${e.violation ? ' <span class="badge warn">rule</span>' : ""}</li>`).join("")}</ul>`;
}

function openNode(node) {
  select(`#graph g.node[data-id="${CSS.escape(node.id)}"]`);
  const view = state.view;
  const incoming = view.edges.filter((e) => e.target === node.id);
  const outgoing = view.edges.filter((e) => e.source === node.id);
  const zone = node.zone === "pain" || node.zone === "useless" ? `<span class="zone zone-${node.zone}">${ZONE_NAMES[node.zone]}</span>` : ZONE_NAMES[node.zone];
  const metrics = node.kind === "external" ? "" : `
      <dt>Instability I</dt><dd>${num(node.instability)}</dd>
      <dt>Abstractness A</dt><dd>${num(node.abstractness)}</dd>
      <dt>Distance D</dt><dd>${num(node.distance)}</dd>
      <dt>Zone</dt><dd>${zone}</dd>
      <dt></dt><dd><button class="link" data-explain>What do these mean?</button></dd>`;
  const body = openPanel(
    `<h2>${esc(node.name)} ${node.abstract ? '<span class="badge abs">abstract</span>' : ""}${node.in_cycle ? ' <span class="badge">cycle</span>' : ""}</h2><div class="sub">${esc(node.id)}</div>`,
    `<div class="actions">
       ${node.has_children ? '<button data-act="open">Open</button>' : ""}
       ${node.kind === "module" ? '<button data-act="source">Source</button>' : ""}
       <button data-act="neighbours">Focus neighbours</button>
       <button data-act="reaches" title="Everything this depends on, directly or not">What it reaches</button>
       <button data-act="reached" title="Everything that depends on this, directly or not">What reaches it</button>
     </div>
     <dl class="facts">
       <dt>Kind</dt><dd>${node.kind}${node.kind === "package" ? `, ${plural(node.module_count, "module")}` : ""}</dd>
       <dt>Layer</dt><dd>${node.layer}</dd>
       <dt>Imports</dt><dd>${node.fan_out}</dd>
       <dt>Imported by</dt><dd>${node.fan_in}</dd>
       ${metrics}
     </dl>
     <h3>Depends on</h3>${linkList(outgoing, (e) => e.target)}
     <h3>Depended on by</h3>${linkList(incoming, (e) => e.source)}`,
  );
  const actions = {
    open: () => enterOrOpen(node.id),
    source: () => openSource(node.id),
    neighbours: () => {
      const ids = new Set([node.id]);
      view.edges.forEach((e) => { if (e.source === node.id) ids.add(e.target); if (e.target === node.id) ids.add(e.source); });
      pin(ids, `${node.name} and its neighbours`, false, node.id);
    },
    reaches: () => pin(reach(node.id, true), `what ${node.name} reaches`, true, node.id),
    reached: () => pin(reach(node.id, false), `what reaches ${node.name}`, true, node.id),
  };
  body.querySelectorAll("[data-act]").forEach((b) => { b.onclick = actions[b.dataset.act]; });
  const explain = body.querySelector("[data-explain]");
  if (explain) explain.onclick = openMetricsPanel;
  body.querySelectorAll(".links li").forEach((li) => {
    li.onclick = () => openEdge(view.edges.find((e) => e.source === li.dataset.s && e.target === li.dataset.t));
  });
}

function warningTooltip(w) {
  return w.kind === "unresolved_import" ? "unresolved import: not resolved" : "dynamic import: not followed";
}

async function openSource(module, line = null) {
  let source;
  try {
    const q = new URLSearchParams({ module });
    if (state.package) q.set("package", state.package);
    source = await api(`/api/source?${q}`);
  } catch (error) {
    toast(error.message);
    return;
  }
  select(`#graph g.node[data-id="${CSS.escape(module)}"]`);
  state.source = module;
  drawTree();
  const lines = source.text.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  const byLine = new Map();
  source.imports.forEach((i) => {
    if (!byLine.has(i.line)) byLine.set(i.line, []);
    byLine.get(i.line).push(i);
  });
  const warnedLines = new Map();
  source.warnings.forEach((w) => {
    if (!warnedLines.has(w.line)) warnedLines.set(w.line, []);
    warnedLines.get(w.line).push(w);
  });
  const grammar = grammarOf(source.file);
  const highlighted = window.hljs
    ? hljs.highlight(source.text, { language: grammar, ignoreIllegals: true }).value
    : esc(source.text);
  const gutter = lines.map((_, i) => {
    const n = i + 1;
    const imports = byLine.get(n);
    if (imports) {
      const title = imports.map((x) => `imports ${x.imported}${x.violation ? " (breaks a rule)" : ""}`).join("\n");
      return `<span class="imp" data-line="${n}" title="${esc(title)} (click to open)">${n}</span>`;
    }
    const atLine = warnedLines.get(n);
    return atLine ? `<span title="${esc(atLine.map(warningTooltip).join(" · "))}">${n}⚠</span>` : `<span>${n}</span>`;
  }).join("");
  const bar = (n, cls) => `<div class="mark ${cls}" style="top:calc(8px + ${n - 1} * var(--line))"></div>`;
  const marks = [...byLine.entries()].map(([n, imps]) => bar(n, imps.some((x) => x.violation) ? "target" : "")).join("")
    + (line ? bar(line, "target") : "");

  const flags = source.abstract ? ' <span class="badge abs">abstract</span>' : "";
  const body = openPanel(
    `<h2>${esc(short(module))}${flags}</h2><div class="sub">${esc(source.file)}${line ? `:${line}` : ""}</div>`,
    `<div class="source">${marks}<div class="gutter">${gutter}</div><pre><code class="hljs language-${grammar}">${highlighted}</code></pre></div>`,
    true,
  );
  body.querySelectorAll(".gutter span.imp").forEach((span) => {
    span.onclick = () => openSource(byLine.get(Number(span.dataset.line))[0].imported);
  });
  if (line) {
    const lineHeight = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--line")) || 18;
    body.scrollTop = Math.max(0, (line - 1) * lineHeight - body.clientHeight / 3);
  }
}

function warningTarget(w) {
  if (w.kind === "unresolved_import") return `could not resolve ${esc(w.target)}`;
  return w.target ? `target ${esc(w.target)}` : "target not a literal";
}

function openWarnings() {
  const warnings = state.project.warnings;
  const body = openPanel(
    `<h2>Extraction warnings</h2><div class="sub">not resolved or followed by the analysis or the checker</div>`,
    `<ul class="imports">${warnings.map((w, n) => `<li data-n="${n}">
        <div class="where">${esc(w.file)}:${w.line} <span class="badge flag">${esc(WARNING_LABELS[w.kind] || w.kind)}</span></div>
        <div class="text">${esc(w.text)}</div>
        <div class="target">${warningTarget(w)}</div></li>`).join("")}</ul>`,
  );
  body.querySelectorAll(".imports li").forEach((li) => {
    const w = warnings[Number(li.dataset.n)];
    li.onclick = () => openSource(w.module, w.line);
  });
}

async function openRules() {
  let report;
  try {
    report = await api(`/api/check${state.package ? `?package=${encodeURIComponent(state.package)}` : ""}`);
  } catch (error) {
    toast(error.message);
    return;
  }
  // At a workspace's top level `/api/check` returns the workspace report (M8): the
  // rules between packages, plus each package's own report. Anywhere else, one project.
  const workspace = Boolean(report.between);
  const order = (r) => [...r.problems.filter((p) => p.fails), ...r.problems.filter((p) => !p.fails)];
  const failingIn = (r) => r.problems.filter((p) => p.fails).length
    + (r.scopes || []).reduce((n, s) => n + failingIn(s), 0);
  const shown = [];  // every problem shown, in order: data-p indexes into it across all sections
  const failing = (workspace ? [report.between, ...report.packages] : [report])
    .reduce((n, r) => n + failingIn(r), 0);
  const card = (p) => {
    const i = shown.push(p) - 1;
    const what = p.kind === "cycle" ? cycleText(p.components) : p.components.join(" → ");
    const known = p.baselined ? ` · ${p.baselined} in the baseline` : "";
    const status = p.fails ? "" : p.baselined ? " (known)" : " (reported only)";
    return `<div class="problem ${p.fails ? "" : "known"}">
      <div class="head">${esc(p.kind.replace("_", " "))}: ${esc(what)}${status}</div>
      <div class="sub">${esc(p.rule)} · ${plural(p.count, p.kind === "cycle" ? "edge" : "import")}${known}</div>
      <div class="hint">${esc(p.hint)}</div>
      ${p.imports.length ? `<ul class="imports" data-p="${i}">${importItems(p.imports.slice(0, 20), true)}</ul>` : ""}
    </div>`;
  };
  const section = (r, empty) => {
    const problems = order(r);
    const unused = r.unused_allowances.length
      ? `<h3>Allowed but unused</h3><ul class="links">${r.unused_allowances.map((u) => `<li>${esc(u.from)} → ${esc(u.to)}</li>`).join("")}</ul>` : "";
    const warnings = r.warnings.length
      ? `<h3>Warnings</h3><ul class="links">${r.warnings.map((w) => `<li>${esc(w.message)}</li>`).join("")}</ul>` : "";
    return (problems.length ? problems.map(card).join("") : empty) + unused + warnings;
  };
  const none = '<p class="hint">No problems.</p>';
  const scopeSection = (s) => `<h3 class="group">${esc(s.project)}</h3><div class="sub">${esc(s.rules)} · ${plural(s.components.length, "component")}</div>`
    + section(s, none);
  const scopes = (r) => (r.scopes || []).map(scopeSection).join("");
  const packageSection = (p) => `<h3 class="group">${esc(p.package)}</h3><div class="sub">${plural(p.components.length, "component")}</div>`
    + section(p, none) + scopes(p);
  const [counted, content] = workspace
    ? [plural(report.between.components.length, "package"),
      `<h3 class="group">Between packages</h3>${section(report.between, none)}${report.packages.map(packageSection).join("")}`]
    : [plural(report.components.length, "component"),
      section(report, (report.scopes || []).length ? "" : none) + scopes(report)];
  const body = openPanel(
    `<h2>${failing ? plural(failing, "failing problem") : "Rules pass"}</h2><div class="sub">${esc(state.project.rules)} · ${counted}</div>`,
    content,
  );
  body.querySelectorAll(".imports[data-p]").forEach((ul) => {
    const imports = shown[Number(ul.dataset.p)].imports;
    ul.querySelectorAll("li").forEach((li) => {
      const imp = imports[Number(li.dataset.n)];
      li.onclick = () => openSource(imp.importer, imp.line);
    });
  });
}

function openMetricsTable() {
  $("view-menu").open = false;
  const nodes = state.view.nodes.filter((n) => n.kind !== "external");
  const columns = [
    ["name", "Box"], ["fan_in", "In"], ["fan_out", "Out"], ["instability", "I"], ["abstractness", "A"], ["distance", "D"], ["zone", "Zone"],
  ];
  let sortKey = "distance";
  let descending = true;
  const render = () => {
    const sorted = [...nodes].sort((a, b) => {
      const x = a[sortKey] ?? -1, y = b[sortKey] ?? -1;
      const order = typeof x === "string" ? x.localeCompare(y) : x - y;
      return (descending ? -order : order) || a.name.localeCompare(b.name);
    });
    const rows = sorted.map((n) => `<tr data-id="${esc(n.id)}">
        <td>${esc(n.name)}${n.abstract ? ' <span class="badge abs">abs</span>' : ""}</td><td>${n.fan_in}</td><td>${n.fan_out}</td>
        <td>${num(n.instability)}</td><td>${num(n.abstractness)}</td><td>${num(n.distance)}</td>
        <td><span class="zone zone-${n.zone}">${ZONE_NAMES[n.zone]}</span></td></tr>`).join("");
    const body = openPanel(
      `<h2>Metrics</h2><div class="sub">${esc(state.root)} · I = instability, A = abstractness, D = |A + I − 1| · <button class="link" data-explain>What do these mean?</button></div>`,
      `<table class="metrics"><thead><tr>${columns.map(([k, label]) => `<th data-k="${k}">${label}${k === sortKey ? (descending ? " ▾" : " ▴") : ""}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`,
    );
    $("panel-title").querySelector("[data-explain]").onclick = openMetricsPanel;
    body.querySelectorAll("th").forEach((th) => {
      th.onclick = () => { descending = th.dataset.k === sortKey ? !descending : true; sortKey = th.dataset.k; render(); };
    });
    body.querySelectorAll("tbody tr").forEach((tr) => { tr.onclick = () => openNode(nodeById(tr.dataset.id)); });
  };
  render();
}

// ---------- export (V12) ----------

function download(name, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportView(format) {
  $("export-menu").open = false;
  const base = state.root.replaceAll(sep(), "-");
  if (format === "svg" || format === "png") {
    const svgText = state.viz.renderString(state.view.dot, { format: "svg" });
    if (format === "svg") return download(`${base}.svg`, new Blob([svgText], { type: "image/svg+xml" }));
    const image = new Image();
    image.onload = () => {
      const scale = 2;
      const canvas = document.createElement("canvas");
      canvas.width = image.width * scale;
      canvas.height = image.height * scale;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.scale(scale, scale);
      ctx.drawImage(image, 0, 0);
      canvas.toBlob((blob) => download(`${base}.png`, blob), "image/png");
    };
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgText)}`;
    return;
  }
  const text = await api(`/api/export?format=${format}&${viewQuery(state.root)}`);
  try {
    await navigator.clipboard.writeText(text);
    toast(`${format === "dot" ? "DOT" : "Mermaid"} copied to the clipboard`);
  } catch {
    download(`${base}.${format === "dot" ? "dot" : "mmd"}`, new Blob([text], { type: "text/plain" }));
  }
}

// ---------- reanalysis (V9) ----------

async function refresh(summary, message) {
  state.project = summary;
  state.isWorkspace = !!summary.workspace;
  state.views.clear();
  state.trees.clear();
  rulesButton();
  let root = state.root;
  let pkg = state.package;
  while (root) {
    try { await loadView(root, pkg); break; } catch {
      root = parentOf(root);
      if (!root) pkg = null;
    }
  }
  root = root || summary.project;
  if (root === state.root && pkg === state.package) {
    await show(root, pkg, { keepPanel: true });
  } else {
    go(root, pkg);
  }
  if (message) toast(message);
}

async function reanalyze() {
  const button = $("reanalyze");
  button.disabled = true;
  try {
    const summary = await api("/api/reanalyze", { method: "POST" });
    await refresh(summary, `Reanalyzed: ${plural(summary.modules, "module")}, ${plural(summary.imports, "import")}`);
  } catch (error) {
    toast(`Reanalyze failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function poll() {
  setInterval(async () => {
    try {
      const summary = await api("/api/project");
      if (summary.error && summary.error !== state.project.error) toast(summary.error);
      if (summary.generation !== state.project.generation) await refresh(summary, "Source changed: view updated");
      else state.project = summary;
    } catch { /* server stopped; try again next tick */ }
  }, 2000);
}

function rulesButton() {
  const button = $("rules");
  const p = state.project;
  const scoped = insideAPackage();
  const prefix = scoped ? "Workspace rules" : "Rules";
  button.hidden = !p.rules;
  button.classList.toggle("bad", p.failing > 0 || !!p.rules_error);
  button.textContent = p.rules_error ? `${prefix} ⚠` : p.failing ? `${prefix}: ${p.failing} failing` : `${prefix} ✓`;
  const base = p.rules_error || `archview check against ${p.rules}`;
  button.title = scoped ? `${base} - counts every package in the workspace, not just this one` : base;
}

// ---------- wiring ----------

function bind() {
  $("tree-toggle").onclick = toggleTree;
  $("home").onclick = (e) => { e.preventDefault(); go(state.project.project, null); };
  $("up").onclick = () => {
    if (!state.view || !state.view.parent) return;
    // Up from a package's own root (M8) leaves the package, back to the workspace.
    const leavingPackage = state.isWorkspace && state.root === state.package;
    go(state.view.parent, leavingPackage ? null : state.package);
  };
  $("zoom-in").onclick = () => setZoom(state.zoom * 1.25);
  $("zoom-out").onclick = () => setZoom(state.zoom / 1.25);
  $("zoom-fit").onclick = () => setZoom(fitZoom());
  $("reset-layout").onclick = resetLayout;
  $("reanalyze").onclick = reanalyze;
  $("rules").onclick = openRules;
  $("metrics-table").onclick = openMetricsTable;
  $("panel-close").onclick = closePanel;
  document.querySelectorAll("[data-export]").forEach((b) => { b.onclick = () => exportView(b.dataset.export); });
  const option = (id, key, redraw) => {
    $(id).onchange = () => {
      state.options[key] = $(id).checked;
      saveOptions();
      applyOptions();
      if (redraw) show(state.root, state.package, { refit: true });
    };
  };
  option("opt-tests", "tests", true);
  option("opt-externals", "externals", true);
  document.querySelectorAll('input[name="colour"]').forEach((r) => { r.onchange = () => setScheme(r.value); });
  option("opt-legend", "legend", false);
  $("graph").onclick = (e) => {
    if (e.target.closest("g.node, g.edge")) return;
    if (state.sticky) clearFocus();
  };
  document.addEventListener("click", (e) => {
    document.querySelectorAll("details.menu[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; });
  });
  addEventListener("hashchange", () => { const place = placeFromHash(); show(place.root, place.package); });
  addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || e.target.matches("input, textarea")) return;
    const keys = {
      Escape: () => { closePanel(); if (state.sticky) clearFocus(); },
      u: () => $("up").click(),
      "+": () => $("zoom-in").click(),
      "=": () => $("zoom-in").click(),
      "-": () => $("zoom-out").click(),
      "0": () => $("zoom-fit").click(),
      r: reanalyze,
      t: toggleTree,
      "/": () => finder.open(),
    };
    if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
  });
  finder = createFinder($("stage").parentElement, { load: findEntries, onPick: pickFound });
  $("find").onclick = () => finder.open();
}

async function start() {
  loadOptions();
  applyOptions();
  bind();
  state.palette = paletteFromCss();
  // Label ink is picked from the fill's colour in code, so a theme change redraws.
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    state.palette = paletteFromCss();
    redraw();
  });
  try {
    [state.viz, state.project] = await Promise.all([Viz.instance(), api("/api/project")]);
  } catch (error) {
    $("graph").innerHTML = `<p class="hint">Could not start: ${esc(error.message)}</p>`;
    return;
  }
  state.isWorkspace = !!state.project.workspace;
  rulesButton();
  if (state.project.watching) poll();
  const place = placeFromHash();
  show(place.root, place.package);
}

start();
