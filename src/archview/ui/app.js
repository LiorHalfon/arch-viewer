"use strict";

// archview viewer: one root at a time, drawn by Graphviz (viz-js), drill down by click.
// Every root keeps its own zoom and scroll position, so Back returns to where you were.

const $ = (id) => document.getElementById(id);
const state = {
  viz: null,
  project: null,
  isWorkspace: false,   // the server has a [archview.workspace] table
  package: null,        // the workspace member currently drilled into, or null at its top
  root: null,
  view: null,
  views: new Map(),     // "root=..&package=..&externals=..&hide_tests=.." -> view payload
  places: new Map(),    // "package|root" -> {zoom, left, top}
  zoom: 1,
  natural: { w: 0, h: 0 },
  sticky: null,         // {ids, label} while a focus is pinned
  trees: new Map(),     // "package|root|tests" -> tree payload
  expanded: new Set(),  // package ids opened in place in the file drawer
  source: null,         // module whose source is in the panel
  options: { tests: false, externals: false, zones: false, legend: true, tree: true },
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
const ZONE_NAMES = { main_sequence: "main sequence", pain: "zone of pain", useless: "zone of uselessness", isolated: "no dependencies", external: "third-party" };
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
  try { Object.assign(state.options, JSON.parse(localStorage.getItem("archview.options") || "{}")); } catch { /* storage unavailable */ }
}

function saveOptions() {
  try { localStorage.setItem("archview.options", JSON.stringify(state.options)); } catch { /* storage unavailable */ }
}

function applyOptions() {
  $("opt-tests").checked = state.options.tests;
  $("opt-externals").checked = state.options.externals;
  $("opt-zones").checked = state.options.zones;
  $("opt-legend").checked = state.options.legend;
  document.body.classList.toggle("zones", state.options.zones);
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
  if (!keepPanel) closePanel();
  draw(view);
  notes();
  drawTree();
  const place = state.places.get(key);
  setZoom(place ? place.zoom : fitZoom(), false);
  const stage = $("stage");
  stage.scrollLeft = place ? place.left : 0;
  stage.scrollTop = place ? place.top : 0;
  $("up").disabled = !view.parent;
  if (state.sticky) focusOn(state.sticky.ids, state.sticky);
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

function stats(view) {
  const parts = [plural(view.nodes.length, "box", "boxes"), plural(view.edges.length, "dependency", "dependencies")];
  parts.push(view.cycles.length ? `<span class="bad">${plural(view.cycles.length, "cycle")}</span>` : "no cycles");
  const violations = view.edges.filter((e) => e.violation).length;
  if (violations) parts.push(`<span class="bad">${plural(violations, "rule break")}</span>`);
  const warnings = state.project.warnings;
  if (warnings.length) parts.push(`<button class="link" id="show-warnings" title="Imports the analysis could not resolve or follow">⚠ ${warningSummary(warnings)}</button>`);
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
  if (!view.nodes.length) {
    graph.innerHTML = '<p class="hint">Nothing to show at this level.</p>';
    return;
  }
  const svg = state.viz.renderSVGElement(view.dot);
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  const box = svg.viewBox.baseVal;
  state.natural = { w: box.width, h: box.height };
  graph.append(svg);
  wire(svg, view);
}

function nodeById(id) {
  return state.view.nodes.find((n) => n.id === id);
}

function wire(svg, view) {
  svg.querySelectorAll("g.node").forEach((g) => {
    const id = g.querySelector("title").textContent;
    const node = nodeById(id);
    g.dataset.id = id;
    g.querySelector("title").textContent = tooltip(node);
    g.onclick = (e) => {
      if (e.shiftKey || e.altKey || node.kind === "external") return openNode(node);
      return node.has_children ? enterOrOpen(id) : openSource(id);
    };
    g.oncontextmenu = (e) => { e.preventDefault(); openNode(node); };
    g.onmouseenter = () => { if (!state.sticky) focusOn(new Set([id])); };
    g.onmouseleave = () => { if (!state.sticky) unfocus(); };
  });
  svg.querySelectorAll("g.edge").forEach((g) => {
    const [source, target] = g.querySelector("title").textContent.split("->");
    g.dataset.source = source;
    g.dataset.target = target;
    const path = g.querySelector("path");
    if (path) {
      const hit = path.cloneNode();
      hit.setAttribute("class", "hit");
      g.insertBefore(hit, path);
    }
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
  const shown = new Set(ids);
  svg.querySelectorAll("g.edge").forEach((g) => {
    const related = single
      ? ids.has(g.dataset.source) || ids.has(g.dataset.target)
      : ids.has(g.dataset.source) && ids.has(g.dataset.target);
    g.classList.toggle("related", related);
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

function pin(ids, label, strict = true, root = null) {
  state.sticky = { ids, label, strict, root };
  focusOn(ids, state.sticky);
  notes();
}

function clearFocus() {
  state.sticky = null;
  unfocus();
  notes();
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

async function drawTree() {
  if (!state.options.tree || !state.root) return;
  const root = state.root;
  const pkg = state.package;
  const key = `${placeKey(pkg, root)}|${state.options.tests}`;
  if (!state.trees.has(key)) {
    const q = new URLSearchParams({ root });
    if (pkg) q.set("package", pkg);
    if (state.options.tests) q.set("hide_tests", "true");
    try {
      state.trees.set(key, await api(`/api/tree?${q}`));
    } catch (error) {
      $("tree-head").innerHTML = "";
      $("tree-body").innerHTML = `<p class="hint">${esc(error.message)}</p>`;
      return;
    }
  }
  if (root !== state.root || pkg !== state.package) return;
  renderTree(state.trees.get(key));
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
      <dt>Zone</dt><dd>${zone}</dd>`;
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
  const all = [...report.problems.filter((p) => p.fails), ...report.problems.filter((p) => !p.fails)];
  const failing = all.filter((p) => p.fails).length;
  const card = (p, i) => {
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
  const unused = report.unused_allowances.length
    ? `<h3>Allowed but unused</h3><ul class="links">${report.unused_allowances.map((u) => `<li>${esc(u.from)} → ${esc(u.to)}</li>`).join("")}</ul>` : "";
  const warnings = report.warnings.length
    ? `<h3>Warnings</h3><ul class="links">${report.warnings.map((w) => `<li>${esc(w.message)}</li>`).join("")}</ul>` : "";
  const body = openPanel(
    `<h2>${failing ? plural(failing, "failing problem") : "Rules pass"}</h2><div class="sub">${esc(state.project.rules)} · ${plural(report.components.length, "component")}</div>`,
    (all.length ? all.map(card).join("") : '<p class="hint">No problems.</p>') + unused + warnings,
  );
  body.querySelectorAll(".imports[data-p]").forEach((ul) => {
    const imports = all[Number(ul.dataset.p)].imports;
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
      `<h2>Metrics</h2><div class="sub">${esc(state.root)} · I = instability, A = abstractness, D = |A + I − 1|</div>`,
      `<table class="metrics"><thead><tr>${columns.map(([k, label]) => `<th data-k="${k}">${label}${k === sortKey ? (descending ? " ▾" : " ▴") : ""}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`,
    );
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
  button.hidden = !p.rules;
  button.classList.toggle("bad", p.failing > 0 || !!p.rules_error);
  button.textContent = p.rules_error ? "Rules ⚠" : p.failing ? `Rules: ${p.failing} failing` : "Rules ✓";
  button.title = p.rules_error || `archview check against ${p.rules}`;
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
  option("opt-zones", "zones", false);
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
    };
    if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
  });
}

async function start() {
  loadOptions();
  applyOptions();
  bind();
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
