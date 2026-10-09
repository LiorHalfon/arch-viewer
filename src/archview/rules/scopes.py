"""Check one scope: a package with its own rules file for its children (spec M12)."""

from __future__ import annotations

from dataclasses import replace

from archview.model.filter import scoped_model
from archview.model.graph import Model
from archview.rules.check import Notice, Report, check
from archview.rules.config import Config
from archview.rules.qualified import owner


def check_scope(model: Model, scope: str, config: Config, in_workspace: bool = False) -> Report:
    """`check()` on the model cut down to `scope`, plus a notice for each literal
    `forbidden` target that is not a child of the scope (it can never fire there).
    A qualified target (`core.desk`) is a part of a child; `check()` has placed it.
    A missing `allowed` table points at `init --root` rather than at `init`."""
    report = check(scoped_model(model, scope), config, in_workspace)
    own = [_for_scope(notice, scope) for notice in report.warnings]
    dead = [
        Notice(
            "unknown_component",
            f"[{config.table}.forbidden] names {f.target!r}, which is not a child of {scope}; "
            "imports that leave a nested scope are checked by the rules above it",
        )
        for f in config.all_forbidden()
        if f.origin == "forbidden"
        and f.target not in report.components
        and owner(f.target) not in report.components
    ]
    return replace(report, warnings=tuple(dict.fromkeys((*own, *dead))))


def _for_scope(notice: Notice, scope: str) -> Notice:
    """`check()`'s `no_rules` notice points at `archview init`, which writes the root
    file; a nested file comes from `init --root`."""
    if notice.kind != "no_rules":
        return notice
    command = f"`archview init --root {scope}`"
    return replace(notice, message=notice.message.replace("`archview init`", command))
