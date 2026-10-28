"""The viewer as a static site (V21, ADR 0022): every answer the UI can ask one project for."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archview.server.app import create_app
from archview.server.snapshot import answers, key, write_site
from archview.server.state import ViewerState

REPO = Path(__file__).parent.parent
PIZZERIA = REPO / "examples" / "pizzeria"
ROOTS = [
    "pizzeria",
    "pizzeria.delivery",
    "pizzeria.kitchen",
    "pizzeria.kitchen.stations",
    "pizzeria.menu",
    "pizzeria.orders",
    "pizzeria.payments",
    "pizzeria.storefront",
]
SETTINGS = [
    {},
    {"externals": "true"},
    {"hide_tests": "true"},
    {"externals": "true", "hide_tests": "true"},
]


@pytest.fixture(scope="module")
def state():
    return ViewerState(PIZZERIA)


@pytest.fixture(scope="module")
def baked(state):
    return answers(state)


def test_a_key_is_the_endpoint_and_its_parameters_sorted_and_unencoded():
    view = key("view", {"root": "pizzeria", "hide_tests": "true"})
    assert view == "view?hide_tests=true&root=pizzeria"
    assert key("source", {"module": "src/a/b.ts"}) == "source?module=src/a/b.ts"
    assert key("project", {}) == "project"


def test_bakes_every_view_and_both_exports_for_every_setting(baked):
    for root in ROOTS:
        for setting in SETTINGS:
            q = {"root": root, **setting}
            assert baked[key("view", q)]["root"] == root
            assert baked[key("export", {**q, "format": "dot"})].startswith("digraph")
            assert "flowchart" in baked[key("export", {**q, "format": "mermaid"})]


def test_bakes_a_tree_per_root_with_and_without_tests(baked):
    for root in ROOTS:
        assert baked[key("tree", {"root": root})]["id"] == root
        assert baked[key("tree", {"root": root, "hide_tests": "true"})]["id"] == root


def test_bakes_the_source_of_every_file_package_inits_included(state, baked):
    files = [n.id for n in state.project.model.nodes if n.file]
    assert len(files) == 23 and "pizzeria.kitchen" in files
    for module in files:
        assert baked[key("source", {"module": module})]["module"] == module


def test_bakes_the_summary_and_the_check_and_nothing_else(baked):
    assert baked["project"]["project"] == "pizzeria"
    assert baked["project"]["watching"] is False
    assert baked["check"]["ok"] is False
    assert len(baked) == 8 * 4 * 3 + 8 * 2 + 23 + 2  # 137
    assert list(baked) == sorted(baked)


def test_an_answer_is_what_the_server_sends(state, baked):
    client = TestClient(create_app(state))
    stations = client.get("/api/view?root=pizzeria.kitchen.stations&hide_tests=true")
    assert baked["view?hide_tests=true&root=pizzeria.kitchen.stations"] == stations.json()
    mermaid = client.get("/api/export?format=mermaid&root=pizzeria")
    assert baked["export?format=mermaid&root=pizzeria"] == mermaid.text


def test_a_workspace_is_not_baked():
    with pytest.raises(ValueError, match="workspace"):
        answers(ViewerState(REPO / "tests" / "fixtures" / "workspace"))


def test_writes_the_page_the_ui_and_the_snapshot(state, tmp_path):
    out = tmp_path / "site"
    write_site(state, out, about="<p>hello</p>")

    page = (out / "index.html").read_text()
    assert '<meta name="archview-snapshot" content="snapshot.json">' in page
    assert '"/ui/' not in page and "'/ui/" not in page
    assert (out / "ui" / "app.js").is_file()
    assert (out / "ui" / "vendor" / "viz-global.js").is_file()
    snapshot = json.loads((out / "snapshot.json").read_text())
    assert snapshot["about"] == "<p>hello</p>"
    assert snapshot["answers"]["project"]["project"] == "pizzeria"


def test_refuses_a_folder_that_already_exists(state, tmp_path):
    with pytest.raises(FileExistsError):
        write_site(state, tmp_path)


def test_every_link_in_the_demo_note_opens_a_baked_view(baked):
    note = (REPO / "scripts" / "pages" / "about.html").read_text()
    roots = re.findall(r'href="#/([^"?]+)"', note)
    assert roots
    for root in roots:
        assert key("view", {"root": root}) in baked
