#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["grimp>=3.16", "networkx>=3.4"]
# ///
"""Spike: build a single self-contained HTML drill-down viewer for a Python repo.

  uv run spike/viewer/view.py                     # analyse the current directory
  uv run spike/viewer/view.py ~/git/some-repo     # analyse another repo
  uv run spike/viewer/view.py ~/git/some-repo -p mypkg -o /tmp/out.html --no-open

Top-level packages are auto-detected (src/ layout, flat layout, or `src` as the
package itself); pass -p/--package to override. The graph is built once with
grimp, a view is derived for every package root, and the whole thing - views,
Graphviz DOT and Graphviz-WASM - is inlined into one HTML file that needs no
server and no network.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import webbrowser
from pathlib import Path

import tomllib

VIEWER = Path(__file__).resolve().parent
sys.path.insert(0, str(VIEWER.parent))  # the spike dir, for arch_graph

import grimp
from arch_graph import build_view, to_dot

VIZ = VIEWER / "vendor" / "viz-global.js"

SKIP_DIRS = {
    "alembic",
    "build",
    "dist",
    "doc",
    "docs",
    "example",
    "examples",
    "migrations",
    "node_modules",
    "scripts",
    "site-packages",
    "test",
    "testing",
    "tests",
    "venv",
}


def detect_packages(repo: Path) -> dict[str, Path]:
    """Map top-level package name -> the sys.path entry that makes it importable."""
    src = repo / "src"
    if (src / "__init__.py").is_file():  # 'src' is itself the package
        found, bases = {"src": repo}, [repo]
    else:
        found, bases = {}, ([src, repo] if src.is_dir() else [repo])

    def candidates():
        for base in bases:
            for child in sorted(base.iterdir()):
                if (
                    child.is_dir()
                    and child.name not in SKIP_DIRS
                    and not child.name.startswith((".", "_"))
                ):
                    yield base, child

    for base, child in candidates():
        if child.name not in found and (child / "__init__.py").is_file():
            found[child.name] = base
    if not found:  # namespace packages / no __init__.py
        for base, child in candidates():
            if child.name not in found and any(child.glob("*.py")):
                found[child.name] = base
    return found


def main_package(repo: Path) -> str | None:
    """The package named by pyproject.toml, if there is one."""
    try:
        name = tomllib.loads((repo / "pyproject.toml").read_text())["project"]["name"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return None
    return name.replace("-", "_")


def in_view_order(paths: dict[str, Path], repo: Path) -> list[str]:
    """The project's own package first, then biggest first - that is the one to look at."""
    main = main_package(repo)
    size = {
        name: len(list((base / name).rglob("*.py"))) for name, base in paths.items()
    }
    return sorted(paths, key=lambda n: (n != main, -size[n], n))


TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<title>archview spike - __TITLE__</title>
<style>
  :root { color-scheme: light dark; }
  body { margin:0; font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         display:grid; grid-template-rows:auto 1fr; height:100vh; }
  header { padding:10px 14px; border-bottom:1px solid #8883; display:flex; gap:12px;
           align-items:baseline; flex-wrap:wrap; }
  #roots button { margin-right:4px; }
  #roots button[aria-current="true"] { font-weight:700; }
  #crumbs a { cursor:pointer; text-decoration:underline; }
  #crumbs span.sep { opacity:.5; padding:0 4px; }
  #stats { opacity:.7; font-size:12px; margin-left:auto; }
  main { display:grid; grid-template-columns:1fr 0; overflow:hidden; transition:grid-template-columns .15s; }
  main.with-panel { grid-template-columns:1fr 380px; }
  #graph { overflow:auto; padding:16px; }
  #graph svg { max-width:none; }
  #graph g.node, #graph g.edge { cursor:pointer; }
  #graph g.node:hover polygon, #graph g.node:hover path { stroke-width:2.5; }
  #panel { border-left:1px solid #8883; overflow:auto; padding:14px; font-size:13px; }
  #panel h3 { margin:0 0 8px; font-size:14px; }
  #panel code { font:12px ui-monospace,Menlo,monospace; word-break:break-all; }
  #panel li { margin-bottom:10px; }
  .cycle { color:#c00; font-weight:600; }
  button { font:inherit; }
</style>
<header>
  <strong>archview spike</strong>
  <nav id="roots"></nav>
  <nav id="crumbs"></nav>
  <span id="stats"></span>
</header>
<main id="main">
  <div id="graph">rendering&hellip;</div>
  <aside id="panel" hidden></aside>
</main>
<script>__VIZ__</script>
<script>
const VIEWS = __VIEWS__;
const DOTS = __DOTS__;
const PACKAGES = __PACKAGES__;
let viz = null;

function roots(current) {
  const el = document.getElementById("roots");
  if (PACKAGES.length < 2) return;
  el.innerHTML = "";
  for (const p of PACKAGES) {
    const b = document.createElement("button");
    b.textContent = p;
    b.onclick = () => show(p);
    if (current === p || current.startsWith(p + ".")) b.setAttribute("aria-current", "true");
    el.append(b);
  }
}

function crumbs(root) {
  const parts = root.split(".");
  const el = document.getElementById("crumbs");
  el.innerHTML = "";
  parts.forEach((p, i) => {
    const id = parts.slice(0, i + 1).join(".");
    if (i) { const s = document.createElement("span"); s.className = "sep"; s.textContent = "/"; el.append(s); }
    if (VIEWS[id] && id !== root) {
      const a = document.createElement("a"); a.textContent = p; a.onclick = () => show(id); el.append(a);
    } else {
      const s = document.createElement("span"); s.textContent = p; el.append(s);
    }
  });
}

function show(root) {
  const v = VIEWS[root];
  if (!v) return;
  location.hash = root;
  roots(root);
  crumbs(root);
  document.getElementById("stats").innerHTML =
    `${v.nodes.length} children &middot; ${v.edges.length} edges &middot; ` +
    (v.cycles.length ? `<span class="cycle">${v.cycles.length} cycle(s)</span>` : "no cycles");
  const g = document.getElementById("graph");
  g.innerHTML = "";
  g.append(viz.renderSVGElement(DOTS[root]));
  wire(v);
  closePanel();
}

function wire(v) {
  document.querySelectorAll("#graph g.node").forEach(n => {
    const id = n.querySelector("title").textContent;
    n.onclick = () => VIEWS[id] ? show(id) : nodePanel(v, id);
    if (!VIEWS[id]) n.style.cursor = "default";
  });
  document.querySelectorAll("#graph g.edge").forEach(e => {
    const [from, to] = e.querySelector("title").textContent.split("->");
    e.onclick = () => edgePanel(v, from, to);
  });
}

function openPanel(html) {
  document.getElementById("main").classList.add("with-panel");
  const p = document.getElementById("panel");
  p.hidden = false; p.innerHTML = html;
}
function closePanel() {
  document.getElementById("main").classList.remove("with-panel");
  document.getElementById("panel").hidden = true;
}

function nodePanel(v, id) {
  const n = v.nodes.find(x => x.id === id);
  if (!n) return;
  openPanel(`<h3>${n.name}</h3>
    <p>${n.kind} &middot; ${n.module_count} module(s) &middot; layer ${n.layer}
      ${n.in_cycle ? '<span class="cycle">&middot; in cycle</span>' : ""}</p>
    <p>imported by ${n.fan_in}, imports ${n.fan_out}</p><p><code>${n.id}</code></p>`);
}

function edgePanel(v, from, to) {
  const e = v.edges.find(x => x.from === from && x.to === to);
  if (!e) return;
  const items = e.examples.map(x =>
    `<li><code>${x.importer}:${x.line}</code><br><code>${x.text.trim()}</code></li>`).join("");
  openPanel(`<h3>${from.split(".").pop()} &rarr; ${to.split(".").pop()}</h3>
    <p>${e.count} import(s)${e.in_cycle ? ' <span class="cycle">&middot; part of a cycle</span>' : ""}</p>
    <ul>${items}</ul>`);
}

addEventListener("hashchange", () => show(location.hash.slice(1) || PACKAGES[0]));
Viz.instance().then(v => { viz = v; show(location.hash.slice(1) || PACKAGES[0]); });
</script>
"""


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "repo", nargs="?", default=".", type=Path, help="repo to analyse (default: .)"
    )
    p.add_argument(
        "-p",
        "--package",
        action="append",
        default=[],
        help="top-level package (repeatable); default: auto-detect",
    )
    p.add_argument("-o", "--out", type=Path, help="output HTML (default: a temp file)")
    p.add_argument("--no-open", action="store_true", help="do not open a browser")
    args = p.parse_args()

    repo = args.repo.expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"{repo} is not a directory")

    if args.package:
        detected = detect_packages(repo)
        paths = {
            name: detected.get(name, repo / "src" if (repo / "src").is_dir() else repo)
            for name in args.package
        }
    else:
        paths = detect_packages(repo)
        if not paths:
            raise SystemExit(
                f"no importable package found in {repo}; pass -p/--package"
            )
    packages = in_view_order(paths, repo)

    for entry in dict.fromkeys(paths.values()):
        sys.path.insert(0, str(entry))
    print(f"analysing {', '.join(packages)} in {repo}", file=sys.stderr)

    graph = grimp.build_graph(*packages, cache_dir=None)
    views: dict[str, dict] = {}

    def walk(root: str) -> None:
        if root in views or not graph.find_children(root):
            return
        views[root] = build_view(graph, root)
        for child in sorted(graph.find_children(root)):
            walk(child)

    for package in packages:
        walk(package)
    if not views:
        raise SystemExit("nothing to show: no package has children")

    html = (
        TEMPLATE.replace("__VIZ__", VIZ.read_text())
        .replace("__VIEWS__", json.dumps(views))
        .replace("__DOTS__", json.dumps({r: to_dot(v) for r, v in views.items()}))
        .replace("__PACKAGES__", json.dumps([p for p in packages if p in views]))
        .replace("__TITLE__", repo.name)
    )

    out = args.out or Path(tempfile.gettempdir()) / f"archview-{repo.name}.html"
    out.write_text(html)
    print(f"{out}  ({len(views)} roots, {len(html) / 1e6:.1f} MB)")
    if not args.no_open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
