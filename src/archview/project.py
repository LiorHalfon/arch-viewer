"""Open a repo: find its rules, its package and build the filtered model.

Shared by every face of the tool (the CLI commands and the server), so they all see
the same model for the same repo.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, replace
from pathlib import Path

from archview.extract import typescript
from archview.extract.discover import find_packages
from archview.extract.python import build_model
from archview.model.filter import without_files
from archview.model.graph import Model
from archview.rules.baseline import BASELINE_FILE, apply_baseline, load_baseline
from archview.rules.check import Notice, Report, check
from archview.rules.config import Config, ConfigError, find_config, load_config


class ProjectError(Exception):
    """The repo cannot be analysed as asked."""


class SeveralPackages(ProjectError):
    """More than one top-level Python package, and none was named."""


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
    language: str | None = None,
    tsconfig: str | None = None,
) -> Project:
    """Analyse `repo` with the rules at `config_path`, found in the repo, or given as `config`."""
    repo = Path(repo).expanduser().resolve()
    if not repo.is_dir():
        raise ProjectError(f"{repo} is not a directory")
    path = config_path or find_config(repo)
    if config is None:
        config = load_config(path) if path else Config()
    tsconfig = tsconfig or config.tsconfig
    if _language(repo, config, language, tsconfig) == "typescript":
        model = _typescript_model(repo, config, package or config.package, tsconfig)
        return Project(
            repo, model.project, repo, config, path, without_files(model, config.exclude)
        )
    packages = _packages(repo, config)
    name = _choose(packages, repo, package or config.package)
    extra = (
        tuple(sorted((n, root) for n, root in packages.items() if n != name))
        if config.source_roots
        else ()
    )
    model = build_model(name, packages[name], relative_to=repo, extra=extra)
    return Project(repo, name, packages[name], config, path, without_files(model, config.exclude))


def _language(repo: Path, config: Config, asked: str | None, tsconfig: str | None) -> str:
    """`--language`, then the rules file; else a tsconfig means TypeScript."""
    chosen = asked or config.language
    if chosen:
        return chosen
    return "typescript" if tsconfig or (repo / "tsconfig.json").is_file() else "python"


def _typescript_model(repo: Path, config: Config, name: str | None, tsconfig: str | None) -> Model:
    if len(config.source_roots) > 1:
        raise ProjectError(
            "a TypeScript project has one source root; "
            f"source_roots lists {len(config.source_roots)}"
        )
    root = config.source_roots[0] if config.source_roots else None
    try:
        return typescript.extract(repo, name, tsconfig, root)
    except typescript.ExtractionError as error:
        raise ProjectError(str(error)) from None


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
        raise SeveralPackages(f"several packages in {repo} ({names}); pick one with --package")
    return next(iter(packages))


def baseline_path(project: Project) -> Path:
    """Next to the rules file unless `baseline` names another place (relative to it)."""
    base = project.config_path.parent if project.config_path else project.repo
    return base / (project.config.baseline or BASELINE_FILE)


def project_report(project: Project, in_workspace: bool = False) -> Report:
    """`archview check` for this project, with its baseline applied when there is one."""
    report = check(project.model, project.config, in_workspace)
    report = replace(report, warnings=report.warnings + tuple(_empty_source_root_warnings(project)))
    path = baseline_path(project)
    if path.is_file():
        report = apply_baseline(report, load_baseline(path), path.name)
    elif project.config.baseline:
        raise ConfigError(f"baseline {path} does not exist; `archview check --update-baseline`")
    return report


def _empty_source_root_warnings(project: Project) -> list[Notice]:
    """A `source_roots` entry that did not contribute to the analysed package
    (issue #10). Each language has its own truthful way to answer "did this root
    contribute anything", so this asks that language's own question rather than
    guessing from one shared rule - mirroring the existing `language`-gated seams for
    this same `source_root` discrepancy (`workspace.py`'s `p.project.model.language
    == "python"`, `server/state.py`'s branch on `"typescript"`)."""
    roots = project.config.source_roots
    if not roots:
        return []
    empty = (
        _empty_typescript_roots(project, roots)
        if project.model.language == "typescript"
        else _empty_python_roots(project, roots)
    )
    return [
        Notice(
            "empty_source_root",
            f"source root {root!r} contributed no modules to package {project.package!r}; "
            "only code under the package is analysed",
        )
        for root in empty
    ]


def _empty_python_roots(project: Project, roots: tuple[str, ...]) -> list[str]:
    """`_packages`/`_choose` pick exactly one winning root per package, and
    `project.source_root` is it - so a naive version of this would compare each
    configured root's *resolved* path against only the winner's. That over-reports:
    `source_roots = ["src", "plugins"]` with `a` under `src/` and `b` under
    `plugins/` is not a mistake - `package` exists for exactly this repo shape - so a
    root that produced a *sibling* package the current `--package` run did not select
    must not read as contributing nothing (Fix 4, review). This asks `_packages`
    again - the same question `open_project` already asked to pick a winner - for
    every root that produced *any* package, not just the chosen one, and only a root
    absent from that whole set is reported. A single configured root is never empty
    here: `_choose` raises `ProjectError` before `open_project` returns a `Project`
    unless that lone root was the one that produced the package."""
    if len(roots) <= 1:
        return []
    produced = {base.resolve() for base in _packages(project.repo, project.config).values()}
    return sorted(root for root in set(roots) if (project.repo / root).resolve() not in produced)


def _empty_typescript_roots(project: Project, roots: tuple[str, ...]) -> list[str]:
    """Unlike the Python path, `typescript.build_model`'s own root filter (`_below`)
    never validates that a configured root matched anything, so a bad single root -
    the only multiplicity TypeScript allows, `_typescript_model` rejects more than
    one - still lets `open_project` succeed, silently, with an almost-empty model.
    Ask the model directly instead: a TypeScript `Node.file` carries the configured
    root as a literal prefix by construction, so a root none of them start with
    contributed nothing - exactly what the base commit's string check got right for
    this language."""
    files = [n.file for n in project.model.nodes if n.file]
    return sorted(root for root in set(roots) if not any(_under_ts_root(f, root) for f in files))


def _under_ts_root(file: str, root: str) -> bool:
    prefix = _ts_root_prefix(root)
    return not prefix or file == prefix or file.startswith(f"{prefix}/")


def _ts_root_prefix(root: str) -> str:
    """Normalise a configured root the way `posixpath.normpath` would resolve it -
    handling `"./"`, a trailing slash and `"a/../a"` - without touching the
    filesystem: `Node.file` here is a path string from the model, not a real path
    relative to this process's cwd."""
    normalized = posixpath.normpath(root)
    return "" if normalized in (".", "") else normalized
