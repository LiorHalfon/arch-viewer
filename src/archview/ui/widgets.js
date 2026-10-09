// The viewer's DOM widgets that sit on top of the diagram.

import { chartSvg } from "./chart.js";
import { legendRows } from "./colour.js";
import { rank } from "./find.js";

export const ZONE_NAMES = { main_sequence: "main sequence", pain: "zone of pain", useless: "zone of uselessness", isolated: "no dependencies", external: "third-party" };

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;
const sum = (edges) => edges.reduce((total, e) => total + e.count, 0);

// ---------- hover card ----------

let card = null;

function importsRow(label, cls, edges) {
  return `<div class="row"><span class="${cls}">${label}</span><span>${plural(edges.length, "box", "boxes")} · ${plural(sum(edges), "import")}</span></div>`;
}

function bar(label, value) {
  const shown = value === null || value === undefined ? "–" : Number(value).toFixed(2);
  const width = Math.round(Math.max(0, Math.min(1, value || 0)) * 100);
  return `<span class="k">${label}</span><span class="bar"><i style="width:${width}%"></i></span><span>${shown}</span>`;
}

function cardHtml(node, view, drag) {
  const outs = view.edges.filter((e) => e.source === node.id);
  const ins = view.edges.filter((e) => e.target === node.id);
  const rows = importsRow("imports", "out", outs) + importsRow("imported by", "in", ins);
  if (node.kind === "external") {
    return `<div class="t">${esc(node.name)}</div><div class="k">third-party package</div>${rows}<div class="tip">click for details</div>`;
  }
  const kind = node.kind === "package" ? `package, ${plural(node.module_count, "module")}` : "module";
  const abstract = node.abstract ? ' <span class="k abs">abstract</span>' : "";
  const hint = [node.has_children ? "click to open" : "click for source", drag && "drag to move", "shift-click for details"].filter(Boolean).join(" · ");
  return `<div class="t">${esc(node.name)}${abstract}</div>
    <div class="k">${kind} · layer ${node.layer}</div>
    ${rows}
    <div class="bars">${bar("instability", node.instability)}${bar("abstractness", node.abstractness)}${bar("distance", node.distance)}</div>
    <div><span class="zone zone-${esc(node.zone)}">${esc(ZONE_NAMES[node.zone] || node.zone)}</span></div>
    <div class="tip">${hint}</div>`;
}

// Beside the box: on its right, or on its left when the card would leave the host.
export function showCard(host, node, view, anchor, { drag = false } = {}) {
  if (!card || card.parentElement !== host) {
    card?.remove();
    card = document.createElement("div");
    card.className = "hovercard";
    card.setAttribute("role", "tooltip");
    host.append(card);
  }
  card.innerHTML = cardHtml(node, view, drag);
  card.hidden = false;
  const box = host.getBoundingClientRect();
  const { offsetWidth: w, offsetHeight: h } = card;
  let left = anchor.right - box.left + 10;
  if (left + w > box.width - 8) left = anchor.left - box.left - w - 10;
  left = Math.max(8, Math.min(left, box.width - w - 8));
  const top = Math.max(8, Math.min(anchor.top - box.top, box.height - h - 8));
  card.style.left = `${left}px`;
  card.style.top = `${top}px`;
}

export function hideCard() {
  if (card) card.hidden = true;
}

// ---------- legend ----------

const SCHEME_LABELS = { role: "Role", instability: "Instability", zone: "Zone", none: "None" };
const EXPLAIN = { instability: "What is instability?", zone: "What are the zones?" };

const LINES = `<details class="lines"><summary>Lines</summary>
  <div><span class="ln"></span>imports (count)</div>
  <div><span class="ln ln-thick"></span>thicker: more imports</div>
  <div><span class="ln ln-abs"></span>to an abstraction</div>
  <div><span class="ln ln-typing"></span>type checking only</div>
  <div><span class="ln ln-cycle"></span>in a cycle</div>
  <div><span class="ln ln-violation"></span>breaks a rule</div>
</details>`;

const PLAIN_BOXES = `<div class="keys">
  <div><span class="sw sw-pkg"></span>package</div>
  <div><span class="sw sw-mod"></span>module</div>
  <div><span class="sw sw-abs"></span>abstract</div>
  <div><span class="sw sw-ext"></span>third-party</div>
</div>`;

function classRows(view, scheme, picked) {
  const rows = legendRows(view, scheme).map((r) => `<button type="button" class="item${r.count ? "" : " zero"}" data-key="${esc(r.key)}" aria-pressed="${r.key === picked}">`
    + `<span class="sw" style="background:var(${r.token})"></span>`
    + `<span class="nm">${esc(r.name)}${r.note ? `<small>${esc(r.note)}</small>` : ""}</span>`
    + `<span class="ct">${r.count}</span></button>`).join("");
  const extra = [
    view.nodes.some((n) => n.kind === "external") && '<div><span class="sw sw-ext"></span>third-party</div>',
    view.nodes.some((n) => n.abstract) && '<div><i>name</i>&nbsp;abstract</div>',
  ].filter(Boolean).join("");
  return `<div class="items">${rows}</div>${extra ? `<div class="keys">${extra}</div>` : ""}<div class="hint">Click a row to pick out that group.</div>`;
}

export function legendHtml(view, scheme, { picked = null, explain = false } = {}) {
  const buttons = Object.entries(SCHEME_LABELS)
    .map(([key, label]) => `<button type="button" data-scheme="${key}" aria-pressed="${key === scheme}">${label}</button>`).join("");
  const body = scheme === "none" ? PLAIN_BOXES : classRows(view, scheme, picked);
  const about = explain && EXPLAIN[scheme] ? `<button type="button" class="about">${EXPLAIN[scheme]}</button>` : "";
  return `<div class="lh">Colour by</div><div class="seg" role="group" aria-label="Colour by">${buttons}</div>${body}${about}${LINES}`;
}

// ---------- quick find ----------

function marked(name, query) {
  const i = name.toLowerCase().indexOf(query.trim().toLowerCase());
  if (!query.trim() || i < 0) return esc(name);
  const end = i + query.trim().length;
  return `${esc(name.slice(0, i))}<b>${esc(name.slice(i, end))}</b>${esc(name.slice(end))}`;
}

// A search box floating over the diagram: type, move with the arrow keys, Enter or
// click to pick, Esc to close. `load` gives the entries (find.js) the first time.
export function createFinder(host, { load, onPick }) {
  const box = document.createElement("div");
  box.className = "finder";
  box.id = "finder";
  box.hidden = true;
  box.innerHTML = `<div class="in"><span aria-hidden="true">⌕</span><input type="text" autocomplete="off" spellcheck="false" aria-label="Find a package or module" placeholder="Find a package or module"><kbd>esc</kbd></div><ul role="listbox" aria-label="Matches"></ul>`;
  host.append(box);
  const input = box.querySelector("input");
  const list = box.querySelector("ul");
  let entries = [], results = [], selected = 0, failed = false;

  const render = () => {
    if (failed) { list.innerHTML = '<li class="empty">Could not read the package tree.</li>'; return; }
    list.innerHTML = results.length
      ? results.map((r, i) => `<li role="option" data-i="${i}" aria-selected="${i === selected}">
          <span class="n">${marked(r.name, input.value)}</span>
          <span class="p">${esc(r.parent ?? (r.member || ""))}</span>
          <span class="k">${r.kind === "package" ? `package, ${plural(r.items, "item")}` : "module"}</span></li>`).join("")
      : `<li class="empty">${input.value.trim() ? "No package or module matches." : "Type part of a name."}</li>`;
  };
  const search = () => { results = rank(entries, input.value); selected = Math.min(selected, Math.max(0, results.length - 1)); render(); };
  const close = () => { box.hidden = true; };
  const pick = (i) => { const entry = results[i]; if (!entry) return; close(); onPick(entry); };

  input.oninput = () => { selected = 0; search(); };
  input.onkeydown = (e) => {
    const keys = {
      ArrowDown: () => { selected = Math.min(results.length - 1, selected + 1); render(); },
      ArrowUp: () => { selected = Math.max(0, selected - 1); render(); },
      Enter: () => pick(selected),
      Escape: close,
    };
    if (!keys[e.key]) return;
    e.preventDefault();
    e.stopPropagation();
    keys[e.key]();
  };
  list.onclick = (e) => { const li = e.target.closest("li[data-i]"); if (li) pick(Number(li.dataset.i)); };
  document.addEventListener("pointerdown", (e) => { if (!box.hidden && !box.contains(e.target) && !e.target.closest("#find")) close(); });

  const open = async () => {
    box.hidden = false;
    input.focus();
    input.select();
    try {
      entries = await load();
      failed = false;
    } catch {
      failed = true;
    }
    search();
  };
  return { open, close };
}

// ---------- metrics panel ----------

function metricsText(view, threshold) {
  const count = (zone) => view.nodes.filter((n) => n.zone === zone).length;
  return `<p>Each dot is a box in this view: ${plural(count("pain"), "box", "boxes")} in the zone of pain, ${count("useless")} in the zone of uselessness, ${count("main_sequence")} near the main sequence. These are Robert C. Martin's package metrics; <code>archview metrics</code> prints the same numbers.</p>
    <section><h3>Instability, I (across)</h3>
      <p>How much a box leans on others compared with how much others lean on it. I = Ce ÷ (Ca + Ce): Ce counts the modules outside the box that it imports, Ca the modules outside it that import it. Both are counted over the whole project, not just this view.</p>
      <ul><li><b>0</b>: other code imports it and it imports nothing. A change to it can break everything that depends on it.</li>
      <li><b>1</b>: it imports other code and nothing imports it. Nothing breaks when it changes.</li></ul></section>
    <section><h3>Abstractness, A (up)</h3>
      <p>The share of a box's modules that are abstract. A Python module counts when it defines a class that subclasses <code>Protocol</code> or <code>ABC</code>, uses <code>metaclass=ABCMeta</code>, or has an <code>@abstractmethod</code>. A TypeScript file counts when it has an <code>abstract class</code> or exports only types. One such class is enough.</p></section>
    <section><h3>Zones</h3>
      <p>Code that much else depends on should be abstract, so a change lands behind an interface. Code nothing depends on can be concrete. Healthy boxes sit near the dashed line, the main sequence. D = |A + I − 1| is the distance from it, and a box more than ${threshold} away is in a zone:</p>
      <ul><li><b>Zone of pain</b>, bottom left. Stable and concrete: much imports it and it offers no interface, so every change spreads. Fine for code that rarely changes, such as config or data models.</li>
      <li><b>Zone of uselessness</b>, top right. Abstract and unstable: interfaces that little or nothing uses.</li></ul></section>
    <p class="more">The longer version, with examples, is <code>docs/metrics.md</code> in the archview repository.</p>`;
}

export function renderMetricsPanel(body, view, threshold, { onHoverBox, onClickBox }) {
  const { svg, dots } = chartSvg(view, threshold);
  body.innerHTML = `<div class="explain">${svg}
    <div class="zk"><span><i class="sw-zone pain"></i>zone of pain</span><span><i class="sw-zone"></i>main sequence, within ${threshold}</span><span><i class="sw-zone useless"></i>zone of uselessness</span></div>
    ${metricsText(view, threshold)}</div>`;
  const chart = body.querySelector("svg");
  const groups = [...body.querySelectorAll(".dot")];
  const mark = (id) => {
    const on = id ? dots.find((d) => d.ids.includes(id)) : null;
    chart.classList.toggle("focus", !!on);
    for (const g of groups) {
      const lit = dots[Number(g.dataset.i)] === on;
      g.classList.toggle("on", lit);
      if (lit) g.parentNode.append(g);  // draw it and its label on top
    }
  };
  for (const g of groups) {
    const d = dots[Number(g.dataset.i)];
    g.onmouseenter = () => { mark(d.ids[0]); onHoverBox(d.ids[0]); };
    g.onmouseleave = () => { mark(null); onHoverBox(null); };
    g.onclick = () => d.ids.forEach(onClickBox);
  }
  return { mark };
}

export function renderLegend(el, view, scheme, { picked = null, onScheme, onPick, onExplain } = {}) {
  const open = el.querySelector("details.lines")?.open;
  el.innerHTML = legendHtml(view, scheme, { picked, explain: !!onExplain });
  if (open) el.querySelector("details.lines").open = true;
  el.querySelectorAll("[data-scheme]").forEach((b) => { b.onclick = () => onScheme(b.dataset.scheme); });
  const rows = legendRows(view, scheme);
  el.querySelectorAll("[data-key]").forEach((b) => { b.onclick = () => onPick(rows.find((r) => r.key === b.dataset.key)); });
  const about = el.querySelector(".about");
  if (about) about.onclick = () => onExplain();
}
