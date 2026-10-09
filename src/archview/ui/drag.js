// Dragging boxes, and remembering where they were left for each view.
// Positions live in the browser's localStorage only: the viewer never writes into
// the repo it analyses.

export const DRAG_THRESHOLD = 4;
export const STORE_KEY = "archview.layout.v1";

// Past 4 px it is a drag; anything less is a click and keeps its meaning.
export const isDrag = (start, now) => Math.hypot(now.x - start.x, now.y - start.y) > DRAG_THRESHOLD;

// Everything that changes which boxes a view has: the project, the workspace member,
// the root, and the two filters.
export function layoutKey({ repo, project, package: pkg, root, externals, hideTests }) {
  return `${repo}|${project}|${pkg ?? ""}|${root}|${externals ? 1 : 0}|${hideTests ? 1 : 0}`;
}

function readAll(storage) {
  try {
    const all = JSON.parse(storage.getItem(STORE_KEY));
    return all && typeof all === "object" && !Array.isArray(all) ? all : {};
  } catch {
    return {};  // no storage, blocked storage, or not JSON
  }
}

const isPoint = (p) => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite);

// The boxes moved in this view that it still has.
export function loadMoved(storage, key, ids) {
  const saved = readAll(storage)[key];
  const moved = new Map();
  if (!saved || typeof saved !== "object") return moved;
  for (const [id, p] of Object.entries(saved)) if (ids.has(id) && isPoint(p)) moved.set(id, { x: p[0], y: p[1] });
  return moved;
}

const round = (v) => Math.round(v * 100) / 100;

export function saveMoved(storage, key, moved) {
  try {
    const all = readAll(storage);
    if (moved.size) all[key] = Object.fromEntries([...moved].map(([id, p]) => [id, [round(p.x), round(p.y)]]));
    else delete all[key];
    storage.setItem(STORE_KEY, JSON.stringify(all));
  } catch {
    // storage full, blocked or missing: dragging still works, nothing is kept
  }
}

// Pointer handling on the boxes. `onMove` and `onDrop` get the pointer's offset since
// it went down, in SVG units. The click that follows a drag is swallowed, so dropping
// a package does not open it.
export function enableDrag(svg, { toSvgPoint, onMove, onDrop, onCancel = () => {} }) {
  let drag = null;
  const offset = (e) => {
    const p = toSvgPoint(e);
    return { x: p.x - drag.origin.x, y: p.y - drag.origin.y };
  };
  const end = () => {
    svg.classList.remove("dragging");
    drag = null;
  };
  svg.addEventListener("pointerdown", (e) => {
    const g = e.target.closest("g.node");
    if (!g || e.button !== 0) return;
    drag = { id: g.dataset.id, g, start: { x: e.clientX, y: e.clientY }, origin: toSvgPoint(e), moving: false, pointer: e.pointerId };
  });
  svg.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.pointer) return;
    if (!drag.moving) {
      if (!isDrag(drag.start, { x: e.clientX, y: e.clientY })) return;
      drag.moving = true;
      svg.classList.add("dragging");
      try {
        drag.g.setPointerCapture(e.pointerId);
      } catch {
        // the pointer is already gone; the svg still gets its moves
      }
    }
    onMove(drag.id, offset(e));
  });
  svg.addEventListener("pointerup", (e) => {
    if (!drag || e.pointerId !== drag.pointer) return;
    if (drag.moving) {
      // The drop redraws the diagram: the click may reach the page, or the old svg it
      // left behind, so swallow it on both.
      const swallow = (click) => { click.stopPropagation(); click.preventDefault(); };
      for (const target of [window, svg]) {
        target.addEventListener("click", swallow, { capture: true, once: true });
        setTimeout(() => target.removeEventListener("click", swallow, { capture: true }), 0);
      }
      const { id } = drag, by = offset(e);
      end();
      onDrop(id, by);
      return;
    }
    end();
  });
  svg.addEventListener("pointercancel", () => {
    if (drag?.moving) onCancel(drag.id);
    end();
  });
}
