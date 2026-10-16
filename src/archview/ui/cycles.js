// The loops inside a tangle, for the cycles panel. A tangle (one of a view's
// `cycles`) is a strongly connected set of boxes; a loop is one way round it that
// visits no box twice. Seeing the loops one at a time shows which imports to cut.

const BUDGET = 200_000;  // search steps before a very dense tangle stops listing

// The loops among `members` along `edges` ({source, target}; edges leaving the
// tangle are ignored), shortest first, then by name, each starting at its first
// member by name and listed without the return to it. At most `limit` of them;
// `more` says there were others.
export function loopsIn(members, edges, limit = 30) {
  const names = [...members].sort();
  const index = new Map(names.map((name, i) => [name, i]));
  const next = names.map(() => []);
  for (const { source, target } of edges) {
    if (index.has(source) && index.has(target) && source !== target) next[index.get(source)].push(index.get(target));
  }
  next.forEach((targets) => targets.sort((a, b) => a - b));

  const loops = [];
  let steps = 0;
  const full = () => loops.length > limit || steps > BUDGET;
  // Paths of exactly `size` boxes from `start` through later names only, so each
  // loop is found once, from its first name.
  const walk = (start, path, onPath, size) => {
    for (const to of next[path.at(-1)]) {
      if (full()) return;
      steps += 1;
      if (to === start && path.length === size) loops.push(path.map((i) => names[i]));
      else if (to > start && !onPath.has(to) && path.length < size) {
        onPath.add(to);
        path.push(to);
        walk(start, path, onPath, size);
        path.pop();
        onPath.delete(to);
      }
    }
  };
  for (let size = 2; size <= names.length && !full(); size += 1) {
    for (let start = 0; start < names.length && !full(); start += 1) walk(start, [start], new Set([start]), size);
  }
  return { loops: loops.slice(0, limit), more: full() };
}
