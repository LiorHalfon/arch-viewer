"""What the viewer is looking at: one analysed project, with views cached per root."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from archview.model.filter import without_tests
from archview.model.graph import Model
from archview.model.serialize import view_to_dict
from archview.model.view import View, build_view, tangled_packages
from archview.project import Project, baseline_path, open_project, project_report
from archview.render.check import report_to_dict
from archview.render.dot import to_dot
from archview.render.mermaid import to_mermaid
from archview.rules.config import ConfigError
from archview.rules.overlay import failing_imports, violating_edges

POLL_SECONDS = 1.0


class NotFound(Exception):
    pass


class Workspace:
    def __init__(self, repo: Path, package: str | None = None, config_path: Path | None = None):
        self._args = (repo, package, config_path)
        self._lock = threading.RLock()
        self.generation = 0
        self.watching = False
        self.error: str | None = None
        self.reload()

    # ---------- analysis ----------

    def reload(self) -> None:
        """Re-read the source, the rules and the baseline; views are rebuilt on demand."""
        project = open_project(*self._args)
        report, rules_error = None, None
        if project.config_path is not None:
            try:
                report = project_report(project)
            except ConfigError as error:
                rules_error = str(error)
        with self._lock:
            self.project: Project = project
            self.report = report
            self.rules_error = rules_error
            self._failing = failing_imports(report) if report else frozenset()
            self._models: dict[bool, Model] = {False: project.model}
            self._parents = {n.parent for n in project.model.nodes if n.parent}
            self._tangled = tangled_packages(project.model)
            self._views: dict[tuple[str, bool, bool], tuple[View, dict[str, Any]]] = {}
            self.generation += 1
            self.error = None

    def _model(self, hide_tests: bool) -> Model:
        if hide_tests not in self._models:
            self._models[hide_tests] = without_tests(self.project.model)
        return self._models[hide_tests]

    # ---------- watching (V9) ----------

    def _signature(self) -> tuple:
        project = self.project
        roots = [project.source_root / project.package]
        files = sorted(p for root in roots for p in root.rglob("*.py"))
        extra = [p for p in (project.config_path, baseline_path(project)) if p and p.is_file()]
        return tuple((str(p), p.stat().st_mtime_ns) for p in (*files, *extra) if p.exists())

    def watch(self, interval: float = POLL_SECONDS) -> None:
        """Poll the source tree and reanalyze on change, in a daemon thread."""
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
        project, report = self.project, self.report
        return {
            "project": project.package,
            "repo": project.repo.name,
            "rules": project.config_path.name if project.config_path else None,
            "rules_error": self.rules_error,
            "modules": sum(1 for n in project.model.nodes if n.file),
            "imports": len(project.model.imports),
            "generation": self.generation,
            "watching": self.watching,
            "error": self.error,
            "failing": sum(1 for p in report.problems if p.fails) if report else 0,
            "warnings": [asdict(w) for w in project.model.warnings],
        }

    def check(self) -> dict[str, Any]:
        if self.report is None:
            raise NotFound(self.rules_error or "no rules file; run `archview init`")
        return report_to_dict(self.report)

    def _view(self, root: str | None, externals: bool, hide_tests: bool) -> tuple[View, dict]:
        root = root or self.project.package
        if root not in self._parents:
            raise NotFound(f"{root} is not a package of {self.project.package}")
        key = (root, externals, hide_tests)
        with self._lock:
            if key not in self._views:
                threshold = self.project.config.metrics.threshold
                view = build_view(self._model(hide_tests), root, externals, threshold)
                self._views[key] = (view, self._payload(view))
            return self._views[key]

    def view(self, root: str | None, externals: bool = False, hide_tests: bool = False) -> dict:
        return self._view(root, externals, hide_tests)[1]

    def _payload(self, view: View) -> dict[str, Any]:
        violations = violating_edges(view, self._failing)
        data = view_to_dict(view)
        by_id = {n.id: n for n in self.project.model.nodes}
        for node in data["nodes"]:
            node["has_children"] = node["id"] in self._parents
            node["tangled"] = node["id"] in self._tangled
        for edge in data["edges"]:
            edge["violation"] = (edge["source"], edge["target"]) in violations
            for imp in edge["imports"]:
                imp["violation"] = (imp["importer"], imp["imported"], imp["line"]) in self._failing
        data["parent"] = by_id[view.root].parent
        data["dot"] = to_dot(view, self._tangled, violations)
        return data

    def export(self, root: str | None, fmt: str, externals: bool, hide_tests: bool) -> str:
        view, data = self._view(root, externals, hide_tests)
        if fmt == "dot":
            return data["dot"]
        if fmt == "mermaid":
            return to_mermaid(view, violating_edges(view, self._failing))
        raise NotFound(f"unknown export format {fmt!r}")

    def source(self, module: str) -> dict[str, Any]:
        node = next((n for n in self.project.model.nodes if n.id == module), None)
        if node is None or node.file is None:
            raise NotFound(f"{module} has no source file")
        path = self.project.repo / node.file
        return {
            "module": module,
            "file": node.file,
            "abstract": node.abstract,
            "text": path.read_text(errors="replace"),
            "imports": [
                {**asdict(i), "violation": (i.importer, i.imported, i.line) in self._failing}
                for i in self.project.model.imports
                if i.importer == module
            ],
            "warnings": [asdict(w) for w in self.project.model.warnings if w.module == module],
        }
