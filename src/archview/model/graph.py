"""The language-agnostic model: a tree of nodes plus the imports between them.

Nothing in here knows about Python; an extractor for another language produces
the same shapes (requirement A13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["package", "module", "external"]


@dataclass(frozen=True, slots=True)
class Node:
    """One package or module, or an external package squashed into one node.

    `parent` is None for the project root and for externals. `abstract` means the
    module defines an abstraction for other code to depend on (A9).
    """

    id: str
    parent: str | None
    kind: Kind
    file: str | None = None
    abstract: bool = False


@dataclass(frozen=True, slots=True)
class Import:
    """One import statement, attributed to the module that contains it."""

    importer: str
    imported: str
    file: str
    line: int
    text: str
    type_checking: bool = False
    lazy: bool = False


@dataclass(frozen=True, slots=True)
class ExtractionWarning:
    """Something the extractor saw but could not turn into an import (A5)."""

    kind: str
    module: str
    file: str
    line: int
    text: str
    target: str | None = None


@dataclass(frozen=True, slots=True)
class Model:
    """Everything an extractor produces; every view is derived from this."""

    project: str
    nodes: tuple[Node, ...]
    imports: tuple[Import, ...]
    language: str = "python"
    warnings: tuple[ExtractionWarning, ...] = ()
