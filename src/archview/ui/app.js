"use strict";

// archview viewer: one root at a time, drawn by Graphviz (viz-js), drill down by click.
// Every root keeps its own zoom and scroll position, so Back returns to where you were.

const $ = (id) => document.getElementById(id);
const state = {
  viz: null,
  project: null,
  root: null,
  view: null,
  views: new Map(),     // root -> view payload
  places: new Map(),    // root -> {zoom, left, top}
  zoom: 1,
  natural: { w: 0, h: 0 },
};

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const short = (id) => id.split(".").pop();
const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return response.json();
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.hidden = true; }, 2200);
}

// ---------- navigation ----------

function rootFromHash() {
  const raw = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  return raw || state.project.project;
}

function go(root) {
  const target = `#/${encodeURIComponent(root)}`;
  if (location.hash === target) show(root);
  else location.hash = target;
}

function rememberPlace() {
  if (!state.root) return;
  const stage = $("stage");
  state.places.set(state.root, { zoom: state.zoom, left: stage.scrollLeft, top: stage.scrollTop });
}

async function loadView(root) {
  if (!state.views.has(root)) {
    state.views.set(root, await api(`/api/view?root=${encodeURIComponent(root)}`));
  }
  return state.views.get(root);
}

async function show(root) {
  rememberPlace();
  let view;
  try {
    view = await loadView(root);
  } catch (error) {
    $("graph").innerHTML = `<p class="hint">${esc(error.message)}</p>`;
    return;
  }
  state.root = root;
  state.view = view;
  document.title = `${root} · archview`;
  crumbs(root);
  stats(view);
  cyclesFooter(view);
  closePanel();
  draw(view);
  const place = state.places.get(root);
  setZoom(place ? place.zoom : fitZoom(), false);
  const stage = $("stage");
  stage.scrollLeft = place ? place.left : 0;
  stage.scrollTop = place ? place.top : 0;
  $("up").disabled = !view.parent;
}

function crumbs(root) {
  const el = $("crumbs");
  el.innerHTML = "";
  const parts = root.split(".");
  parts.forEach((part, i) => {
    const id = parts.slice(0, i + 1).join(".");
    if (i) el.insertAdjacentHTML("beforeend", '<span class="sep">/</span>');
    if (id === root) {
      el.insertAdjacentHTML("beforeend", `<span class="here">${esc(part)}</span>`);
    } else {
      const a = document.createElement("a");
      a.textContent = part;
      a.href = `#/${encodeURIComponent(id)}`;
      el.append(a);
    }
  });
}

function stats(view) {
  const cycles = view.cycles.length
    ? `<span class="bad">${plural(view.cycles.length, "cycle")}</span>`
    : "no cycles";
  $("stats").innerHTML = `${plural(view.nodes.length, "box", "boxes")} · ${plural(view.edges.length, "dependency", "dependencies")} · ${cycles}`;
}

function cycleText(cycle) {
  const names = cycle.map(short);
  return names.length === 2 ? `${names[0]} → ${names[1]} → ${names[0]}` : `tangle of ${names.length}: ${names.join(", ")}`;
}

function cyclesFooter(view) {
  const el = $("cycles");
  el.hidden = view.cycles.length === 0;
  if (el.hidden) return;
  el.innerHTML = `<h2>Cycles at this level</h2><ul>${view.cycles
    .map((c, i) => `<li data-i="${i}" title="Highlight">${esc(cycleText(c))}</li>`).join("")}</ul>`;
  el.querySelectorAll("li").forEach((li) => {
    li.onclick = () => focusOn(new Set(view.cycles[Number(li.dataset.i)]), true);
  });
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

function wire(svg, view) {
  const byId = new Map(view.nodes.map((n) => [n.id, n]));
  svg.querySelectorAll("g.node").forEach((g) => {
    const id = g.querySelector("title").textContent;
    const node = byId.get(id);
    g.dataset.id = id;
    g.querySelector("title").textContent = tooltip(node);
    g.onclick = () => (node.has_children ? go(id) : openSource(id));
    g.onmouseenter = () => focusOn(new Set([id]));
    g.onmouseleave = () => unfocus();
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
    g.querySelector("title").textContent = `${short(source)} → ${short(target)}: ${plural(edge.count, "import")}`;
    g.onclick = () => openEdge(edge);
  });
}

function tooltip(node) {
  const lines = [node.id];
  if (node.kind === "package") lines.push(plural(node.module_count, "module"));
  lines.push(`imports ${node.fan_out} · imported ${node.fan_in} · layer ${node.layer}`);
  if (node.in_cycle) lines.push("part of a cycle at this level");
  if (node.tangled) lines.push("has a cycle inside");
  lines.push(node.has_children ? "click to open" : "click for source");
  return lines.join("\n");
}

function focusOn(ids, sticky = false) {
  const svg = $("graph").querySelector("svg");
  if (!svg) return;
  svg.classList.add("focusing");
  svg.querySelectorAll("g.node").forEach((g) => g.classList.toggle("related", ids.has(g.dataset.id)));
  const neighbours = new Set(ids);
  svg.querySelectorAll("g.edge").forEach((g) => {
    const single = ids.size === 1;
    const related = single
      ? ids.has(g.dataset.source) || ids.has(g.dataset.target)
      : ids.has(g.dataset.source) && ids.has(g.dataset.target);
    g.classList.toggle("related", related);
    if (related && single) { neighbours.add(g.dataset.source); neighbours.add(g.dataset.target); }
  });
  svg.querySelectorAll("g.node").forEach((g) => g.classList.toggle("related", neighbours.has(g.dataset.id)));
  if (sticky) state.sticky = ids;
}

function unfocus() {
  if (state.sticky) return focusOn(state.sticky, true);
  const svg = $("graph").querySelector("svg");
  if (svg) svg.classList.remove("focusing");
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
  const ratio = zoom / state.zoom;
  const cx = stage.scrollLeft + stage.clientWidth / 2;
  const cy = stage.scrollTop + stage.clientHeight / 2;
  state.zoom = Math.max(0.1, Math.min(4, zoom));
  svg.style.width = `${state.natural.w * state.zoom}px`;
  svg.style.height = `${state.natural.h * state.zoom}px`;
  if (keepCentre) {
    stage.scrollLeft = cx * ratio - stage.clientWidth / 2;
    stage.scrollTop = cy * ratio - stage.clientHeight / 2;
  }
}

// ---------- panel ----------

function openPanel(titleHtml, bodyHtml, code = false) {
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
  document.querySelectorAll("#graph .selected").forEach((g) => g.classList.remove("selected"));
}

function select(selector) {
  document.querySelectorAll("#graph .selected").forEach((g) => g.classList.remove("selected"));
  document.querySelectorAll(selector).forEach((g) => g.classList.add("selected"));
}

function importItems(imports, showTarget) {
  return imports.map((i, n) => `<li data-n="${n}">
      <div class="where">${esc(i.file)}:${i.line}</div>
      <div class="text">${esc(i.text.trim())}</div>
      ${showTarget ? `<div class="target">${esc(i.importer)} → ${esc(i.imported)}</div>` : ""}
    </li>`).join("");
}

function openEdge(edge) {
  select(`#graph g.edge[data-source="${CSS.escape(edge.source)}"][data-target="${CSS.escape(edge.target)}"]`);
  const cycle = edge.in_cycle ? ' <span class="badge">cycle</span>' : "";
  const body = openPanel(
    `<h2>${esc(short(edge.source))} → ${esc(short(edge.target))}${cycle}</h2>
     <div class="sub">${plural(edge.count, "import")}</div>`,
    `<ul class="imports">${importItems(edge.imports, true)}</ul>`,
  );
  body.querySelectorAll(".imports li").forEach((li) => {
    const imp = edge.imports[Number(li.dataset.n)];
    li.onclick = () => openSource(imp.importer, imp.line);
  });
}

async function openSource(module, line = null) {
  let source;
  try {
    source = await api(`/api/source?module=${encodeURIComponent(module)}`);
  } catch (error) {
    toast(error.message);
    return;
  }
  select(`#graph g.node[data-id="${CSS.escape(module)}"]`);
  const lines = source.text.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  const importLines = new Map();
  source.imports.forEach((i) => {
    if (!importLines.has(i.line)) importLines.set(i.line, []);
    importLines.get(i.line).push(i.imported);
  });
  const highlighted = window.hljs
    ? hljs.highlight(source.text, { language: "python", ignoreIllegals: true }).value
    : esc(source.text);
  const gutter = lines.map((_, i) => {
    const n = i + 1;
    const targets = importLines.get(n);
    return targets
      ? `<span class="imp" data-line="${n}" title="imports ${esc(targets.join(", "))} (click to open)">${n}</span>`
      : `<span data-line="${n}">${n}</span>`;
  }).join("");
  const marks = [...importLines.keys()].map((n) => `<div class="mark" style="top:calc(8px + ${n - 1} * var(--line))"></div>`).join("")
    + (line ? `<div class="mark target" style="top:calc(8px + ${line - 1} * var(--line))"></div>` : "");

  const body = openPanel(
    `<h2>${esc(short(module))}</h2><div class="sub">${esc(source.file)}${line ? `:${line}` : ""}</div>`,
    `<div class="source">${marks}<div class="gutter">${gutter}</div><pre><code class="hljs language-python">${highlighted}</code></pre></div>`,
    true,
  );
  body.querySelectorAll(".gutter span.imp").forEach((span) => {
    span.onclick = () => {
      const target = importLines.get(Number(span.dataset.line))[0];
      openSource(target);
    };
  });
  if (line) {
    const lineHeight = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--line")) || 18;
    body.scrollTop = Math.max(0, (line - 1) * lineHeight - body.clientHeight / 3);
  }
}

// ---------- actions ----------

const parentOf = (id) => (id.includes(".") ? id.slice(0, id.lastIndexOf(".")) : null);

async function reanalyze() {
  const button = $("reanalyze");
  button.disabled = true;
  try {
    state.project = await api("/api/reanalyze", { method: "POST" });
    state.views.clear();
    let root = state.root;
    while (root) {
      try { await loadView(root); break; } catch { root = parentOf(root); }
    }
    rememberPlace();    // the same root comes back where it was
    state.root = null;  // so show() does not save over it
    go(root || state.project.project);
    toast(`Reanalyzed: ${plural(state.project.modules, "module")}, ${plural(state.project.imports, "import")}`);
  } catch (error) {
    toast(`Reanalyze failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function bind() {
  $("home").onclick = (e) => { e.preventDefault(); go(state.project.project); };
  $("up").onclick = () => state.view && state.view.parent && go(state.view.parent);
  $("zoom-in").onclick = () => setZoom(state.zoom * 1.25);
  $("zoom-out").onclick = () => setZoom(state.zoom / 1.25);
  $("zoom-fit").onclick = () => setZoom(fitZoom());
  $("reanalyze").onclick = reanalyze;
  $("panel-close").onclick = closePanel;
  $("graph").onclick = (e) => {
    if (e.target.closest("g.node, g.edge")) return;
    state.sticky = null;
    unfocus();
  };
  addEventListener("hashchange", () => show(rootFromHash()));
  addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const keys = {
      Escape: closePanel,
      u: () => $("up").click(),
      "+": () => $("zoom-in").click(),
      "=": () => $("zoom-in").click(),
      "-": () => $("zoom-out").click(),
      "0": () => $("zoom-fit").click(),
      r: reanalyze,
    };
    if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
  });
}

async function start() {
  bind();
  try {
    [state.viz, state.project] = await Promise.all([Viz.instance(), api("/api/project")]);
  } catch (error) {
    $("graph").innerHTML = `<p class="hint">Could not start: ${esc(error.message)}</p>`;
    return;
  }
  show(rootFromHash());
}

start();
