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
