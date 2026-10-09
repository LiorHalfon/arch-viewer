// The metrics panel's chart: every box of the view on Bob's instability /
// abstractness plane, the zones shaded, the main sequence dashed.

export const AREA = { left: 44, top: 12, width: 268, height: 232, bottom: 40, right: 18 };

const OFFSETS = [0, -12, 12, -24, 24, -36, -48];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const n = (v) => Number(v.toFixed(2));
const X = (i) => AREA.left + i * AREA.width;
const Y = (a) => AREA.top + (1 - a) * AREA.height;
const labelWidth = (text) => text.length * 6.2 + 2;

function groupDots(view) {
  const plotted = view.nodes.filter((b) => b.kind !== "external" && b.instability !== null && b.instability !== undefined);
  const byPoint = new Map();
  for (const b of plotted) {
    const key = `${b.instability},${b.abstractness}`;
    byPoint.set(key, [...(byPoint.get(key) || []), b]);
  }
  return [...byPoint.values()].map((group) => {
    const boxes = group.sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
    const [first] = boxes;
    return {
      ids: boxes.map((b) => b.id),
      names: boxes.map((b) => b.name),
      I: first.instability,
      A: first.abstractness,
      x: X(first.instability),
      y: Y(first.abstractness),
      text: boxes.length > 1 ? `${first.name} +${boxes.length - 1}` : first.name,
      label: null,
    };
  });
}

function fits(d, dots, placed, x0, w, y, area) {
  if (y < area.top + 9 || y > area.top + area.height + 4) return false;
  if (placed.some((p) => x0 < p.x1 && x0 + w > p.x0 && Math.abs(y - p.y) < 12)) return false;
  return !dots.some((o) => o !== d && Math.abs(o.x - (x0 + w / 2)) < w / 2 + 4 && Math.abs(o.y - (y - 4)) < 7);
}

// Beside the dot, nudged up or down past earlier labels; a label that fits
// nowhere stays null and the dot shows its name on hover only.
export function placeLabels(dots, area = AREA) {
  const right = area.left + area.width + area.right;
  const placed = [];
  for (const d of [...dots].sort((a, b) => a.y - b.y || a.x - b.x)) {
    const w = labelWidth(d.text);
    const sides = d.x > area.left + area.width * 0.62 ? ["end", "start"] : ["start", "end"];
    for (const anchor of sides) {
      const x0 = anchor === "start" ? d.x + 9 : d.x - 9 - w;
      if (x0 < 2 || x0 + w > right) continue;
      const dy = OFFSETS.find((o) => fits(d, dots, placed, x0, w, d.y + 4 + o, area));
      if (dy === undefined) continue;
      d.label = { x: anchor === "start" ? d.x + 9 : d.x - 9, y: d.y + 4 + dy, anchor, leader: dy !== 0 };
      placed.push({ x0, x1: x0 + w, y: d.y + 4 + dy });
      break;
    }
  }
  return dots;
}

function dotSvg(d, i) {
  const two = (v) => Number(v).toFixed(2);
  const left = d.x > AREA.left + AREA.width * 0.62;
  const leader = d.label?.leader ? `<line x1="${n(d.x)}" y1="${n(d.y)}" x2="${n(d.label.x + (d.label.anchor === "start" ? -2 : 2))}" y2="${n(d.label.y - 4)}"/>` : "";
  const label = d.label ? `<text class="lab" x="${n(d.label.x)}" y="${n(d.label.y)}" text-anchor="${d.label.anchor}">${esc(d.text)}</text>` : "";
  return `<g class="dot" data-i="${i}"><circle class="hit" cx="${n(d.x)}" cy="${n(d.y)}" r="11"/>${leader}`
    + `<circle class="mark" cx="${n(d.x)}" cy="${n(d.y)}" r="${d.ids.length > 1 ? 6.5 : 5}"/>${label}`
    + `<text class="hov" x="${n(left ? d.x - 9 : d.x + 9)}" y="${n(d.y - 9)}" text-anchor="${left ? "end" : "start"}">${esc(d.names.join(", "))} · I ${two(d.I)}, A ${two(d.A)}</text></g>`;
}

export function chartSvg(view, threshold) {
  const dots = placeLabels(groupDots(view));
  const t = threshold;
  const poly = (pts) => pts.map(([i, a]) => `${n(X(i))},${n(Y(a))}`).join(" ");
  const { left, top, width, height, bottom, right } = AREA;
  const ticks = [0, 0.5, 1].map((v) => `<text class="ax" x="${n(X(v))}" y="${top + height + 15}" text-anchor="middle">${v}</text>`
    + `<text class="ax" x="${left - 7}" y="${n(Y(v) + 4)}" text-anchor="end">${v}</text>`).join("");
  const empty = dots.length ? "" : `<text class="empty" x="${left + width / 2}" y="${top + height / 2}" text-anchor="middle">No box in this view has an instability to plot.</text>`;
  const svg = `<svg class="metrics-chart" viewBox="0 0 ${left + width + right} ${top + height + bottom}" role="img" aria-label="Boxes in this view by instability and abstractness">`
    + `<polygon class="pain" points="${poly([[0, 0], [1 - t, 0], [0, 1 - t]])}"/>`
    + `<polygon class="useless" points="${poly([[1, 1], [t, 1], [1, t]])}"/>`
    + `<rect class="frame" x="${left}" y="${top}" width="${width}" height="${height}"/>`
    + `<line class="seq" x1="${X(0)}" y1="${Y(1)}" x2="${X(1)}" y2="${Y(0)}"/>${ticks}`
    + `<text class="axl" x="${left + width / 2}" y="${top + height + 32}" text-anchor="middle">instability, I →</text>`
    + `<text class="axl" transform="translate(13 ${top + height / 2}) rotate(-90)" text-anchor="middle">abstractness, A →</text>`
    + `${dots.map(dotSvg).join("")}${empty}</svg>`;
  return { svg, dots };
}
