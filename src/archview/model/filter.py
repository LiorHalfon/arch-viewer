"""Remove parts of a model before anything is derived from it (requirement A11)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from archview.model.graph import Model
from archview.model.names import within
from archview.model.patterns import matches_name, matches_path


def without_files(model: Model, patterns: Iterable[str]) -> Model:
    """Drop every node whose file matches a pattern, its subtree, and the imports touching them."""
    patterns = tuple(patterns)
    if not patterns:
        return model
    dropped: set[str] = set()
    for node in model.nodes:  # sorted by id, so a parent comes before its children
        excluded = node.file is not None and any(matches_path(p, node.file) for p in patterns)
        if excluded or node.parent in dropped:
            dropped.add(node.id)
    return replace(
        model,
        nodes=tuple(n for n in model.nodes if n.id not in dropped),
        imports=tuple(
            i for i in model.imports if i.importer not in dropped and i.imported not in dropped
        ),
        warnings=tuple(w for w in model.warnings if w.module not in dropped),
    )


TEST_NAMES = {
    "python": ("**.tests", "**.test", "**.test_*", "**.*_test", "**.*_tests", "**.conftest"),
    "typescript": (
        "**/*.test.*",
        "**/*.spec.*",
        "**/*.e2e.*",
        "**/__tests__",
        "**/__mocks__",
        "**/test",
        "**/tests",
        "**/e2e",
    ),
}


def without_names(model: Model, patterns: Iterable[str]) -> Model:
    """Drop every node whose name matches a pattern (with its subtree)."""
    patterns = tuple(patterns)
    dropped = {
        n.id for n in model.nodes if any(matches_name(p, n.id, model.separator) for p in patterns)
    }
    if not dropped:
        return model
    return replace(
        model,
        nodes=tuple(n for n in model.nodes if n.id not in dropped),
        imports=tuple(
            i for i in model.imports if i.importer not in dropped and i.imported not in dropped
        ),
        warnings=tuple(w for w in model.warnings if w.module not in dropped),
    )


def without_tests(model: Model) -> Model:
    """Hide test packages and modules by their conventional names (V10)."""
    return without_names(model, TEST_NAMES.get(model.language, ()))


def scoped_model(model: Model, scope: str) -> Model:
    """Cut the model down to the package `scope`, which becomes the root of the result.

    It keeps the imports between the modules of the scope, and the imports they make of
    packages outside the project, with those packages (issue #18). Imports into the
    rest of the project and extraction warnings are dropped: the rules above the scope
    check those.
    """
    sep = model.separator
    outside = {n.id for n in model.nodes if n.kind == "external"}
    imports = tuple(
        i
        for i in model.imports
        if within(i.importer, scope, sep)
        and (within(i.imported, scope, sep) or i.imported in outside)
    )
    reached = {i.imported for i in imports} & outside
    nodes = tuple(
        replace(n, parent=None) if n.id == scope else n
        for n in model.nodes
        if (n.kind != "external" and within(n.id, scope, sep)) or n.id in reached
    )
    return replace(model, project=scope, nodes=nodes, imports=imports, warnings=())
