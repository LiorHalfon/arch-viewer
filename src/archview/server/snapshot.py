"""The viewer without a server (V21, ADR 0022).

Every answer the UI can ask one project for, baked in advance, so the viewer runs as a
static site: the public demo on GitHub Pages is the pizzeria built this way.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from archview.server.state import NotFound, ViewerState

SETTINGS = [(False, False), (True, False), (False, True), (True, True)]  # externals, hide_tests


def key(endpoint: str, params: dict[str, str]) -> str:
    """`view?hide_tests=true&root=x`: the endpoint and its parameters sorted by name,
    unencoded, so Python and the browser agree however each percent-encodes.
    snapshot.js builds the same key from a request path."""
    query = "&".join(f"{name}={value}" for name, value in sorted(params.items()))
    return f"{endpoint}?{query}" if query else endpoint


def _flags(externals: bool, hide_tests: bool) -> dict[str, str]:
    """The options as the UI sends them: present, as "true", only when on."""
    flags = {"externals": externals, "hide_tests": hide_tests}
    return {name: "true" for name, on in flags.items() if on}


def answers(state: ViewerState) -> dict[str, Any]:
    """The summary, the check, and for every package a view and both exports under
    each Hide tests and third-party setting, its tree with and without tests, and the
    source of every file."""
    if state.workspace is not None:
        raise ValueError("a workspace snapshot is not supported")
    nodes = state.project.model.nodes
    roots = sorted({n.parent for n in nodes if n.parent})
    baked: dict[str, Any] = {"project": state.summary()}
    with suppress(NotFound):  # no rules file: the UI hides the Rules button and never asks
        baked["check"] = state.check()
    for root in roots:
        for externals, hide_tests in SETTINGS:
            q = {"root": root, **_flags(externals, hide_tests)}
            baked[key("view", q)] = state.view(root, externals, hide_tests)
            for fmt in ("dot", "mermaid"):
                baked[key("export", {**q, "format": fmt})] = state.export(
                    root, fmt, externals, hide_tests
                )
        for hide_tests in (False, True):
            q = {"root": root, **_flags(False, hide_tests)}
            baked[key("tree", q)] = state.tree(root, hide_tests)
    for node in nodes:
        if node.file:
            baked[key("source", {"module": node.id})] = state.source(node.id)
    return dict(sorted(baked.items()))
