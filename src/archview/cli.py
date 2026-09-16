"""The command line: `archview graph | check | init`.

Exit codes: 0 success, 1 the check found failing problems, 2 the command could not
run (bad arguments, unreadable rules, no package).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from archview.model.cycles import describe_cycle
from archview.model.serialize import view_to_dict
from archview.model.view import View, build_view
from archview.project import ProjectError, open_project
from archview.render.check import report_to_dict, report_to_text
from archview.render.dot import to_dot
from archview.rules.check import check
from archview.rules.config import RULES_FILE, Config, ConfigError, find_config, load_config
from archview.rules.init import infer_rules

USAGE_ERROR = 2


class UsageError(Exception):
    pass


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
        lines += [f"  {describe_cycle(cycle)}" for cycle in view.cycles]
    return "\n".join(lines) + "\n"


def _graph(args: argparse.Namespace) -> int:
    asked = args.package or (args.root.split(".")[0] if args.root else None)
    project = open_project(args.path, asked, args.config)
    model = project.model
    root = args.root or project.package
    if root not in {n.id for n in model.nodes}:
        raise UsageError(f"{root} is not a module of {project.package}")

    view = build_view(model, root)
    if not view.nodes:
        raise UsageError(f"{root} has no children to show; drill into a package instead")

    if args.json:
        sys.stdout.write(json.dumps(view_to_dict(view), indent=2) + "\n")
    elif args.dot:
        sys.stdout.write(to_dot(view))
    else:
        sys.stdout.write(_as_text(view))
    return 0


def _wants_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _check(args: argparse.Namespace) -> int:
    project = open_project(args.path, args.package, args.config)
    if project.config_path is None:
        raise UsageError(
            f"no {RULES_FILE} (or [tool.archview] in pyproject.toml) in {project.repo}; "
            "run `archview init` first"
        )
    report = check(project.model, project.config)
    if args.format == "json":
        sys.stdout.write(json.dumps(report_to_dict(report), indent=2) + "\n")
    else:
        sys.stdout.write(report_to_text(report, color=_wants_color()))
    return 1 if report.failed else 0


def _init(args: argparse.Namespace) -> int:
    repo = args.path.expanduser().resolve()
    existing = args.config if args.config else find_config(repo)
    if existing and not existing.is_file():
        existing = None
    if existing and not (args.force or args.stdout):
        raise UsageError(f"{existing} already has rules; --force regenerates them")
    config = load_config(existing) if existing else Config()
    if args.exclude:
        config = replace(config, exclude=tuple(dict.fromkeys((*config.exclude, *args.exclude))))

    project = open_project(repo, args.package, config=config)
    text = infer_rules(project.model, config)
    if args.stdout:
        sys.stdout.write(text)
        return 0
    target = args.config or repo / RULES_FILE
    target.write_text(text)
    sys.stdout.write(f"wrote {target}\n")
    return 0


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", nargs="?", default=Path("."), type=Path, help="repo to analyse")
    parser.add_argument("--package", help="top-level package (default: the only one found)")
    parser.add_argument("--config", type=Path, help=f"rules file (default: ./{RULES_FILE})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archview", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    graph = commands.add_parser("graph", help="show the dependency view for one root")
    _common(graph)
    graph.add_argument("--root", help="package to view (default: the whole package)")
    output = graph.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="print the derived view as JSON")
    output.add_argument("--dot", action="store_true", help="print Graphviz DOT")
    graph.set_defaults(run=_graph)

    check_ = commands.add_parser("check", help="check the dependencies against the rules")
    _common(check_)
    check_.add_argument("--format", choices=["text", "json"], default="text")
    check_.set_defaults(run=_check)

    init = commands.add_parser("init", help="write rules inferred from the current imports")
    _common(init)
    init.add_argument("--force", action="store_true", help="regenerate existing rules")
    init.add_argument("--stdout", action="store_true", help="print instead of writing")
    init.add_argument(
        "--exclude", action="append", default=[], metavar="GLOB", help="file glob to leave out"
    )
    init.set_defaults(run=_init)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except (UsageError, ProjectError, ConfigError) as error:
        sys.stderr.write(f"archview: {error}\n")
        return USAGE_ERROR


if __name__ == "__main__":
    sys.exit(main())
