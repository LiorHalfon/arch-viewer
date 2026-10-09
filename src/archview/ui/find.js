// Quick find: every package and module of the project, ranked by how well its name
// matches what was typed. Parents come from the tree's nesting, so Python's "." and
// TypeScript's "/" ids need no separator logic.

export function flatten(tree, member = null) {
  const entries = [];
  const walk = (item, parent, depth) => {
    const children = item.children || [];
    entries.push({ id: item.id, name: item.name, kind: item.kind, parent, member, depth, items: item.kind === "package" ? children.length : 0 });
    for (const child of children) walk(child, item.id, depth + 1);
  };
  walk(tree, null, 0);
  return entries;
}

function score(entry, query) {
  const name = entry.name.toLowerCase();
  if (name.startsWith(query)) return 0;
  if (name.includes(query)) return 1;
  return entry.id.toLowerCase().includes(query) ? 2 : -1;
}

export function rank(entries, query, limit = 10) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return entries
    .map((entry) => ({ entry, score: score(entry, q) }))
    .filter((m) => m.score >= 0)
    .sort((a, b) => a.score - b.score
      || a.entry.depth - b.entry.depth
      || (a.entry.kind === "package" ? 0 : 1) - (b.entry.kind === "package" ? 0 : 1)
      || a.entry.id.localeCompare(b.entry.id))
    .slice(0, limit)
    .map((m) => m.entry);
}
