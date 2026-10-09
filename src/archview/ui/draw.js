// Builds the diagram's SVG from a view payload and a Graphviz layout (layout.js).
// The markup keeps the DOM contract the rest of the viewer relies on: one
// `g.node[data-id]` per box and one `g.edge[data-source][data-target]` per edge.

import { edgeKey } from "./layout.js";

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const n = (v) => Number(v.toFixed(2));
const pt = ([x, y]) => `${n(x)},${n(y)}`;
const classes = (...names) => names.filter(Boolean).join(" ");

export function edgeGeometry(route, width) {
  const p = route.points;
  let d = p.length ? `M${pt(p[0])}` : "";
  for (let i = 1; i + 2 < p.length; i += 3) d += `C${pt(p[i])} ${pt(p[i + 1])} ${pt(p[i + 2])}`;
  let arrow = "";
  if (route.tip && p.length) {
    const base = p[p.length - 1];
    const dx = route.tip[0] - base[0], dy = route.tip[1] - base[1];
    const len = Math.hypot(dx, dy) || 1;
    const half = 3.4 + width * 0.55;
    const [px, py] = [(-dy / len) * half, (dx / len) * half];
    arrow = [route.tip, [base[0] + px, base[1] + py], [base[0] - px, base[1] - py]].map(pt).join(" ");
  }
  return { d, arrow, label: route.label };
}

function drawEdge(edge, route) {
  const cls = classes("edge", edge.in_cycle && "cycle", edge.violation && "violation", !edge.violation && edge.type_checking && "typing", edge.abstract && "abstract");
  const g = edgeGeometry(route, 1);
  const label = g.label ? `<text class="count" x="${n(g.label[0])}" y="${n(g.label[1])}" dy=".35em" text-anchor="middle">${edge.count}</text>` : "";
  return `<g class="${cls}" data-source="${esc(edge.source)}" data-target="${esc(edge.target)}">`
    + `<title>${esc(edge.source)}->${esc(edge.target)}</title>`
    + `<path class="hit" d="${g.d}"/><path class="line" d="${g.d}"/>`
    + (g.arrow ? `<polygon class="arrow" points="${g.arrow}"/>` : "")
    + `${label}</g>`;
}

// Name and second line as render/dot.py's _label: packages at the top of the view
// show their module count, everything else its name only.
function labelLines(node) {
  if (node.kind !== "package" || node.parent !== null) return [node.name];
  const modules = node.module_count === 1 ? "1 module" : `${node.module_count} modules`;
  return [`${node.name}${node.tangled ? " ⟲" : ""}`, `(${modules})`];
}

function shape(node, x0, y0, w, h) {
  const rect = (cls, x, y, width, height, r) => `<rect class="${cls}" x="${n(x)}" y="${n(y)}" width="${n(width)}" height="${n(height)}" rx="${r}"/>`;
  if (node.kind !== "package") return rect("shape", x0, y0, w, h, 6);
  const tab = (cy) => rect("shape tab", x0 - 4, cy - 2.5, 8, 5, 1);
  return rect("shape", x0, y0, w, h, 2) + tab(y0 + h / 4) + tab(y0 + (3 * h) / 4);
}

function drawNode(node, box, at) {
  const { w, h } = box;
  const x0 = at.x - w / 2, y0 = at.y - h / 2;
  const cls = classes("node", node.kind, node.in_cycle && "cycle", node.tangled && "tangled", node.abstract && "abstract");
  const [name, sub] = labelLines(node);
  const text = (c, y, value) => `<text class="${c}" x="${n(at.x)}" y="${n(y)}" text-anchor="middle">${esc(value)}</text>`;
  const words = sub ? text("name", at.y - 3.5, name) + text("sub", at.y + 13.3, sub) : text("name", at.y + 4.9, name);
  return `<g class="${cls}" data-id="${esc(node.id)}"><title>${esc(node.id)}</title>`
    + `<rect class="ring" x="${n(x0 - 4)}" y="${n(y0 - 4)}" width="${n(w + 8)}" height="${n(h + 8)}" rx="8"/>`
    + `${shape(node, x0, y0, w, h)}${words}</g>`;
}

function drawCluster(c) {
  return `<g class="cluster"><rect x="${n(c.x)}" y="${n(c.y)}" width="${n(c.w)}" height="${n(c.h)}" rx="8"/></g>`;
}

export function drawSvg(view, layout, opts = {}) {
  const positions = opts.positions || {};
  const routes = opts.routes || layout.routes;
  const clusters = opts.clusters || layout.clusters;
  const box = opts.box || { x: 0, y: 0, w: layout.w, h: layout.h };
  const parts = clusters.map(drawCluster);
  for (const e of view.edges) {
    const route = routes[edgeKey(e.source, e.target)];
    if (route) parts.push(drawEdge(e, route));
  }
  for (const node of view.nodes) {
    const size = layout.nodes[node.id];
    if (size) parts.push(drawNode(node, size, positions[node.id] || size));
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${n(box.x)} ${n(box.y)} ${n(box.w)} ${n(box.h)}">${parts.join("")}</svg>`;
}
