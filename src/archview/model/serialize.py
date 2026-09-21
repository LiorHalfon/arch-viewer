"""Model <-> JSON (requirement A12).

The output carries no timestamp and no machine-specific paths: the same source
must produce byte-identical JSON on every run and on every machine (N1).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from archview.model.graph import ExtractionWarning, Import, Model, Node
from archview.model.view import View

SCHEMA_VERSION = 4
SCHEMA = Path(__file__).with_name("schema.json")


def model_to_dict(model: Model) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "language": model.language,
        "separator": model.separator,
        "project": model.project,
        "nodes": [asdict(n) for n in model.nodes],
        "imports": [asdict(i) for i in model.imports],
        "warnings": [asdict(w) for w in model.warnings],
    }


def model_from_dict(data: dict[str, Any]) -> Model:
    if data.get("schema") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported model schema {data.get('schema')!r}; "
            f"this archview reads schema {SCHEMA_VERSION}"
        )
    return Model(
        project=data["project"],
        language=data["language"],
        separator=data["separator"],
        nodes=tuple(Node(**n) for n in data["nodes"]),
        imports=tuple(Import(**i) for i in data["imports"]),
        warnings=tuple(ExtractionWarning(**w) for w in data["warnings"]),
    )


def dumps(model: Model) -> str:
    return json.dumps(model_to_dict(model), indent=2) + "\n"


def view_to_dict(view: View) -> dict[str, Any]:
    """The derived view for one root - what `archview graph --json` prints."""
    return {
        "root": view.root,
        "nodes": [asdict(n) for n in view.nodes],
        "edges": [
            {
                "source": e.source,
                "target": e.target,
                "count": e.count,
                "in_cycle": e.in_cycle,
                "abstract": e.abstract,
                "type_checking": e.type_checking,
                "imports": [asdict(i) for i in e.imports],
            }
            for e in view.edges
        ],
        "cycles": [list(c) for c in view.cycles],
    }
