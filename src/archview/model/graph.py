"""The language-agnostic model: a tree of nodes plus the imports between them.

Nothing in here knows about Python; an extractor for another language produces
the same shapes (requirement A13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["package", "module"]


@dataclass(frozen=True, slots=True)
class Node:
    """One package or module. `parent` is None for the project root."""

    id: str
    parent: str | None
    kind: Kind
    file: str | None = None


@dataclass(frozen=True, slots=True)
class Import:
    """One import statement, attributed to the module that contains it."""

    importer: str
    imported: str
    file: str
    line: int
    text: str


@dataclass(frozen=True, slots=True)
class Model:
    """Everything an extractor produces; every view is derived from this."""

    project: str
    nodes: tuple[Node, ...]
    imports: tuple[Import, ...]
    language: str = "python"
