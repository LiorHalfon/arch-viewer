"""Check one scope: a package with its own rules file for its children (spec M12)."""

from __future__ import annotations

from dataclasses import replace

from archview.model.filter import scoped_model
from archview.model.graph import Model
from archview.rules.check import Notice, Report, check
from archview.rules.config import Config


def check_scope(model: Model, scope: str, config: Config, in_workspace: bool = False) -> Report:
    """`check()` on the model cut down to `scope`, plus a notice for each literal
    `forbidden` target that is not a child of the scope (it can never fire there)."""
    report = check(scoped_model(model, scope), config, in_workspace)
    dead = [
        Notice(
            "unknown_component",
            f"[{config.table}.forbidden] names {f.target!r}, which is not a child of {scope}; "
            "imports that leave a nested scope are checked by the rules above it",
        )
        for f in config.all_forbidden()
        if f.origin == "forbidden" and f.target not in report.components
    ]
    return replace(report, warnings=tuple(dict.fromkeys((*report.warnings, *dead))))
