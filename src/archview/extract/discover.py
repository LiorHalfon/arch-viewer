"""Work out which top-level packages a Python repo contains, and from where.

This is the only reason `archview` needs no configuration for the common case
(requirement V13); the rules file will be able to override it in M2.
"""

from __future__ import annotations

from pathlib import Path

SKIP_DIRS = frozenset(
    {
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
)


def _candidates(bases: list[Path]):
    """Every directory that could hold a package, base by base, name-sorted."""
    for base in bases:
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if (
                child.is_dir()
                and child.name not in SKIP_DIRS
                and not child.name.startswith((".", "_"))
            ):
                yield base, child


def find_packages(repo: Path) -> dict[str, Path]:
    """Map each top-level package name to the directory that must be importable."""
    repo = Path(repo)
    src = repo / "src"
    if (src / "__init__.py").is_file():  # 'src' is itself the package
        return {"src": repo}

    bases = [src, repo] if src.is_dir() else [repo]
    found = _first_wins(bases, lambda d: (d / "__init__.py").is_file())
    if not found:  # namespace packages have no __init__.py
        found = _first_wins(bases, lambda d: any(d.glob("*.py")))
    return found


def _first_wins(bases: list[Path], is_package) -> dict[str, Path]:
    """src/ is searched before the repo root, and the first hit for a name wins."""
    found: dict[str, Path] = {}
    for base, child in _candidates(bases):
        if child.name not in found and is_package(child):
            found[child.name] = base
    return found
