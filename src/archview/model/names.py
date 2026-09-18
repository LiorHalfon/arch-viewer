"""Hierarchy on node ids: a name, its parent and its ancestors.

Python ids are split by '.', TypeScript ids by '/' (ADR 0010). `sep` is always passed
explicitly - from `Model.separator` - so no caller silently assumes one language.
"""

from __future__ import annotations


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
