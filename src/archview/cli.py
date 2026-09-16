"""The command line: `archview graph` for now (M1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from archview.extract.discover import find_packages
from archview.extract.python import build_model
from archview.model.serialize import view_to_dict
from archview.model.view import View, build_view
from archview.render.dot import to_dot


def _fail(message: str) -> None:
    raise SystemExit(f"archview: {message}")


def _choose_package(packages: dict[str, Path], repo: Path, asked: str | None) -> str:
    if asked is not None:
        if asked not in packages:
            _fail(
                f"no package {asked!r} in {repo} (found: {', '.join(sorted(packages)) or 'none'})"
            )
        return asked
    if not packages:
        _fail(f"no Python package found in {repo}")
    if len(packages) > 1:
        _fail(
            f"several packages in {repo} ({', '.join(sorted(packages))}); "
            "pick one with --package or --root"
        )
    return next(iter(packages))


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _as_text(view: View) -> str:
    children = "1 child" if len(view.nodes) == 1 else f"{len(view.nodes)} children"
    lines = [
        f"{view.root}  {children}, {_plural(len(view.edges), 'edge')}, "
        f"{_plural(len(view.cycles), 'cycle')}",
        "",
    ]
    for node in view.nodes:
        mark = "  *cycle*" if node.in_cycle else ""
        lines.append(
            f"  L{node.layer}  {node.id} ({_plural(node.module_count, 'module')}, "
            f"in {node.fan_in}, out {node.fan_out}){mark}"
        )
    if view.cycles:
        lines += ["", "cycles:"]
        lines += [f"  {' -> '.join((*cycle, cycle[0]))}" for cycle in view.cycles]
    return "\n".join(lines) + "\n"


def _graph(args: argparse.Namespace) -> int:
    repo = args.path.expanduser().resolve()
    packages = find_packages(repo)
    asked = args.package or (args.root.split(".")[0] if args.root else None)
    package = _choose_package(packages, repo, asked)

    model = build_model(package, packages[package], relative_to=repo)
    root = args.root or package
    if root not in {n.id for n in model.nodes}:
        _fail(f"{root} is not a module of {package}")

    view = build_view(model, root)
    if not view.nodes:
        _fail(f"{root} has no children to show; drill into a package instead")

    if args.json:
        sys.stdout.write(json.dumps(view_to_dict(view), indent=2) + "\n")
    elif args.dot:
        sys.stdout.write(to_dot(view))
    else:
        sys.stdout.write(_as_text(view))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archview", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    graph = commands.add_parser("graph", help="show the dependency view for one root")
    graph.add_argument("path", nargs="?", default=Path("."), type=Path, help="repo to analyse")
    graph.add_argument("--package", help="top-level package (default: the only one found)")
    graph.add_argument("--root", help="package to view (default: the whole package)")
    output = graph.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="print the derived view as JSON")
    output.add_argument("--dot", action="store_true", help="print Graphviz DOT")
    graph.set_defaults(run=_graph)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
