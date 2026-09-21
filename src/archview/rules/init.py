"""Infer a starter rules file from the dependencies as they are (requirement C6).

`archview init` writes what *is*, so `archview check` passes straight away. The human
then deletes the dependencies that should not exist, and the checker fails until the
code matches the design.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from archview.model.cycles import describe_cycle, find_cycles
from archview.model.graph import Model
from archview.rules.check import (
    checked_imports,
    component_edges,
    component_map,
    present_components,
)
from archview.rules.config import Config

BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _key(name: str) -> str:
    return name if BARE_KEY.match(name) else json.dumps(name)


def _array(values: Iterable[str]) -> str:
    return "[" + ", ".join(json.dumps(v) for v in values) + "]"


def infer_rules(model: Model, config: Config | None = None, externals: bool = False) -> str:
    """The text of an `archview.toml`; keeps package, exclusions and components from `config`.

    `externals` adds an `[archview.externals]` table from today's outside imports,
    for repos that want the freeze-then-delete loop `[archview.allowed]` already offers.
    """
    config = config or Config()
    model = checked_imports(model, config)
    components = component_map(config, model)
    present = present_components(model, components)
    edges = component_edges(model, components)
    cycles = find_cycles(present, edges.internal)

    lines = [
        "# Dependency rules for `archview check`, inferred by `archview init` from the",
        "# imports as they are today. Delete the dependencies that should not exist; the",
        "# check then fails until the code matches. Agents: never edit this file to make",
        "# the check pass - fix the code or ask.",
        "",
        "[archview]",
        f"package = {json.dumps(model.project)}",
    ]
    if model.language != "python":
        lines.append(f"language = {json.dumps(model.language)}")
    if config.tsconfig:
        lines.append(f"tsconfig = {json.dumps(config.tsconfig)}")
    roots = config.source_roots or _inferred_source_roots(model)
    if roots:
        lines.append(f"source_roots = {_array(roots)}")
    lines.append(f"exclude = {_array(config.exclude)}")
    if config.ignored:
        lines.append(f"ignored = {_array(config.ignored)}")
    lines.append("fail_on_violations = true")
    lines.extend(_cycle_setting(cycles))
    lines += ["", "[archview.allowed]"]
    for component in present:
        targets = sorted(t for (s, t) in edges.internal if s == component)
        lines.append(f"{_key(component)} = {_array(targets)}")
    if externals:
        lines += ["", "[archview.externals]"]
        for component in present:
            targets = sorted(t for (s, t) in edges.outside if s == component)
            lines.append(f"{_key(component)} = {_array(targets)}")
    if config.components:
        lines += ["", "[archview.components]"]
        for name, patterns in sorted(config.components.items()):
            lines.append(f"{_key(name)} = {_array(patterns)}")
    return "\n".join(lines) + "\n"


def _inferred_source_roots(model: Model) -> tuple[str, ...]:
    """The directory the TypeScript extractor stripped from the ids, read back off the model.

    Ids are the file path below the source root, prefixed by the project, so what the
    extractor stripped is whatever each `file` has that its id does not. Pinning it keeps
    the component keys stable: without it, one new file at the repo root would re-root
    every id and every key in this file would go stale at once.
    """
    if model.language != "typescript":
        return ()
    sep, prefix = model.separator, model.project + model.separator
    roots = set()
    for node in model.nodes:
        if node.kind != "module" or not node.file or not node.id.startswith(prefix):
            continue
        below = node.id[len(prefix) :]
        roots.add(node.file[: -len(below)].strip(sep) if node.file.endswith(below) else "")
    return (roots.pop(),) if len(roots) == 1 and "" not in roots else ()


def _cycle_setting(cycles: tuple[tuple[str, ...], ...]) -> list[str]:
    if not cycles:
        return ["fail_on_cycles = true"]
    listed = [describe_cycle(cycle) for cycle in cycles]
    return [
        f"# {len(cycles)} component cycle(s) today; set to true once they are gone:",
        *(f"#   {cycle}" for cycle in listed),
        "fail_on_cycles = false",
    ]
