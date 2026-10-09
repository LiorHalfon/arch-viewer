"""Hierarchy on node ids: a name, its parent and its ancestors.

Python ids are split by '.', TypeScript ids by '/' (ADR 0010). `sep` is always passed
explicitly - from `Model.separator` - so no caller silently assumes one language.
"""

from __future__ import annotations

from archview.model.graph import Model


def within(name: str, ancestor: str, sep: str) -> bool:
    """True if `name` is `ancestor` or lies below it."""
    return name == ancestor or name.startswith(ancestor + sep)


def parent(name: str, sep: str) -> str | None:
    head, found, _ = name.rpartition(sep)
    return head if found else None


def ancestors(name: str, sep: str) -> list[str]:
    """`a.b.c` -> `a`, `a.b`, `a.b.c`: shortest first, the name itself last."""
    parts = name.split(sep)
    return [sep.join(parts[: i + 1]) for i in range(len(parts))]


def last(name: str, sep: str) -> str:
    return name.rpartition(sep)[2]


def truncate(name: str, depth: int, sep: str) -> str:
    return sep.join(name.split(sep)[:depth])


def stripped_source_root(model: Model) -> str | None:
    """The directory the TypeScript extractor stripped from the ids, read back off the model.

    Ids are the file path below the source root, prefixed by the project, so what the
    extractor stripped is whatever each `file` has that its id does not. `""` means the ids
    start at the repo; `None` means Python, or files that disagree.
    """
    if model.language != "typescript":
        return None
    sep, prefix = model.separator, model.project + model.separator
    roots = set()
    for node in model.nodes:
        if node.kind != "module" or not node.file or not node.id.startswith(prefix):
            continue
        below = node.id[len(prefix) :]
        roots.add(node.file[: -len(below)].strip(sep) if node.file.endswith(below) else "")
    return roots.pop() if len(roots) == 1 else None
