"""What the viewer is looking at: one analysed project, or a workspace of several,
with their views cached per (package, root).
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from archview.model.filter import without_tests
from archview.model.graph import Model
from archview.model.names import last
from archview.model.serialize import view_to_dict
from archview.model.view import View, build_view, tangled_packages
from archview.project import Project, baseline_path, open_project, project_report
from archview.render.check import report_to_dict
from archview.render.dot import to_dot
from archview.render.mermaid import to_mermaid
from archview.render.workspace import workspace_to_dict
from archview.rules.check import Report, WorkspaceReport
from archview.rules.config import ConfigError, find_config, load_config
from archview.rules.overlay import ImportKey, failing_imports, outside_targets, violating_edges
from archview.workspace import Workspace, check_workspace, open_workspace, workspace_view

POLL_SECONDS = 1.0

SOURCE_SUFFIXES = {
    "python": (".py",),
    "typescript": (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".json"),
}


def source_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Files to watch below `root`, skipping node_modules and hidden directories."""
    found: list[Path] = []
    for directory, subdirs, files in os.walk(root):
        subdirs[:] = [d for d in subdirs if d != "node_modules" and not d.startswith(".")]
        found.extend(Path(directory) / f for f in files if f.endswith(suffixes))
    return sorted(found)


class NotFound(Exception):
    pass


@dataclass(slots=True)
class _Analysis:
    """Everything one open `Project` needs to serve views and source: its check
    report (when it has rules), the outside names a rule violation must keep
    visible even without `--externals` (M7), and the packages with a cycle
    somewhere inside. Shared by a plain repo (keyed `None`) and every member of
    a workspace (keyed by package name)."""

    project: Project
    report: Report | None
    rules_error: str | None
    failing: frozenset[ImportKey]
    keep: frozenset[str]
    parents: set[str]
    tangled: frozenset[str]
    models: dict[bool, Model] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.models.setdefault(False, self.project.model)

    def model(self, hide_tests: bool) -> Model:
        if hide_tests not in self.models:
            self.models[hide_tests] = without_tests(self.project.model)
        return self.models[hide_tests]


def _analyse(project: Project) -> _Analysis:
    report, rules_error = None, None
    if project.config_path is not None:
        try:
            report = project_report(project)
        except ConfigError as error:
            rules_error = str(error)
    return _Analysis(
        project=project,
        report=report,
        rules_error=rules_error,
        failing=failing_imports(report) if report else frozenset(),
        keep=outside_targets(report) if report else frozenset(),
        parents={n.parent for n in project.model.nodes if n.parent},
        tangled=tangled_packages(project.model),
    )


def _project_signature(project: Project) -> list[tuple[str, float]]:
    language = project.model.language
    root = project.repo if language == "typescript" else project.source_root / project.package
    files = source_files(root, SOURCE_SUFFIXES.get(language, (".py",)))
    extra = [p for p in (project.config_path, baseline_path(project)) if p and p.is_file()]
    return [(str(p), p.stat().st_mtime_ns) for p in (*files, *extra) if p.exists()]


def _is_workspace_root(repo: Path, package: str | None, config_path: Path | None) -> bool:
    """Mirrors `cli._workspace_root`'s condition, for a plain `(repo, package,
    config_path)` triple rather than an `argparse.Namespace` - the server has no
    parsed args of its own, and `reload()` must be able to redo this check on
    every watch-triggered reanalysis."""
    if package is not None:
        return False
    path = config_path or find_config(repo)
    return path is not None and load_config(path).workspace is not None


class ViewerState:
    """The project or workspace the viewer is looking at, with its cached views."""

    def __init__(
        self,
        repo: Path,
        package: str | None = None,
        config_path: Path | None = None,
        language: str | None = None,
        tsconfig: str | None = None,
    ):
        self._args = (repo, package, config_path)
        self._options = {"language": language, "tsconfig": tsconfig}
        self._lock = threading.RLock()
        self.generation = 0
        self.watching = False
        self.error: str | None = None
        self.reload()

    # ---------- analysis ----------

    def reload(self) -> None:
        """Re-read the source, the rules and the baseline; views are rebuilt on demand.

        A workspace table at the root (and no `--package`) opens every member
        package; otherwise this is a plain, single-project repo, exactly as before.
        """
        repo, package, config_path = self._args
        root = Path(repo).expanduser().resolve()
        with self._lock:
            if _is_workspace_root(root, package, config_path):
                self._reload_workspace(root, config_path)
            else:
                self._reload_project()
            self._views: dict[tuple, tuple[View, dict[str, Any]]] = {}
            self._top: tuple[View, dict[str, Any]] | None = None
            self.generation += 1
            self.error = None

    def _reload_project(self) -> None:
        repo, package, config_path = self._args
        project = open_project(repo, package, config_path, **self._options)
        self.workspace: Workspace | None = None
        self.project: Project | None = project
        self._packages: dict[str | None, _Analysis] = {None: _analyse(project)}
        self._workspace_report: WorkspaceReport | None = None
        self._workspace_rules_error: str | None = None

    def _reload_workspace(self, root: Path, config_path: Path | None) -> None:
        ws = open_workspace(root, config_path)
        self.workspace = ws
        self.project = None
        self._packages = {p.name: _analyse(p.project) for p in ws.packages}
        try:
            self._workspace_report = check_workspace(ws)
            self._workspace_rules_error = None
        except ConfigError as error:
            self._workspace_report = None
            self._workspace_rules_error = str(error)

    def _analysis(self, package: str | None) -> _Analysis:
        if package in self._packages:
            return self._packages[package]
        if self.workspace is None:
            table = self.project.config.table
            raise NotFound(f"{package!r} is not a package; this repo has no [{table}.workspace]")
        names = ", ".join(p.name for p in self.workspace.packages)
        raise NotFound(
            f"no package {package!r} in workspace {self.workspace.name} (found: {names})"
        )

    def _failing_for(self, package: str | None) -> frozenset[ImportKey]:
        if package is None and self.workspace is not None:
            return (
                failing_imports(self._workspace_report.between)
                if self._workspace_report
                else frozenset()
            )
        return self._analysis(package).failing

    # ---------- watching (V9) ----------

    def _signature(self) -> tuple:
        parts: list[tuple[str, float]] = [
            entry
            for analysis in self._packages.values()
            for entry in _project_signature(analysis.project)
        ]
        if self.workspace is not None:
            rules = self.workspace.config.workspace
            extra = [find_config(self.workspace.root)]
            if rules and rules.baseline:
                extra.append(self.workspace.root / rules.baseline)
            parts += [(str(p), p.stat().st_mtime_ns) for p in extra if p and p.is_file()]
        return tuple(parts)

    def watch(self, interval: float = POLL_SECONDS) -> None:
        """Poll every package's source tree and reanalyze on change, in a daemon thread."""
        self.watching = True
        seen = self._signature()

        def loop() -> None:
            nonlocal seen
            while True:
                time.sleep(interval)
                try:
                    current = self._signature()
                    if current != seen:
                        seen = current
                        self.reload()
                except Exception as error:  # keep serving the last good analysis
                    self.error = f"reanalysis failed: {error}"

        threading.Thread(target=loop, name="archview-watch", daemon=True).start()

    # ---------- payloads ----------

    def summary(self) -> dict[str, Any]:
        return self._workspace_summary() if self.workspace is not None else self._project_summary()

    def _project_summary(self) -> dict[str, Any]:
        project, analysis = self.project, self._packages[None]
        report = analysis.report
        return {
            "project": project.package,
            "repo": project.repo.name,
            "language": project.model.language,
            "separator": project.model.separator,
            "rules": project.config_path.name if project.config_path else None,
            "rules_error": analysis.rules_error,
            "modules": sum(1 for n in project.model.nodes if n.file),
            "imports": len(project.model.imports),
            "generation": self.generation,
            "watching": self.watching,
            "error": self.error,
            "failing": sum(1 for p in report.problems if p.fails) if report else 0,
            "warnings": [asdict(w) for w in project.model.warnings],
            "workspace": False,
        }

    def _workspace_summary(self) -> dict[str, Any]:
        ws = self.workspace
        analyses = [self._packages[p.name] for p in ws.packages]
        between = self._workspace_report.between if self._workspace_report else None
        failing = sum(1 for p in between.problems if p.fails) if between else 0
        failing += sum(sum(1 for p in a.report.problems if p.fails) for a in analyses if a.report)
        return {
            "project": ws.name,
            "repo": ws.root.name,
            "language": None,
            "separator": None,
            "rules": ws.config.path,
            "rules_error": self._workspace_rules_error,
            "modules": sum(sum(1 for n in a.project.model.nodes if n.file) for a in analyses),
            "imports": sum(len(a.project.model.imports) for a in analyses),
            "generation": self.generation,
            "watching": self.watching,
            "error": self.error,
            "failing": failing,
            "warnings": [asdict(w) for a in analyses for w in a.project.model.warnings],
            "workspace": True,
            "packages": [p.name for p in ws.packages],
        }

    def check(self, package: str | None = None) -> dict[str, Any]:
        if package is None and self.workspace is not None:
            if self._workspace_report is None:
                raise NotFound(self._workspace_rules_error or "no rules file; run `archview init`")
            return workspace_to_dict(self._workspace_report)
        analysis = self._analysis(package)
        if analysis.report is None:
            raise NotFound(analysis.rules_error or "no rules file; run `archview init`")
        return report_to_dict(analysis.report)

    def _view(
        self, package: str | None, root: str | None, externals: bool, hide_tests: bool
    ) -> tuple[View, dict]:
        if package is None and self.workspace is not None:
            return self._top_view()
        analysis = self._analysis(package)
        root = root or analysis.project.package
        if root not in analysis.parents:
            raise NotFound(f"{root} is not a package of {analysis.project.package}")
        key = (package, root, externals, hide_tests)
        with self._lock:
            if key not in self._views:
                threshold = analysis.project.config.metrics.threshold
                model = analysis.model(hide_tests)
                view = build_view(model, root, externals, threshold, keep=analysis.keep)
                self._views[key] = (view, self._payload(view, analysis))
            return self._views[key]

    def _top_view(self) -> tuple[View, dict[str, Any]]:
        with self._lock:
            if self._top is None:
                view = workspace_view(self.workspace)
                self._top = (view, self._top_payload(view))
            return self._top

    def view(
        self,
        root: str | None = None,
        externals: bool = False,
        hide_tests: bool = False,
        package: str | None = None,
    ) -> dict:
        return self._view(package, root, externals, hide_tests)[1]

    def _payload(self, view: View, analysis: _Analysis) -> dict[str, Any]:
        violations = violating_edges(view, analysis.failing)
        data = view_to_dict(view)
        by_id = {n.id: n for n in analysis.project.model.nodes}
        for node in data["nodes"]:
            node["has_children"] = node["id"] in analysis.parents
            node["tangled"] = node["id"] in analysis.tangled
        for edge in data["edges"]:
            edge["violation"] = (edge["source"], edge["target"]) in violations
            for imp in edge["imports"]:
                imp["violation"] = (
                    imp["importer"],
                    imp["imported"],
                    imp["line"],
                ) in analysis.failing
        # A package's own root has no parent in its own model; in a workspace, "up"
        # from there leaves the package for the workspace top (M8).
        parent = by_id[view.root].parent
        if parent is None and self.workspace is not None:
            parent = self.workspace.name
        data["parent"] = parent
        data["dot"] = to_dot(view, analysis.tangled, violations)
        data["project"] = analysis.project.package
        data["separator"] = analysis.project.model.separator
        data["language"] = analysis.project.model.language
        return data

    def _top_payload(self, view: View) -> dict[str, Any]:
        """The workspace's top-level view: each node a package, always drillable."""
        failing = self._failing_for(None)
        violations = violating_edges(view, failing)
        tangled = {name for name, analysis in self._packages.items() if name in analysis.tangled}
        data = view_to_dict(view)
        for node in data["nodes"]:
            node["has_children"] = True
            node["tangled"] = node["id"] in tangled
        for edge in data["edges"]:
            edge["violation"] = (edge["source"], edge["target"]) in violations
            for imp in edge["imports"]:
                imp["violation"] = (imp["importer"], imp["imported"], imp["line"]) in failing
        data["parent"] = None
        data["dot"] = to_dot(view, tangled, violations)
        data["project"] = self.workspace.name
        data["separator"] = "."
        data["language"] = None
        return data

    def export(
        self,
        root: str | None,
        fmt: str,
        externals: bool,
        hide_tests: bool,
        package: str | None = None,
    ) -> str:
        view, data = self._view(package, root, externals, hide_tests)
        if fmt == "dot":
            return data["dot"]
        if fmt == "mermaid":
            return to_mermaid(view, violating_edges(view, self._failing_for(package)))
        raise NotFound(f"unknown export format {fmt!r}")

    def tree(
        self, root: str | None = None, hide_tests: bool = False, package: str | None = None
    ) -> dict[str, Any]:
        """The packages and modules under a root, nested, packages first (V15)."""
        if package is None and self.workspace is not None:
            raise NotFound("pick a package: the workspace top level has no file tree")
        analysis = self._analysis(package)
        root = root or analysis.project.package
        model = analysis.model(hide_tests)
        by_id = {n.id: n for n in model.nodes}
        if root not in analysis.parents or root not in by_id:
            raise NotFound(f"{root} is not a package of {analysis.project.package}")
        children: dict[str, list] = {}
        for node in model.nodes:
            if node.parent:
                children.setdefault(node.parent, []).append(node)

        def item(node) -> dict[str, Any]:
            kids = sorted(children.get(node.id, ()), key=lambda n: (n.kind != "package", n.id))
            return {
                "id": node.id,
                "name": last(node.id, model.separator),
                "kind": node.kind,
                "abstract": node.abstract,
                "tangled": node.id in analysis.tangled,
                "children": [item(k) for k in kids],
            }

        return {**item(by_id[root]), "parent": by_id[root].parent}

    def source(self, module: str, package: str | None = None) -> dict[str, Any]:
        if package is None and self.workspace is not None:
            raise NotFound(f"{module} has no source file")
        analysis = self._analysis(package)
        node = next((n for n in analysis.project.model.nodes if n.id == module), None)
        if node is None or node.file is None:
            raise NotFound(f"{module} has no source file")
        path = analysis.project.repo / node.file
        return {
            "module": module,
            "file": node.file,
            "abstract": node.abstract,
            "text": path.read_text(errors="replace"),
            "imports": [
                {**asdict(i), "violation": (i.importer, i.imported, i.line) in analysis.failing}
                for i in analysis.project.model.imports
                if i.importer == module
            ],
            "warnings": [asdict(w) for w in analysis.project.model.warnings if w.module == module],
        }
