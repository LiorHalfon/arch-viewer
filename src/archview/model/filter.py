"""Remove parts of a model before anything is derived from it (requirement A11)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from archview.model.graph import Model
from archview.model.patterns import matches_path


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
    )
