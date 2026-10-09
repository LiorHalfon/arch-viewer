// Builds the diagram's SVG from a view payload and a Graphviz layout (layout.js).
// The markup keeps the DOM contract the rest of the viewer relies on: one
// `g.node[data-id]` per box and one `g.edge[data-source][data-target]` per edge.

import { classOf, fillToken, inkFor, legendRows, LIGHT } from "./colour.js";
import { edgeKey } from "./layout.js";

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const n = (v) => Number(v.toFixed(2));
const pt = ([x, y]) => `${n(x)},${n(y)}`;
const classes = (...names) => names.filter(Boolean).join(" ");

// Width in pixels at zoom 1: 1 for one import, about 4.6 for 94, never above 6.
// Cycle and rule-break lines stay at least 2 wide, as they always were.
export function edgeWidth(count, { cycle = false, violation = false } = {}) {
  const width = Math.min(6, 1 + Math.log2(Math.max(1, count)) / 1.8);
  return cycle || violation ? Math.max(2, width) : width;
}

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

// On screen app.css styles the drawing; an export writes the same light colours into
// each element, so the file needs no stylesheet.
const P = LIGHT;

function edgePaint(edge, exporting) {
  if (!exporting) return { line: "", arrow: "", count: "" };
  const colour = edge.in_cycle ? P["--danger"] : edge.violation ? P["--violation"] : P["--edge"];
  const dash = edge.violation ? ' stroke-dasharray="6 4"' : edge.type_checking ? ' stroke-dasharray="2 3"' : "";
  const countFill = edge.in_cycle ? P["--danger"] : edge.violation ? P["--violation"] : P["--muted"];
  return {
    line: ` fill="none" stroke="${colour}"${dash}`,
    arrow: ` fill="${edge.abstract ? P["--surface"] : colour}" stroke="${colour}" stroke-width="1"`,
    count: ` fill="${countFill}" font-size="10"${edge.violation ? ' font-weight="600"' : ""} stroke="${P["--bg"]}" stroke-width="3" stroke-linejoin="round" paint-order="stroke"`,
  };
}

function drawEdge(edge, route, weighted, exporting) {
  const cls = classes("edge", edge.in_cycle && "cycle", edge.violation && "violation", !edge.violation && edge.type_checking && "typing", edge.abstract && "abstract");
  const width = weighted ? edgeWidth(edge.count, { cycle: edge.in_cycle, violation: edge.violation }) : 1;
  const g = edgeGeometry(route, width);
  const look = edgePaint(edge, exporting);
  const stroke = weighted || exporting ? ` stroke-width="${width.toFixed(2)}"` : "";
  const label = g.label ? `<text class="count" x="${n(g.label[0])}" y="${n(g.label[1])}" dy=".35em" text-anchor="middle"${look.count}>${edge.count}</text>` : "";
  return `<g class="${cls}" data-source="${esc(edge.source)}" data-target="${esc(edge.target)}">`
    + `<title>${esc(edge.source)}->${esc(edge.target)}</title>`
    + (exporting ? "" : `<path class="hit" d="${g.d}"/>`)
    + `<path class="line" d="${g.d}"${stroke}${look.line}/>`
    + (g.arrow ? `<polygon class="arrow" points="${g.arrow}"${look.arrow}/>` : "")
    + `${label}</g>`;
}

// Name and second line as render/dot.py's _label: packages at the top of the view
// show their module count, everything else its name only.
function labelLines(node) {
  if (node.kind !== "package" || node.parent !== null) return [node.name];
  const modules = node.module_count === 1 ? "1 module" : `${node.module_count} modules`;
  return [`${node.name}${node.tangled ? " ⟲" : ""}`, `(${modules})`];
}

function shape(node, x0, y0, w, h, look) {
  const rect = (cls, x, y, width, height, r) => `<rect class="${cls}" x="${n(x)}" y="${n(y)}" width="${n(width)}" height="${n(height)}" rx="${r}"${look}/>`;
  if (node.kind !== "package") return rect("shape", x0, y0, w, h, 6);
  const tab = (cy) => rect("shape tab", x0 - 4, cy - 2.5, 8, 5, 1);
  return rect("shape", x0, y0, w, h, 2) + tab(y0 + h / 4) + tab(y0 + (3 * h) / 4);
}

// On screen: the scheme's fill and the label ink that reads on it, as inline styles
// over the stylesheet; under "none" the stylesheet's own fills apply. A red name
// (cycle) keeps its colour and gets a halo it can be read against on any fill.
function screenPaint(node, scheme, key, palette) {
  const token = scheme === "none" ? null : fillToken(node, scheme, key);
  if (!token) return { shape: "", name: "", sub: "" };
  const ink = inkFor(palette[token] || LIGHT[token]);
  const halo = inkFor(palette["--danger"] || LIGHT["--danger"]);
  return {
    shape: ` style="fill:var(${token})"`,
    name: node.in_cycle || node.tangled
      ? ` style="stroke:${halo};stroke-width:3px;stroke-linejoin:round;paint-order:stroke"`
      : ` style="fill:${ink}"`,
    sub: ` style="fill:${ink};fill-opacity:.75"`,
  };
}

// In an export: everything app.css would have set, in light colours.
function exportPaint(node, scheme, key) {
  const external = node.kind === "external";
  const token = fillToken(node, scheme, key);
  const fill = external ? "none" : P[token];
  const stroke = external ? P["--mod-stroke"] : node.abstract ? P["--abs-stroke"] : node.in_cycle ? P["--danger"] : node.kind === "package" ? P["--pkg-stroke"] : P["--mod-stroke"];
  const width = node.kind === "module" ? 2 : 1;
  const plain = scheme === "none" || external;
  const ink = plain ? P[external ? "--muted" : "--text"] : inkFor(fill);
  const red = node.in_cycle || node.tangled;
  const halo = red && !plain ? ` stroke="${inkFor(P["--danger"])}" stroke-width="3" stroke-linejoin="round" paint-order="stroke"` : "";
  return {
    shape: ` fill="${fill}" stroke="${stroke}" stroke-width="${width}"${external ? ' stroke-dasharray="4 3"' : ""}`,
    name: ` fill="${red ? P["--danger"] : ink}" font-size="14"${red ? ' font-weight="600"' : ""}${halo}`,
    sub: plain ? ` fill="${P["--muted"]}" font-size="14"` : ` fill="${ink}" fill-opacity=".75" font-size="14"`,
  };
}

function drawNode(node, box, at, look, exporting) {
  const { w, h } = box;
  const x0 = at.x - w / 2, y0 = at.y - h / 2;
  const zone = (node.zone === "pain" || node.zone === "useless") && `zone-${node.zone}`;
  const cls = classes("node", node.kind, node.in_cycle && "cycle", node.tangled && "tangled", node.abstract && "abstract", zone);
  const [name, sub] = labelLines(node);
  const italic = (c) => (c === "name" && node.abstract ? ' font-style="italic"' : "");
  const text = (c, y, value) => `<text class="${c}" x="${n(at.x)}" y="${n(y)}" text-anchor="middle"${italic(c)}${look[c]}>${esc(value)}</text>`;
  const words = sub ? text("name", at.y - 3.5, name) + text("sub", at.y + 13.3, sub) : text("name", at.y + 4.9, name);
  const ring = exporting ? "" : `<rect class="ring" x="${n(x0 - 4)}" y="${n(y0 - 4)}" width="${n(w + 8)}" height="${n(h + 8)}" rx="8"/>`;
  return `<g class="${cls}" data-id="${esc(node.id)}">${ring}${shape(node, x0, y0, w, h, look.shape)}${words}</g>`;
}

function drawCluster(c, exporting) {
  const look = exporting ? ` fill="none" stroke="${P["--pkg-stroke"]}"` : "";
  return `<g class="cluster"><rect x="${n(c.x)}" y="${n(c.y)}" width="${n(c.w)}" height="${n(c.h)}" rx="8"${look}/></g>`;
}

const LEGEND_TITLES = { role: "Colour: role in this view", instability: "Colour: instability", zone: "Colour: zone" };

// Below an exported drawing: one swatch and name per class that has boxes.
function exportLegend(view, scheme, box) {
  const rows = scheme === "none" ? [] : legendRows(view, scheme).filter((r) => r.count);
  if (!rows.length) return { markup: "", height: 0 };
  const x = box.x + 8, top = box.y + box.h + 14;
  const items = rows.map((r, i) => {
    const y = top + 10 + i * 18;
    return `<rect x="${n(x)}" y="${n(y)}" width="14" height="10" rx="2" fill="${P[r.token]}" stroke="${P["--mod-stroke"]}"/>`
      + `<text x="${n(x + 22)}" y="${n(y + 9)}" fill="${P["--text"]}" font-size="12">${esc(r.name)}</text>`;
  });
  const title = `<text x="${n(x)}" y="${n(top)}" fill="${P["--muted"]}" font-size="12" font-weight="600">${LEGEND_TITLES[scheme]}</text>`;
  return { markup: `<g class="legend">${title}${items.join("")}</g>`, height: 28 + rows.length * 18 };
}

export function drawSvg(view, layout, opts = {}) {
  const positions = opts.positions || {};
  const routes = opts.routes || layout.routes;
  const clusters = opts.clusters || layout.clusters;
  const box = opts.box || { x: 0, y: 0, w: layout.w, h: layout.h };
  const exporting = opts.mode === "export";
  const parts = clusters.map((c) => drawCluster(c, exporting));
  for (const e of view.edges) {
    const route = routes[edgeKey(e.source, e.target)];
    if (route) parts.push(drawEdge(e, route, opts.weighted, exporting));
  }
  const scheme = opts.scheme || "none";
  const keys = classOf(view, scheme);
  const palette = opts.palette || LIGHT;
  for (const node of view.nodes) {
    const size = layout.nodes[node.id];
    if (!size) continue;
    const key = keys.get(node.id);
    const look = exporting ? exportPaint(node, scheme, key) : screenPaint(node, scheme, key, palette);
    parts.push(drawNode(node, size, positions[node.id] || size, look, exporting));
  }
  if (!exporting) return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${n(box.x)} ${n(box.y)} ${n(box.w)} ${n(box.h)}">${parts.join("")}</svg>`;
  const legend = exportLegend(view, scheme, box);
  const full = { ...box, w: Math.max(box.w, legend.height ? 220 : 0), h: box.h + legend.height };
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${n(full.x)} ${n(full.y)} ${n(full.w)} ${n(full.h)}" width="${n(full.w)}" height="${n(full.h)}" font-family="Helvetica, Arial, sans-serif">`
    + `<rect x="${n(full.x)}" y="${n(full.y)}" width="${n(full.w)}" height="${n(full.h)}" fill="#ffffff"/>${parts.join("")}${legend.markup}</svg>`;
}
