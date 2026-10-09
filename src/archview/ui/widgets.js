// The viewer's DOM widgets that sit on top of the diagram.

import { legendRows } from "./colour.js";

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
