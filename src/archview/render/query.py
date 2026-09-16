"""Render the agent queries as terse text or JSON (requirement G1, ADR 0009)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from archview.model.graph import Import
from archview.model.query import Cycle, Dependency, Why

EXAMPLES = 10


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _import_lines(imports: Sequence[Import], indent: str) -> list[str]:
    shown = imports[:EXAMPLES]
    width = max((len(f"{i.file}:{i.line}") for i in shown), default=0)
    lines = []
    for i in shown:
        where = f"{i.file}:{i.line}".ljust(width)
        marks = "" if i.imported in i.text else f"  [{i.imported}]"
        marks += "  [TYPE_CHECKING]" if i.type_checking else ""
        marks += "  [lazy]" if i.lazy else ""
        lines.append(f"{indent}{where}  {i.text.strip()}{marks}")
    if len(imports) > EXAMPLES:
        more = len(imports) - EXAMPLES
        lines.append(f"{indent}... and {more} more (--format json lists all)")
    return lines


def why_to_text(answer: Why) -> str:
    head = f"{answer.source} -> {answer.target}"
    if answer.direct:
        lines = [f"{head}: {_plural(len(answer.direct), 'direct import')}"]
        lines += _import_lines(answer.direct, "  ")
    elif answer.chain:
        lines = [f"{head}: no direct import; shortest chain of {len(answer.chain)}"]
        for step in answer.chain:
            lines.append(f"  {step.importer} -> {step.imported}")
            lines += _import_lines([step], "    ")
    else:
        lines = [f"{answer.source} does not depend on {answer.target}"]
    return "\n".join(lines) + "\n"


def why_to_dict(answer: Why) -> dict[str, Any]:
    return {
        "from": answer.source,
        "to": answer.target,
        "found": answer.found,
        "direct": [asdict(i) for i in answer.direct],
        "chain": [asdict(i) for i in answer.chain],
    }


def neighbours_to_text(name: str, found: Sequence[Dependency], outgoing: bool) -> str:
    if not found:
        return f"{name} {'depends on nothing' if outgoing else 'has no dependents'}\n"
    head = f"depends on {len(found)}" if outgoing else f"has {_plural(len(found), 'dependent')}"
    lines = [f"{name} {head}:"]
    for dep in found:
        lines.append(f"  {dep.name}  ({_plural(len(dep.imports), 'import')})")
        lines += _import_lines(dep.imports, "    ")
    return "\n".join(lines) + "\n"


def neighbours_to_dict(name: str, found: Sequence[Dependency], outgoing: bool) -> dict[str, Any]:
    return {
        "name": name,
        "dependencies" if outgoing else "dependents": [
            {"name": d.name, "count": len(d.imports), "imports": [asdict(i) for i in d.imports]}
            for d in found
        ],
    }


def cycles_to_text(cycles: Sequence[Cycle], root: str) -> str:
    if not cycles:
        return f"no cycles under {root}\n"
    lines = [_plural(len(cycles), "cycle")]
    for cycle in cycles:
        lines += ["", f"in {cycle.level}: {' -> '.join(cycle.path)}"]
        for step in cycle.steps:
            lines.append(
                f"  {step.source} -> {step.target}  ({_plural(len(step.imports), 'import')})"
            )
            lines += _import_lines(step.imports, "    ")
        if cycle.missed:
            lines.append(f"  also in this tangle: {', '.join(cycle.missed)}")
    return "\n".join(lines) + "\n"


def cycles_to_dict(cycles: Sequence[Cycle], root: str) -> dict[str, Any]:
    return {
        "root": root,
        "cycles": [
            {
                "level": c.level,
                "members": list(c.members),
                "path": list(c.path),
                "missed": list(c.missed),
                "steps": [
                    {
                        "from": s.source,
                        "to": s.target,
                        "count": len(s.imports),
                        "imports": [asdict(i) for i in s.imports],
                    }
                    for s in c.steps
                ],
            }
            for c in cycles
        ],
    }
