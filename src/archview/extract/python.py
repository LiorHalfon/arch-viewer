"""Turn a Python code base into the model, using grimp for the import graph.

The analysed project is parsed, never imported or executed (requirement N2):
grimp locates the package on the path and reads the source, and the path entry
is removed again as soon as the graph is built. A second `ast` pass per file adds
what grimp does not report (`extract/facts.py`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import grimp

from archview.extract.facts import FileFacts, scan
from archview.extract.siblings import _importable, _unimported
from archview.model.graph import ExtractionWarning, Import, Model, Node

STDLIB = frozenset(sys.stdlib_module_names) | {"__future__"}


def _source_file(module: str, source_root: Path, relative_to: Path) -> str | None:
    """`a.b.c` -> the file that defines it, relative to `relative_to`."""
    stem = source_root.joinpath(*module.split("."))
    for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
        if candidate.is_file():
            return candidate.relative_to(relative_to).as_posix()
    return None


def _is_internal(module: str, roots: frozenset[str]) -> bool:
    """True if `module`'s top-level name is the analysed package or an extra root
    (issue #10) - equivalent to `module == root or module.startswith(root + ".")`
    for whichever `root` in `roots` it belongs to, since a top-level package name
    never itself contains a dot."""
    return module.split(".")[0] in roots


def _kind(module: str, roots: frozenset[str], graph: grimp.ImportGraph) -> str:
    if not _is_internal(module, roots):
        return "external"
    return "package" if graph.find_children(module) else "module"


def _facts(files: dict[str, str | None], base: Path) -> dict[str, FileFacts]:
    facts = {}
    for module, file in files.items():
        if file is not None:
            facts[module] = scan((base / file).read_text(errors="replace"))
    return facts


def build_model(
    package: str,
    source_root: Path,
    relative_to: Path | None = None,
    extra: tuple[tuple[str, Path], ...] = (),
) -> Model:
    """Build the model for `package`, plus every other top-level package `extra`
    names (issue #10): grimp graphs them together, exactly as `extract/siblings.py`
    does for sibling packages (M9), so a module under an extra root is internal
    rather than an outside name. Each extra root is one component, named after
    itself - as the project's own root module is a component named after the
    project (ADR 0006). `Model.project` always stays `package`.
    """
    source_root = Path(source_root).resolve()
    base = Path(relative_to).resolve() if relative_to else source_root
    roots = {package: source_root} | {name: Path(root).resolve() for name, root in extra}
    names = frozenset(roots)
    with _importable(sorted(roots.values(), key=str)), _unimported(roots):
        graph = grimp.build_graph(*sorted(names), include_external_packages=True, cache_dir=None)

    internal_first = lambda m: (not _is_internal(m, names), m)  # noqa: E731
    modules = sorted((m for m in graph.modules if m not in STDLIB), key=internal_first)
    files = {
        m: _source_file(m, roots[m.split(".")[0]], base) if _is_internal(m, names) else None
        for m in modules
    }
    facts = _facts(files, base)

    nodes = tuple(
        Node(
            id=module,
            parent=(module.rpartition(".")[0] or None) if _is_internal(module, names) else None,
            kind=_kind(module, names, graph),
            file=files[module],
            abstract=module in facts and facts[module].abstract,
        )
        for module in modules
    )
    return Model(
        project=package,
        nodes=nodes,
        imports=_imports(graph, names, files, facts),
        warnings=_warnings(files, facts),
    )


def _imports(graph, roots: frozenset[str], files, facts) -> tuple[Import, ...]:
    found = []
    for importer in graph.modules:
        if not _is_internal(importer, roots):
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
