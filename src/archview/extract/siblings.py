"""Resolve imports *between* sibling Python packages (issue #4).

grimp squashes an external import to its top-level name, so a package analysed on
its own records `plugin.adapter -> core` whether the source said `core.ports` or
`core.model`. The distinction is destroyed before any rule is checked, and the
import line cannot be read as text either: `from core import model as m2` names
only `core` while reaching `core.model`.

Building one graph over the packages together resolves it exactly, because grimp
then knows the structure of both. This module does that and nothing else. It takes
plain `{package name: source root}` data rather than a workspace, so it stays in
the extraction layer and is testable without opening a project.

The per-package models are untouched: this is a second, narrower query over the
same source, not a merged model (ADR 0012).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from contextlib import contextmanager, suppress
from pathlib import Path

import grimp

Where = tuple[str, int]
"""One import line: the importing module, and the line it sits on."""


@contextmanager
def _importable(roots: list[Path]):
    """Put every source root on sys.path for the resolution only."""
    entries = [str(root) for root in roots]
    sys.path[:0] = entries
    try:
        yield
    finally:
        for entry in entries:
            with suppress(ValueError):
                sys.path.remove(entry)


@contextmanager
def _unimported(roots: Mapping[str, Path]):
    """Evict a name from `sys.modules` for the resolution only, when it is already
    imported from somewhere other than the root about to be graphed.

    Grimp locates each top-level package with `importlib.util.find_spec`, which
    returns an already-imported module's cached spec without consulting `sys.path`
    at all. A process that has ever imported a same-named module from elsewhere -
    this project's own test suite is itself a package called `tests`, so analysing
    a project with a member or extra root also named `tests` (issue #10's own
    example) hits this in this very process - would otherwise silently resolve
    against the wrong package. Checking for a mismatch first, rather than evicting
    every graphed name unconditionally, means a name already imported from exactly
    the root we are about to graph it from - this project's own `archview` package,
    self-checking itself - is never touched at all.
    """
    saved = {
        name: sys.modules[name]
        for name, root in roots.items()
        if name in sys.modules and _elsewhere(sys.modules[name], root, name)
    }
    for name in saved:
        del sys.modules[name]
    try:
        yield
    finally:
        sys.modules.update(saved)


def _elsewhere(module, root: Path, name: str) -> bool:
    """True if `module` (already imported as `name`) was not loaded from `root`.

    `__path__` is a foreign package's own data - nothing enforces that every entry
    is a `str` or `os.PathLike`, so `Path()` is not safe to call on all of them
    unguarded. An entry of neither type is treated as not a match, the safe
    direction here: it still lets a real collision evict, and simply cannot rule
    the entry in as the expected root either.
    """
    paths = getattr(module, "__path__", None)
    if not paths:
        return True
    expected = (root / name).resolve()
    return not any(Path(p).resolve() == expected for p in paths if isinstance(p, str | os.PathLike))


def _owner(module: str, packages: frozenset[str]) -> str | None:
    """The package a module belongs to, or None if it belongs to none of them."""
    top = module.split(".")[0]
    return top if top in packages else None


def resolve_targets(roots: Mapping[str, Path]) -> dict[Where, str]:
    """Every import that crosses a package line, resolved to its exact target.

    `roots` maps a top-level package name to the source root that makes it
    importable. The value is the module the import really reaches - `core.model`
    where a single-package model would only ever say `core`.

    Imports inside one package, and imports of anything outside `roots`, are left
    out: this answers only "which part of a sibling did you touch".
    """
    if len(roots) < 2:
        return {}
    names = frozenset(roots)
    with _importable(sorted(roots.values(), key=str)), _unimported(roots):
        graph = grimp.build_graph(*sorted(names), include_external_packages=True, cache_dir=None)
        found = _cross_imports(graph, names)
    return dict(sorted(found.items()))


def _cross_imports(graph, names: frozenset[str]) -> dict[Where, str]:
    found: dict[Where, str] = {}
    for importer in graph.modules:
        source = _owner(importer, names)
        if source is None:
            continue
        for imported in graph.find_modules_directly_imported_by(importer):
            if _owner(imported, names) in (None, source):
                continue
            for detail in graph.get_import_details(importer=importer, imported=imported):
                found[(importer, detail["line_number"])] = imported
    return found
