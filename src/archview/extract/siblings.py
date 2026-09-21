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
    with _importable(sorted(roots.values(), key=str)):
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
