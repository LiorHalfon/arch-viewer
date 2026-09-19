"""Open a workspace: several packages, each with its own project, joined by name.

A cross-package import already shows up as an outside edge in each package's own
model (M7's outside edges). This module does the one new thing workspace mode needs:
attribute an outside name to the sibling package it belongs to, so a later checker or
view can treat it as a workspace edge rather than an ordinary third-party one.

The structure is a federation, not a merged model: each package keeps its own
`Project`, language and separator. Merging would collide Python's `.` ids with
TypeScript's `/` ids, since `Model` carries a single `project` string and a single
`separator` (see docs/superpowers/specs/2026-09-20-workspace-design.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from archview.project import Project, open_project
from archview.rules.config import RULES_FILE, Config, ConfigError, find_config, load_config


@dataclass(frozen=True, slots=True)
class Package:
    """One workspace member: its own project, plus how siblings may refer to it."""

    name: str
    path: Path
    aliases: frozenset[str]
    project: Project
    has_rules: bool


@dataclass(frozen=True, slots=True)
class Workspace:
    name: str
    root: Path
    packages: tuple[Package, ...]
    config: Config


def open_workspace(root: Path, config_path: Path | None = None) -> Workspace:
    """Open every package the `[archview.workspace]` table at `root` lists."""
    root = Path(root).expanduser().resolve()
    path = config_path or find_config(root)
    config = load_config(path) if path else Config()
    if config.workspace is None:
        raise ConfigError(f"no [archview.workspace] table in {path or root / RULES_FILE}")
    base = path.parent if path else root
    packages = _open_packages(config.workspace.packages, base)
    return Workspace(config.package or root.name, root, packages, config)


def _open_packages(entries: tuple[str, ...], base: Path) -> tuple[Package, ...]:
    """Open each listed package path, sorted by name; reject a name collision."""
    by_name: dict[str, Package] = {}
    for entry in entries:
        package = _open_package(base / entry)
        clash = by_name.get(package.name)
        if clash is not None:
            raise ConfigError(
                f"two workspace packages are both named {package.name!r}: "
                f"{clash.path} and {package.path}"
            )
        by_name[package.name] = package
    return tuple(sorted(by_name.values(), key=lambda p: p.name))


def _open_package(path: Path) -> Package:
    project = open_project(path)
    return Package(
        name=project.package,
        path=project.repo,
        aliases=aliases(project),
        project=project,
        has_rules=project.config_path is not None,
    )


def aliases(project: Project) -> frozenset[str]:
    """How siblings may refer to `project`: its top-level name, plus, for
    TypeScript, the name(s) its `package.json` gives it."""
    names = {project.package}
    if project.model.language == "typescript":
        names |= _npm_names(project.repo)
    return frozenset(names)


def _npm_names(repo: Path) -> set[str]:
    """The `package.json` `name`, with and without an `@scope/` prefix; a missing
    or malformed file is ignored rather than failing the run."""
    try:
        data = json.loads((repo / "package.json").read_text())
    except (OSError, ValueError):
        return set()
    name = data.get("name") if isinstance(data, dict) else None
    return {name, name.split("/", 1)[-1]} if isinstance(name, str) and name else set()


def _owner(outside: str, importer: Package, packages: tuple[Package, ...]) -> str | None:
    """Which sibling `outside` names, from `importer`'s point of view."""
    if outside.startswith("../"):
        return _owner_by_path(outside, importer, packages)
    return next(
        (p.name for p in sorted(packages, key=lambda p: p.name) if outside in p.aliases), None
    )


def _owner_by_path(outside: str, importer: Package, packages: tuple[Package, ...]) -> str | None:
    """A `../`-relative resolution belongs to whichever package's directory contains it."""
    target = (importer.path / outside).resolve()
    return next(
        (p.name for p in sorted(packages, key=lambda p: p.name) if target.is_relative_to(p.path)),
        None,
    )
