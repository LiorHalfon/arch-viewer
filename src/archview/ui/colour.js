// What a box's colour means: by role in this view, by instability, or by zone.
// Each scheme sorts a box into one class; a class has a name, a note and a fill token.

export const SCHEMES = ["role", "instability", "zone", "none"];

const bins = ["0 to 0.2", "0.2 to 0.4", "0.4 to 0.6", "0.6 to 0.8", "0.8 to 1"];
const binNotes = ["stable, others lean on it", "", "", "", "unstable, leans on others"];
const NO_DEPS = { key: "isolated", name: "no dependencies", note: "", token: "--isolated", focus: "boxes with no dependencies" };

export const CLASSES = {
  role: [
    { key: "entry", name: "entry point", note: "nothing here imports it", token: "--role-entry", focus: "entry points" },
    { key: "between", name: "in between", note: "imports and is imported", token: "--role-between", focus: "boxes in between" },
    { key: "foundation", name: "foundation", note: "imports nothing here", token: "--role-foundation", focus: "foundations" },
    { key: "alone", name: "on its own", note: "no lines either way", token: "--isolated", focus: "boxes on their own" },
  ],
  instability: [
    ...bins.map((name, i) => ({ key: `i${i}`, name, note: binNotes[i], token: `--seq-${i + 1}`, focus: `instability ${name}` })),
    NO_DEPS,
  ],
  zone: [
    { key: "main_sequence", name: "main sequence", note: "balanced", token: "--pkg-fill", focus: "boxes on the main sequence" },
    { key: "pain", name: "zone of pain", note: "stable and concrete", token: "--pain", focus: "zone of pain" },
    { key: "useless", name: "zone of uselessness", note: "abstract and unstable", token: "--useless", focus: "zone of uselessness" },
    NO_DEPS,
  ],
};

// The light value of every token draw.js writes; an export uses these (app.css is the source).
export const LIGHT = {
  "--bg": "#f6f7f9", "--surface": "#ffffff", "--text": "#1d232b", "--muted": "#5f6b7a", "--accent": "#2f6fb3",
  "--pkg-fill": "#e3ecf6", "--pkg-stroke": "#7a93ad", "--mod-fill": "#ffffff", "--mod-stroke": "#9aa6b4",
  "--edge": "#6b7785", "--danger": "#c62828", "--violation": "#d9480f", "--abs-fill": "#dcefd9", "--abs-stroke": "#5f9a57",
  "--pain": "#fde2cf", "--useless": "#e9dcf7", "--in": "#8b3fd1",
  "--role-entry": "#2771cc", "--role-between": "#1baf7a", "--role-foundation": "#eda100", "--isolated": "#d9dee5",
  "--seq-1": "#b7d3f6", "--seq-2": "#86b6ef", "--seq-3": "#4b93ea", "--seq-4": "#256abf", "--seq-5": "#104281",
};

const external = (node) => node.kind === "external";

export function roles(view) {
  const inside = new Set(view.nodes.filter((n) => !external(n)).map((n) => n.id));
  const imports = new Set(), imported = new Set();
  for (const e of view.edges) {
    if (!inside.has(e.source) || !inside.has(e.target)) continue;
    imports.add(e.source);
    imported.add(e.target);
  }
  const role = (id) => (imports.has(id) ? (imported.has(id) ? "between" : "entry") : imported.has(id) ? "foundation" : "alone");
  return new Map([...inside].map((id) => [id, role(id)]));
}

const bin = (node) => (node.instability === null || node.instability === undefined ? "isolated" : `i${Math.min(4, Math.floor(node.instability * 5))}`);

export function classOf(view, scheme) {
  if (scheme === "role") return roles(view);
  const boxes = view.nodes.filter((n) => !external(n));
  if (scheme === "instability") return new Map(boxes.map((n) => [n.id, bin(n)]));
  if (scheme === "zone") return new Map(boxes.filter((n) => CLASSES.zone.some((c) => c.key === n.zone)).map((n) => [n.id, n.zone]));
  return new Map();
}

export function legendRows(view, scheme) {
  const counts = new Map();
  for (const key of classOf(view, scheme).values()) counts.set(key, (counts.get(key) || 0) + 1);
  return (CLASSES[scheme] || []).map((c) => ({ ...c, count: counts.get(c.key) || 0 }));
}

const plainFill = (node) => (node.abstract ? "--abs-fill" : node.kind === "package" ? "--pkg-fill" : "--mod-fill");

export function fillToken(node, scheme, key) {
  if (external(node)) return null;
  if (scheme === "none" || !key) return plainFill(node);
  if (key === "main_sequence") return node.kind === "package" ? "--pkg-fill" : "--mod-fill";
  return (CLASSES[scheme] || []).find((c) => c.key === key)?.token ?? plainFill(node);
}

// WCAG 2 contrast between two #rrggbb colours.
function luminance(hex) {
  const channel = (i) => {
    const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const INK = "#1d232b", WHITE = "#ffffff";
export const inkFor = (fill) => (contrast(INK, fill) >= contrast(WHITE, fill) ? INK : WHITE);

export function schemeFromOptions(saved) {
  if (SCHEMES.includes(saved.colour)) return saved.colour;
  return saved.zones === true ? "zone" : "role";
}
