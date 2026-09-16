"""What the viewer is looking at: one analysed project, with views cached per root."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Any

from archview.model.serialize import view_to_dict
from archview.model.view import View, build_view, tangled_packages
from archview.project import Project, open_project
from archview.render.dot import to_dot


class NotFound(Exception):
    pass


class Workspace:
    def __init__(self, repo: Path, package: str | None = None, config_path: Path | None = None):
        self._args = (repo, package, config_path)
        self._lock = Lock()
        self.reload()

    def reload(self) -> None:
        """Re-read the source and the rules; views are rebuilt on demand."""
        project = open_project(*self._args)
        with self._lock:
            self.project: Project = project
            self._by_id = {n.id: n for n in project.model.nodes}
            self._parents = {n.parent for n in project.model.nodes if n.parent}
            self._tangled = tangled_packages(project.model)
            self._views: dict[str, dict[str, Any]] = {}

    def summary(self) -> dict[str, Any]:
        project = self.project
        return {
            "project": project.package,
            "repo": project.repo.name,
            "rules": project.config_path.name if project.config_path else None,
            "modules": sum(1 for n in project.model.nodes if n.file),
            "imports": len(project.model.imports),
        }

    def view(self, root: str | None) -> dict[str, Any]:
        root = root or self.project.package
        if root not in self._parents:
            raise NotFound(f"{root} is not a package of {self.project.package}")
        with self._lock:
            if root not in self._views:
                self._views[root] = self._payload(build_view(self.project.model, root))
            return self._views[root]

    def _payload(self, view: View) -> dict[str, Any]:
        data = view_to_dict(view)
        for node in data["nodes"]:
            node["has_children"] = node["id"] in self._parents
            node["tangled"] = node["id"] in self._tangled
        data["parent"] = self._by_id[view.root].parent
        data["dot"] = to_dot(view, self._tangled)
        return data

    def source(self, module: str) -> dict[str, Any]:
        node = self._by_id.get(module)
        if node is None or node.file is None:
            raise NotFound(f"{module} has no source file")
        path = self.project.repo / node.file
        return {
            "module": module,
            "file": node.file,
            "text": path.read_text(errors="replace"),
            "imports": [asdict(i) for i in self.project.model.imports if i.importer == module],
        }
