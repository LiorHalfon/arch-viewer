"""The command line: `archview [serve] [path] | graph | check | init | metrics`, and the
agent queries `why | deps | rdeps | cycles`.

`archview .` is short for `archview serve .`.

Exit codes: 0 success, 1 the check found failing problems (or `why` found no
dependency), 2 the command could not run (bad arguments, unreadable rules, no package).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import webbrowser
from dataclasses import asdict, replace
from pathlib import Path

from archview.model.cycles import describe_cycle
from archview.model.filter import without_tests
from archview.model.graph import Model
from archview.model.query import (
    UnknownName,
    all_cycles,
    dependencies,
    dependents,
    resolve,
    runtime_only,
    why,
)
from archview.model.serialize import view_to_dict
from archview.model.view import View, build_view
from archview.project import ProjectError, baseline_path, open_project, project_report
from archview.render.check import report_to_dict, report_to_text
from archview.render.dot import to_dot
from archview.render.mermaid import to_mermaid
from archview.render.query import (
    cycles_to_dict,
    cycles_to_text,
    neighbours_to_dict,
    neighbours_to_text,
    why_to_dict,
    why_to_text,
)
from archview.rules.baseline import baseline_of
from archview.rules.check import check
from archview.rules.config import RULES_FILE, Config, ConfigError, find_config, load_config
from archview.rules.init import infer_rules
from archview.rules.overlay import failing_imports, violating_edges

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
    model = without_tests(project.model) if args.hide_tests else project.model
    root = args.root or project.package
    if root not in {n.id for n in model.nodes}:
        raise UsageError(f"{root} is not a module of {project.package}")

    view = build_view(model, root, externals=args.externals)
    if not view.nodes:
        raise UsageError(f"{root} has no children to show; drill into a package instead")

    fmt = args.format or next(
        f for f in ("json", "dot", "mermaid", "text") if getattr(args, f, True)
    )
    violations = set()
    if project.config_path and fmt in ("dot", "mermaid"):
        violations = violating_edges(view, failing_imports(project_report(project)))
    if fmt == "json":
        sys.stdout.write(json.dumps(view_to_dict(view), indent=2) + "\n")
    elif fmt == "dot":
        sys.stdout.write(to_dot(view, violations=violations))
    elif fmt == "mermaid":
        sys.stdout.write(to_mermaid(view, violations))
    else:
        sys.stdout.write(_as_text(view))
    return 0


def _wants_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _check(args: argparse.Namespace) -> int:
    if args.stop_hook:
        return _stop_hook(args)
    project = _rules_project(args)
    if args.update_baseline:
        path = baseline_path(project)
        baseline = baseline_of(check(project.model, project.config))
        path.write_text(baseline.to_json())
        sys.stdout.write(f"wrote {path} ({len(baseline.entries)} known problems)\n")
        return 0
    report = project_report(project)
    if args.format == "json":
        sys.stdout.write(json.dumps(report_to_dict(report), indent=2) + "\n")
    else:
        sys.stdout.write(report_to_text(report, color=_wants_color()))
    return 1 if report.failed else 0


HOOK_BLOCKS = 2  # Claude Code's Stop hook: exit 2 sends stderr back to the agent


def _stop_hook(args: argparse.Namespace) -> int:
    """`check` as a Claude Code Stop hook that never traps the agent (ADR 0009)."""
    if _hook_input().get("stop_hook_active"):
        return 0
    try:
        report = project_report(_rules_project(args))
    except (UsageError, ProjectError, ConfigError) as error:
        sys.stderr.write(f"archview: {error} (not blocking the stop)\n")
        return 0
    if not report.failed:
        return 0
    sys.stderr.write(report_to_text(report))
    return HOOK_BLOCKS


def _hook_input() -> dict:
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _rules_project(args: argparse.Namespace):
    project = open_project(args.path, args.package, args.config)
    if project.config_path is None:
        raise UsageError(
            f"no {RULES_FILE} (or [tool.archview] in pyproject.toml) in {project.repo}; "
            "run `archview init` first"
        )
    return project


def _query_model(args: argparse.Namespace, names: list[str]) -> Model:
    """The model the queries run on; the package may be named by the first query name."""
    try:
        project = open_project(args.path, args.package, args.config)
    except ProjectError:
        if args.package or not names:
            raise
        try:
            project = open_project(args.path, names[0].split(".")[0], args.config)
        except ProjectError:
            raise ProjectError(
                f"several packages in {args.path}; pick one with --package"
            ) from None
    model = without_tests(project.model) if args.hide_tests else project.model
    return runtime_only(model) if args.runtime_only else model


def _write(args: argparse.Namespace, text: str, data: dict) -> None:
    sys.stdout.write(json.dumps(data, indent=2) + "\n" if args.format == "json" else text)


def _why(args: argparse.Namespace) -> int:
    model = _query_model(args, [args.source, args.target])
    try:
        answer = why(model, resolve(model, args.source), resolve(model, args.target))
    except ValueError as error:
        raise UsageError(str(error)) from None
    _write(args, why_to_text(answer), why_to_dict(answer))
    return 0 if answer.found else 1


def _neighbours(args: argparse.Namespace, outgoing: bool) -> int:
    model = _query_model(args, [args.name])
    try:
        name = resolve(model, args.name)
    except UnknownName as error:
        raise UsageError(str(error)) from None
    found = dependencies(model, name, args.externals) if outgoing else dependents(model, name)
    _write(
        args, neighbours_to_text(name, found, outgoing), neighbours_to_dict(name, found, outgoing)
    )
    return 0


def _cycles(args: argparse.Namespace) -> int:
    model = _query_model(args, [args.root] if args.root else [])
    try:
        root = resolve(model, args.root) if args.root else model.project
    except UnknownName as error:
        raise UsageError(str(error)) from None
    found = all_cycles(model, root)
    _write(args, cycles_to_text(found, root), cycles_to_dict(found, root))
    return 0


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


def _metrics(args: argparse.Namespace) -> int:
    project = open_project(args.path, args.package, args.config)
    report = check(project.model, project.config)
    if args.format == "json":
        data = {name: asdict(m) for name, m in sorted(report.metrics.items())}
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
        return 0
    rows = [("component", "Ca", "Ce", "I", "A", "D", "zone")]
    for name, m in sorted(report.metrics.items()):
        rows.append(
            (
                name,
                str(m.ca),
                str(m.ce),
                _num(m.instability),
                _num(m.abstractness),
                _num(m.distance),
                m.zone,
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for row in rows:
        sys.stdout.write("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)).rstrip())
        sys.stdout.write("\n")
    return 0


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _free_port(host: str, wanted: int) -> int:
    with socket.socket() as probe:
        try:
            probe.bind((host, wanted))
        except OSError:
            probe.bind((host, 0))
        return probe.getsockname()[1]


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from archview.server.app import create_app
    from archview.server.workspace import Workspace

    workspace = Workspace(args.path, args.package, args.config)
    if args.watch:
        workspace.watch()
    port = _free_port(args.host, args.port)
    url = f"http://{args.host}:{port}/"
    summary = workspace.summary()
    sys.stdout.write(
        f"archview: {summary['project']} ({summary['modules']} modules) at {url}  (Ctrl+C stops)\n"
    )
    sys.stdout.flush()
    if not args.no_open:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(workspace), host=args.host, port=port, log_level="warning")
    return 0


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", nargs="?", default=Path("."), type=Path, help="repo to analyse")
    parser.add_argument("--package", help="top-level package (default: the only one found)")
    parser.add_argument("--config", type=Path, help=f"rules file (default: ./{RULES_FILE})")


def _query_options(parser: argparse.ArgumentParser) -> None:
    _common(parser)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--hide-tests", action="store_true", help="leave test code out")
    parser.add_argument(
        "--runtime-only", action="store_true", help="leave out TYPE_CHECKING imports"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archview", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    graph = commands.add_parser("graph", help="show the dependency view for one root")
    _common(graph)
    graph.add_argument("--root", help="package to view (default: the whole package)")
    output = graph.add_mutually_exclusive_group()
    output.add_argument("--format", choices=["text", "json", "dot", "mermaid"])
    output.add_argument("--json", action="store_true", help="same as --format json")
    output.add_argument("--dot", action="store_true", help="same as --format dot")
    output.add_argument("--mermaid", action="store_true", help="same as --format mermaid")
    graph.add_argument("--externals", action="store_true", help="show third-party packages")
    graph.add_argument("--hide-tests", action="store_true", help="leave test code out")
    graph.set_defaults(run=_graph)

    check_ = commands.add_parser("check", help="check the dependencies against the rules")
    _common(check_)
    check_.add_argument("--format", choices=["text", "json"], default="text")
    check_.add_argument(
        "--update-baseline",
        action="store_true",
        help="record today's failing problems so only new ones fail",
    )
    check_.add_argument(
        "--stop-hook",
        action="store_true",
        help="run as a Claude Code Stop hook: failures go to stderr with exit 2",
    )
    check_.set_defaults(run=_check)

    why_ = commands.add_parser("why", help="why does A depend on B: the imports, or a chain")
    why_.add_argument("source", help="module or package (full, or relative to the package)")
    why_.add_argument("target", help="module, package or external package")
    _query_options(why_)
    why_.set_defaults(run=_why)

    for command, outgoing, help_ in (
        ("deps", True, "what a module or package imports"),
        ("rdeps", False, "what imports a module, package or external package"),
    ):
        sub = commands.add_parser(command, help=help_)
        sub.add_argument("name", help="module or package (full, or relative to the package)")
        _query_options(sub)
        if outgoing:
            sub.add_argument("--externals", action="store_true", help="list third-party packages")
        sub.set_defaults(run=lambda args, outgoing=outgoing: _neighbours(args, outgoing))

    cycles = commands.add_parser("cycles", help="the cycles at every level, with a path each")
    _query_options(cycles)
    cycles.add_argument("--root", help="only look under this package")
    cycles.set_defaults(run=_cycles)

    metrics = commands.add_parser("metrics", help="fan-in/out, instability, abstractness, zones")
    _common(metrics)
    metrics.add_argument("--format", choices=["text", "json"], default="text")
    metrics.set_defaults(run=_metrics)

    init = commands.add_parser("init", help="write rules inferred from the current imports")
    _common(init)
    init.add_argument("--force", action="store_true", help="regenerate existing rules")
    init.add_argument("--stdout", action="store_true", help="print instead of writing")
    init.add_argument(
        "--exclude", action="append", default=[], metavar="GLOB", help="file glob to leave out"
    )
    init.set_defaults(run=_init)

    serve = commands.add_parser("serve", help="open the interactive viewer in the browser")
    _common(serve)
    serve.add_argument("--host", default="127.0.0.1", help="interface to bind (default: localhost)")
    serve.add_argument("--port", type=int, default=8765, help="port (a free one if taken)")
    serve.add_argument("--no-open", action="store_true", help="do not open a browser")
    serve.add_argument("--watch", action="store_true", help="reanalyze when files change")
    serve.set_defaults(run=lambda args: _serve(args))
    return parser


COMMANDS = ("graph", "check", "metrics", "init", "serve", "why", "deps", "rdeps", "cycles")


def _with_default_command(argv: list[str]) -> list[str]:
    """`archview` and `archview <path>` open the viewer (requirement V13)."""
    if not argv or (argv[0] not in COMMANDS and not argv[0].startswith("-")):
        return ["serve", *argv]
    return argv


def main(argv: list[str] | None = None) -> int:
    argv = _with_default_command(sys.argv[1:] if argv is None else list(argv))
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except (UsageError, ProjectError, ConfigError) as error:
        sys.stderr.write(f"archview: {error}\n")
        return USAGE_ERROR


if __name__ == "__main__":
    sys.exit(main())
