"""The viewer's HTTP API (V1-V6, V9, V13)."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archview.server.app import create_app
from archview.server.workspace import Workspace

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(FIXTURES / "sample", tmp_path / "sample")
    return tmp_path


@pytest.fixture
def client(repo):
    return TestClient(create_app(Workspace(repo)))


def test_serves_the_page_and_its_vendored_scripts(client):
    page = client.get("/")

    assert page.status_code == 200
    assert '<script src="/ui/app.js"></script>' in page.text
    assert client.get("/ui/vendor/viz-global.js").status_code == 200
    assert client.get("/ui/vendor/highlight.min.js").status_code == 200


def test_summarises_the_project(client, repo):
    summary = client.get("/api/project").json()

    assert {k: summary[k] for k in ("project", "repo", "rules", "modules", "imports")} == {
        "project": "sample",
        "repo": repo.name,
        "rules": None,
        "modules": 11,
        "imports": 10,
    }
    assert [w["kind"] for w in summary["warnings"]] == ["dynamic_import"]


def test_the_top_view_carries_nodes_edges_cycles_and_dot(client):
    view = client.get("/api/view").json()

    assert view["root"] == "sample"
    assert view["parent"] is None
    assert [n["name"] for n in view["nodes"]] == ["api", "domain", "infra", "services"]
    assert all(n["has_children"] for n in view["nodes"])
    assert view["cycles"] == [["sample.infra", "sample.services"]]
    assert view["dot"].startswith('digraph "sample" {')


def test_marks_packages_with_a_cycle_inside(repo):
    (repo / "sample" / "infra" / "cache.py").write_text("from sample.infra import db\n")
    (repo / "sample" / "infra" / "db.py").write_text("from sample.infra import cache\n")
    client = TestClient(create_app(Workspace(repo)))

    view = client.get("/api/view").json()

    assert [n["name"] for n in view["nodes"] if n["tangled"]] == ["infra"]
    assert 'class="package tangled' in view["dot"]


def test_drills_down_and_knows_the_way_back(client):
    view = client.get("/api/view", params={"root": "sample.infra"}).json()

    assert view["parent"] == "sample"
    assert [(n["name"], n["has_children"]) for n in view["nodes"]] == [
        ("cache", False),
        ("db", False),
    ]


def test_a_module_or_unknown_root_is_not_a_view(client):
    assert client.get("/api/view", params={"root": "sample.infra.db"}).status_code == 404
    assert client.get("/api/view", params={"root": "nope"}).status_code == 404


def test_serves_a_modules_source_with_its_project_imports(client):
    source = client.get("/api/source", params={"module": "sample.api.routes"}).json()

    assert source["file"] == "sample/api/routes.py"
    assert source["text"].startswith('"""Top of the stack')
    assert [(i["line"], i["imported"]) for i in source["imports"]] == [
        (8, "grimp"),
        (10, "sample.domain"),
        (14, "sample.infra.db"),
        (11, "sample.services.pricing"),
    ]


def test_only_serves_files_the_model_knows(client):
    assert client.get("/api/source", params={"module": "../../etc/passwd"}).status_code == 404


def test_reanalyze_picks_up_new_code(client, repo):
    (repo / "sample" / "reports").mkdir()
    (repo / "sample" / "reports" / "__init__.py").write_text("")
    (repo / "sample" / "reports" / "sales.py").write_text("from sample.api import routes\n")
    client.get("/api/view")

    summary = client.post("/api/reanalyze").json()
    view = client.get("/api/view").json()

    assert summary["modules"] == 13
    assert "reports" in [n["name"] for n in view["nodes"]]
