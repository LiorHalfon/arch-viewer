"""One `ast` pass per file for what grimp does not tell us (ADR 0002).

- the context of every import statement: under `if TYPE_CHECKING:` and/or inside a
  function (lazy), keyed by the statement's first line;
- whether the module defines an abstraction (`Protocol`, `ABC`, `ABCMeta`,
  `@abstractmethod`) - requirement A9;
- dynamic imports (`importlib.import_module(...)`, `__import__(...)`) - requirement A5.

The source is parsed, never executed (N2).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

ABSTRACT_BASES = frozenset({"Protocol", "ABC"})


@dataclass(frozen=True, slots=True)
class DynamicImport:
    line: int
    text: str
    target: str | None


@dataclass(slots=True)
class FileFacts:
    contexts: dict[int, set[str]] = field(default_factory=dict)
    abstract: bool = False
    dynamic: tuple[DynamicImport, ...] = ()

    def flags(self, line: int) -> set[str]:
        return set(self.contexts.get(line, ()))


def _name(node: ast.AST) -> str | None:
    """`X`, `a.X` and `X[T]` all name `X`."""
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_abstract_class(node: ast.ClassDef) -> bool:
    if any(_name(base) in ABSTRACT_BASES for base in node.bases):
        return True
    if any(k.arg == "metaclass" and _name(k.value) == "ABCMeta" for k in node.keywords):
        return True
    return any(
        isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(_name(d) == "abstractmethod" for d in item.decorator_list)
        for item in node.body
    )


def _dynamic_target(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def _is_dynamic_import(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in ("__import__", "import_module")
    return isinstance(func, ast.Attribute) and func.attr == "import_module"


class _Scanner(ast.NodeVisitor):
    def __init__(self, source: str):
        self.source = source
        self.facts = FileFacts()
        self.dynamic: list[DynamicImport] = []
        self.stack: list[str] = []

    def _import(self, node: ast.Import | ast.ImportFrom) -> None:
        self.facts.contexts.setdefault(node.lineno, set()).update(self.stack)

    visit_Import = _import
    visit_ImportFrom = _import

    def _function(self, node: ast.AST) -> None:
        self.stack.append("lazy")
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function
    visit_Lambda = _function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if _is_abstract_class(node):
            self.facts.abstract = True
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        guarded = _name(node.test) == "TYPE_CHECKING"
        if guarded:
            self.stack.append("type_checking")
        for child in node.body:
            self.visit(child)
        if guarded:
            self.stack.pop()
        for child in node.orelse:
            self.visit(child)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_dynamic_import(node):
            text = ast.get_source_segment(self.source, node) or ""
            self.dynamic.append(DynamicImport(node.lineno, text, _dynamic_target(node)))
        self.generic_visit(node)


def scan(source: str) -> FileFacts:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return FileFacts()
    scanner = _Scanner(source)
    scanner.visit(tree)
    scanner.facts.dynamic = tuple(sorted(scanner.dynamic, key=lambda d: d.line))
    return scanner.facts
