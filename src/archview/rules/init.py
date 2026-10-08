"""Infer a starter rules file from the dependencies as they are (requirement C6).

`archview init` writes what *is*, so `archview check` passes straight away. The human
then deletes the dependencies that should not exist, and the checker fails until the
code matches the design. `archview init --root` does the same for the children of one
package, in a nested rules file (M12).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from archview.model.cycles import describe_cycle, find_cycles
from archview.model.filter import scoped_model
from archview.model.graph import Import, Model
from archview.model.names import stripped_source_root
from archview.rules.check import (
    Edges,
    Pair,
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
    present, edges = _today(model, config)

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
    roots = config.source_roots or ((root,) if (root := stripped_source_root(model)) else ())
    if roots:
        lines.append(f"source_roots = {_array(roots)}")
    lines.append(f"exclude = {_array(config.exclude)}")
    if config.type_checking_imports != Config().type_checking_imports:
        # The edges above were inferred with this setting; `check` must read them with it.
        lines.append(f"type_checking_imports = {json.dumps(config.type_checking_imports)}")
    lines += _rule_lines(present, edges, config)
    if externals:
        lines += _edge_table("archview.externals", present, edges.outside)
    lines += _components_table(config)
    return "\n".join(lines) + "\n"


def infer_scope_rules(model: Model, scope: str, config: Config) -> str:
    """The text of the nested `archview.toml` for the package `scope`: the rules between
    its children as they are today.

    `model` is the whole project's; `config` is the nested one, with the keys it takes
    from the root rules set, so the edges written here are the edges `check` reads.
    It keeps `ignored` and `components` from `config`.
    """
    present, edges = _today(scoped_model(model, scope), config)
    lines = [
        f"# Dependency rules between the children of {scope}, inferred by",
        "# `archview init --root` from the imports as they are today. Imports that leave",
        f"# {scope} are checked by the rules above it, not here. Delete the",
        "# dependencies that should not exist; the check then fails until the code matches.",
        "# Agents: never edit this file to make the check pass - fix the code or ask.",
        "",
        "[archview]",
        *_rule_lines(present, edges, config),
        *_components_table(config),
    ]
    return "\n".join(lines) + "\n"


def _today(model: Model, config: Config) -> tuple[tuple[str, ...], Edges]:
    """The components present and the edges between them, as `check` would see them."""
    model = checked_imports(model, config)
    components = component_map(config, model)
    return present_components(model, components), component_edges(model, components)


def _rule_lines(present: tuple[str, ...], edges: Edges, config: Config) -> list[str]:
    """The end of `[archview]` (ignored, the fail flags) and `[archview.allowed]`."""
    lines = [f"ignored = {_array(config.ignored)}"] if config.ignored else []
    lines.append("fail_on_violations = true")
    lines.extend(_cycle_setting(find_cycles(present, edges.internal)))
    return lines + _edge_table("archview.allowed", present, edges.internal)


def _edge_table(table: str, present: tuple[str, ...], edges: dict[Pair, list[Import]]) -> list[str]:
    """One line per present component, listing the targets it imports today."""
    lines = ["", f"[{table}]"]
    for component in present:
        targets = sorted(t for (s, t) in edges if s == component)
        lines.append(f"{_key(component)} = {_array(targets)}")
    return lines


def _components_table(config: Config) -> list[str]:
    if not config.components:
        return []
    lines = ["", "[archview.components]"]
    for name, patterns in sorted(config.components.items()):
        lines.append(f"{_key(name)} = {_array(patterns)}")
    return lines


def _cycle_setting(cycles: tuple[tuple[str, ...], ...]) -> list[str]:
    if not cycles:
        return ["fail_on_cycles = true"]
    listed = [describe_cycle(cycle) for cycle in cycles]
    return [
        f"# {len(cycles)} component cycle(s) today; set to true once they are gone:",
        *(f"#   {cycle}" for cycle in listed),
        "fail_on_cycles = false",
    ]
