// Graphviz lays out every view; this reads its JSON output into plain data the
// viewer draws from: box centres and sizes, cluster frames, and edge splines.
// Everything is in points, with y pointing down from the top-left of the drawing.

export const edgeKey = (source, target) => `${source}>${target}`;

const inches = (value) => Number.parseFloat(value) * 72;

function flipper(height) {
  return (text) => {
    const [x, y] = text.split(",").map(Number);
    return [x, height - y];
  };
}

function parseRoute(edge, point) {
  const route = { points: [], tip: null, label: edge.lp ? point(edge.lp) : null };
  for (const item of edge.pos.split(" ")) {
    if (item.startsWith("e,")) route.tip = point(item.slice(2));
    else if (!item.startsWith("s,")) route.points.push(point(item));
  }
  return route;
}

function membersBox(members, nodes) {
  const boxes = members.map((id) => nodes[id]);
  return {
    left: Math.min(...boxes.map((n) => n.x - n.w / 2)),
    top: Math.min(...boxes.map((n) => n.y - n.h / 2)),
    right: Math.max(...boxes.map((n) => n.x + n.w / 2)),
    bottom: Math.max(...boxes.map((n) => n.y + n.h / 2)),
  };
}

function parseCluster(object, names, nodes, height) {
  const [x1, y1, x2, y2] = object.bb.split(",").map(Number);
  const frame = { x: x1, y: height - y2, w: x2 - x1, h: y2 - y1 };
  const members = (object.nodes || []).map((gvid) => names[gvid]).filter((id) => id in nodes);
  const inside = members.length ? membersBox(members, nodes) : { left: frame.x, top: frame.y, right: frame.x + frame.w, bottom: frame.y + frame.h };
  const pad = { l: inside.left - frame.x, t: inside.top - frame.y, r: frame.x + frame.w - inside.right, b: frame.y + frame.h - inside.bottom };
  return { id: object.name, members, ...frame, pad };
}

export function parseLayout(json) {
  const [, , w, h] = json.bb.split(",").map(Number);
  const point = flipper(h);
  const objects = json.objects || [];
  const names = Object.fromEntries(objects.map((o) => [o._gvid, o.name]));
  const nodes = {};
  for (const o of objects) {
    if (!o.pos) continue;
    const [x, y] = point(o.pos);
    nodes[o.name] = { x, y, w: inches(o.width), h: inches(o.height) };
  }
  const clusters = objects
    .filter((o) => !o.pos && o.bb && o.name.startsWith("cluster"))
    .map((o) => parseCluster(o, names, nodes, h));
  const routes = {};
  for (const e of json.edges || []) routes[edgeKey(names[e.tail], names[e.head])] = parseRoute(e, point);
  return { w, h, nodes, clusters, routes };
}

export const layoutView = (viz, dot) => parseLayout(viz.renderJSON(dot));

// ---------- routing again after boxes move ----------

// Graphviz routes every line around the boxes in about 230 ms at 100 boxes and 300
// lines, and 4.9 s at 300 boxes (Node, viz 3.30.0). Past this many boxes a drop
// draws the moved box's lines straight instead.
export const REROUTE_LIMIT = 100;

const at = (layout, positions, id) => positions[id] || layout.nodes[id];
// In a DOT quoted string only the double quote is escaped; a backslash stays as it is.
const quote = (id) => `"${String(id).replace(/"/g, '\\"')}"`;

export function pinnedDot(layout, positions, edges) {
  const lines = ['digraph "pinned" {', '  splines=true; overlap=true; inputscale=72; esep="+4";', '  node [shape=box fixedsize=true label=""];'];
  for (const [id, box] of Object.entries(layout.nodes)) {
    const p = at(layout, positions, id);
    lines.push(`  ${quote(id)} [pos="${p.x},${layout.h - p.y}!" width=${box.w / 72} height=${box.h / 72}];`);
  }
  for (const e of edges) lines.push(`  ${quote(e.source)} -> ${quote(e.target)};`);
  lines.push("}");
  return lines.join("\n");
}

const shiftPoint = (dx, dy) => (p) => (p ? [p[0] + dx, p[1] + dy] : p);

// Halfway along the spline, 9 pt to the left of travel: where a count goes when neato
// routed the line (the pinned DOT has no edge labels, so it places none).
function labelAt(points) {
  const segments = (points.length - 1) / 3;
  if (segments < 1) return null;
  const s = segments / 2, i = Math.min(Math.floor(s), segments - 1), t = s - i;
  const [p0, p1, p2, p3] = points.slice(i * 3, i * 3 + 4);
  const u = 1 - t;
  const at = (k) => u ** 3 * p0[k] + 3 * u * u * t * p1[k] + 3 * u * t * t * p2[k] + t ** 3 * p3[k];
  const slope = (k) => 3 * (u * u * (p1[k] - p0[k]) + 2 * u * t * (p2[k] - p1[k]) + t * t * (p3[k] - p2[k]));
  const len = Math.hypot(slope(0), slope(1)) || 1;
  return [at(0) + (slope(1) / len) * 9, at(1) - (slope(0) / len) * 9];
}

// neato keeps the pinned boxes in place relative to each other but moves the whole
// drawing so its corner is at the origin; put it back by one box's offset.
export function rerouteLayout(viz, layout, positions, edges) {
  const result = viz.render(pinnedDot(layout, positions, edges), { engine: "neato", format: "json" });
  if (result.status !== "success") throw new Error(result.errors.map((e) => e.message).join("; "));
  const out = parseLayout(JSON.parse(result.output));
  const [first] = Object.keys(layout.nodes);
  if (!first) return out;
  const want = at(layout, positions, first);
  const shift = shiftPoint(want.x - out.nodes[first].x, want.y - out.nodes[first].y);
  for (const n of Object.values(out.nodes)) [n.x, n.y] = shift([n.x, n.y]);
  for (const r of Object.values(out.routes)) {
    r.points = r.points.map(shift);
    r.tip = shift(r.tip);
    r.label = r.label ? shift(r.label) : labelAt(r.points);
  }
  return out;
}

export const reroute = (viz, layout, positions, edges) => rerouteLayout(viz, layout, positions, edges).routes;

// From border to border, as one cubic with its handles on its ends; the tip stops 1 pt
// short of the target and the arrow is 10 pt long.
export function straightRoute(a, boxA, b, boxB) {
  const len = Math.hypot(b.x - a.x, b.y - a.y);
  const [ux, uy] = len ? [(b.x - a.x) / len, (b.y - a.y) / len] : [1, 0];
  const exit = (box) => Math.min(box.w / 2 / Math.max(Math.abs(ux), 1e-9), box.h / 2 / Math.max(Math.abs(uy), 1e-9)) + 1;
  const start = [a.x + ux * exit(boxA), a.y + uy * exit(boxA)];
  const tip = [b.x - ux * exit(boxB), b.y - uy * exit(boxB)];
  const base = [tip[0] - ux * 10, tip[1] - uy * 10];
  const label = [(start[0] + tip[0]) / 2 + uy * 9, (start[1] + tip[1]) / 2 - ux * 9];
  return { points: [start, start, base, base], tip, label };
}

export function routesAfterMove(viz, layout, positions, edges, previous, moved) {
  if (Object.keys(layout.nodes).length <= REROUTE_LIMIT) return reroute(viz, layout, positions, edges);
  const routes = { ...previous };
  for (const e of edges) {
    if (!moved.has(e.source) && !moved.has(e.target)) continue;
    const [a, b] = [at(layout, positions, e.source), at(layout, positions, e.target)];
    routes[edgeKey(e.source, e.target)] = straightRoute(a, layout.nodes[e.source], b, layout.nodes[e.target]);
  }
  return routes;
}

export function clusterFrames(layout, positions) {
  return layout.clusters.map((c) => {
    if (!c.members.length) return c;
    const boxes = c.members.map((id) => ({ ...layout.nodes[id], ...at(layout, positions, id) }));
    const inside = membersBox(c.members, Object.fromEntries(c.members.map((id, i) => [id, boxes[i]])));
    const x = inside.left - c.pad.l, y = inside.top - c.pad.t;
    return { ...c, x, y, w: inside.right + c.pad.r - x, h: inside.bottom + c.pad.b - y };
  });
}

// The drawing's extent: every box, line and frame, plus a margin.
export function bounds(layout, positions, routes, clusters, margin = 24) {
  const xs = [], ys = [];
  const add = (x, y) => { xs.push(x); ys.push(y); };
  for (const [id, box] of Object.entries(layout.nodes)) {
    const p = at(layout, positions, id);
    add(p.x - box.w / 2, p.y - box.h / 2);
    add(p.x + box.w / 2, p.y + box.h / 2);
  }
  for (const r of Object.values(routes)) for (const p of [...r.points, r.tip, r.label]) if (p) add(p[0], p[1]);
  for (const c of clusters) { add(c.x, c.y); add(c.x + c.w, c.y + c.h); }
  if (!xs.length) return { x: 0, y: 0, w: layout.w, h: layout.h };
  const [x0, y0] = [Math.min(...xs) - margin, Math.min(...ys) - margin];
  return { x: x0, y: y0, w: Math.max(...xs) + margin - x0, h: Math.max(...ys) + margin - y0 };
}
