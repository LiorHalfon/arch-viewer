// The viewer's DOM widgets that sit on top of the diagram.

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
