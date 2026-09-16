"""Turn a Python code base into the model, using grimp for the import graph.

The analysed project is parsed, never imported or executed (requirement N2):
grimp locates the package on the path and reads the source, and the path entry
is removed again as soon as the graph is built. A second `ast` pass per file adds
what grimp does not report (`extract/facts.py`).
"""

from __future__ import annotations

import sys
from contextlib import contextmanager, suppress
from pathlib import Path

import grimp

from archview.extract.facts import FileFacts, scan
from archview.model.graph import ExtractionWarning, Import, Model, Node

STDLIB = frozenset(sys.stdlib_module_names) | {"__future__"}


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


def _is_internal(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def _kind(module: str, package: str, graph: grimp.ImportGraph) -> str:
    if not _is_internal(module, package):
        return "external"
    return "package" if graph.find_children(module) else "module"


def _facts(files: dict[str, str | None], base: Path) -> dict[str, FileFacts]:
    facts = {}
    for module, file in files.items():
        if file is not None:
            facts[module] = scan((base / file).read_text(errors="replace"))
    return facts


def build_model(package: str, source_root: Path, relative_to: Path | None = None) -> Model:
    """Build the model for one top-level package found under `source_root`."""
    source_root = Path(source_root).resolve()
    base = Path(relative_to).resolve() if relative_to else source_root
    with _importable(source_root):
        graph = grimp.build_graph(package, include_external_packages=True, cache_dir=None)

    internal_first = lambda m: (not _is_internal(m, package), m)  # noqa: E731
    modules = sorted((m for m in graph.modules if m not in STDLIB), key=internal_first)
    files = {
        m: _source_file(m, source_root, base) if _is_internal(m, package) else None for m in modules
    }
    facts = _facts(files, base)

    nodes = tuple(
        Node(
            id=module,
            parent=(module.rpartition(".")[0] or None) if _is_internal(module, package) else None,
            kind=_kind(module, package, graph),
            file=files[module],
            abstract=module in facts and facts[module].abstract,
        )
        for module in modules
    )
    return Model(
        project=package,
        nodes=nodes,
        imports=_imports(graph, package, files, facts),
        warnings=_warnings(files, facts),
    )


def _imports(graph, package, files, facts) -> tuple[Import, ...]:
    found = []
    for importer in graph.modules:
        if not _is_internal(importer, package):
            continue
        for imported in graph.find_modules_directly_imported_by(importer):
            if imported in STDLIB:
                continue
            for detail in graph.get_import_details(importer=importer, imported=imported):
                flags = facts[importer].flags(detail["line_number"]) if importer in facts else set()
                found.append(
                    Import(
                        importer=importer,
                        imported=imported,
                        file=files.get(importer) or "",
                        line=detail["line_number"],
                        text=detail["line_contents"],
                        type_checking="type_checking" in flags,
                        lazy="lazy" in flags,
                    )
                )
    return tuple(sorted(found, key=lambda i: (i.importer, i.imported, i.line)))


def _warnings(files, facts) -> tuple[ExtractionWarning, ...]:
    """Dynamic imports whose target is not a stdlib module (A5)."""
    found = []
    for module, file_facts in sorted(facts.items()):
        for dynamic in file_facts.dynamic:
            if dynamic.target is not None and dynamic.target.split(".")[0] in STDLIB:
                continue
            found.append(
                ExtractionWarning(
                    kind="dynamic_import",
                    module=module,
                    file=files[module] or "",
                    line=dynamic.line,
                    text=dynamic.text,
                    target=dynamic.target,
                )
            )
    return tuple(found)
