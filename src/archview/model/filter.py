"""Remove parts of a model before anything is derived from it (requirement A11)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from archview.model.graph import Model
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


TEST_NAMES = ("**.tests", "**.test", "**.test_*", "**.*_test", "**.*_tests", "**.conftest")


def without_names(model: Model, patterns: Iterable[str]) -> Model:
    """Drop every node whose dotted name matches a pattern (with its subtree)."""
    patterns = tuple(patterns)
    dropped = {n.id for n in model.nodes if any(matches_name(p, n.id) for p in patterns)}
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
    return without_names(model, TEST_NAMES)
