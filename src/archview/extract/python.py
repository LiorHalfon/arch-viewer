"""Turn a Python code base into the model, using grimp for the import graph.

The analysed project is parsed, never imported or executed (requirement N2):
grimp locates the package on the path and reads the source, and the path entry
is removed again as soon as the graph is built.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager, suppress
from pathlib import Path

import grimp

from archview.model.graph import Import, Model, Node


@contextmanager
def _importable(source_root: Path):
    """Put `source_root` on sys.path for the extraction only."""
    entry = str(source_root)
    sys.path.insert(0, entry)
    try:
        yield
    finally:
        with suppress(ValueError):
            sys.path.remove(entry)


def _source_file(module: str, source_root: Path, relative_to: Path) -> str | None:
    """`a.b.c` -> the file that defines it, relative to `relative_to`."""
    stem = source_root.joinpath(*module.split("."))
    for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
        if candidate.is_file():
            return candidate.relative_to(relative_to).as_posix()
    return None


def _kind(module: str, graph: grimp.ImportGraph) -> str:
    return "package" if graph.find_children(module) else "module"


def build_model(package: str, source_root: Path, relative_to: Path | None = None) -> Model:
    """Build the model for one top-level package found under `source_root`."""
    source_root = Path(source_root).resolve()
    base = Path(relative_to).resolve() if relative_to else source_root
    with _importable(source_root):
        graph = grimp.build_graph(package, cache_dir=None)

    nodes = tuple(
        Node(
            id=module,
            parent=module.rpartition(".")[0] or None,
            kind=_kind(module, graph),
            file=_source_file(module, source_root, base),
        )
        for module in sorted(graph.modules)
    )
    imports = tuple(
        sorted(
            (
                Import(
                    importer=importer,
                    imported=imported,
                    file=_source_file(importer, source_root, base) or "",
                    line=detail["line_number"],
                    text=detail["line_contents"],
                )
                for importer in graph.modules
                for imported in graph.find_modules_directly_imported_by(importer)
                for detail in graph.get_import_details(importer=importer, imported=imported)
            ),
            key=lambda i: (i.importer, i.imported, i.line),
        )
    )
    return Model(project=package, nodes=nodes, imports=imports)
