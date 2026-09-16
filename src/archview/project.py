"""Open a repo: find its rules, its package and build the filtered model.

Shared by every face of the tool (the CLI commands and the server), so they all see
the same model for the same repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from archview.extract.discover import find_packages
from archview.extract.python import build_model
from archview.model.filter import without_files
from archview.model.graph import Model
from archview.rules.baseline import BASELINE_FILE, apply_baseline, load_baseline
from archview.rules.check import Report, check
from archview.rules.config import Config, ConfigError, find_config, load_config


class ProjectError(Exception):
    """The repo cannot be analysed as asked."""


@dataclass(frozen=True, slots=True)
class Project:
    repo: Path
    package: str
    source_root: Path
    config: Config
    config_path: Path | None
    model: Model


def open_project(
    repo: Path,
    package: str | None = None,
    config_path: Path | None = None,
    config: Config | None = None,
) -> Project:
    """Analyse `repo` with the rules at `config_path`, found in the repo, or given as `config`."""
    repo = Path(repo).expanduser().resolve()
    if not repo.is_dir():
        raise ProjectError(f"{repo} is not a directory")
    path = config_path or find_config(repo)
    if config is None:
        config = load_config(path) if path else Config()
    packages = _packages(repo, config)
    name = _choose(packages, repo, package or config.package)
    model = build_model(name, packages[name], relative_to=repo)
    return Project(repo, name, packages[name], config, path, without_files(model, config.exclude))


def _packages(repo: Path, config: Config) -> dict[str, Path]:
    if not config.source_roots:
        return find_packages(repo)
    found: dict[str, Path] = {}
    for root in config.source_roots:
        base = repo / root
        for child in sorted(base.iterdir()) if base.is_dir() else ():
            if child.is_dir() and child.name not in found and any(child.glob("*.py")):
                found[child.name] = base
    return found


def _choose(packages: dict[str, Path], repo: Path, asked: str | None) -> str:
    names = ", ".join(sorted(packages)) or "none"
    if asked is not None:
        if asked not in packages:
            raise ProjectError(f"no package {asked!r} in {repo} (found: {names})")
        return asked
    if not packages:
        raise ProjectError(f"no Python package found in {repo}")
    if len(packages) > 1:
        raise ProjectError(f"several packages in {repo} ({names}); pick one with --package")
    return next(iter(packages))


def baseline_path(project: Project) -> Path:
    """Next to the rules file unless `baseline` names another place (relative to it)."""
    base = project.config_path.parent if project.config_path else project.repo
    return base / (project.config.baseline or BASELINE_FILE)


def project_report(project: Project) -> Report:
    """`archview check` for this project, with its baseline applied when there is one."""
    report = check(project.model, project.config)
    path = baseline_path(project)
    if path.is_file():
        report = apply_baseline(report, load_baseline(path), path.name)
    elif project.config.baseline:
        raise ConfigError(f"baseline {path} does not exist; `archview check --update-baseline`")
    return report
