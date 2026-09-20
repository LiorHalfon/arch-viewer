"""The viewer's HTTP API (V1-V6, V9, V13)."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archview.server.app import create_app
from archview.server.state import ViewerState, source_files
from tests.typescript_support import TS_SAMPLE, requires_typescript

FIXTURES = Path(__file__).parent / "fixtures"
WORKSPACE = FIXTURES / "workspace"


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(FIXTURES / "sample", tmp_path / "sample")
    return tmp_path


@pytest.fixture
def workspace_repo(tmp_path):
    """A writable copy of the workspace fixture (core has rules, plugin does not)."""
    shutil.copytree(WORKSPACE, tmp_path, dirs_exist_ok=True)
    return tmp_path


def client_for(path):
    return TestClient(create_app(ViewerState(path)))


@pytest.fixture
def client(repo):
    return TestClient(create_app(ViewerState(repo)))


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
    client = TestClient(create_app(ViewerState(repo)))

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


def test_the_tree_nests_the_subtree_of_a_root_packages_first(client):
    tree = client.get("/api/tree").json()

    def shape(node):
        return (node["name"], node["kind"], [shape(c) for c in node["children"]])

    assert tree["id"] == "sample"
    assert tree["parent"] is None
    assert [shape(c) for c in tree["children"]] == [
        ("api", "package", [("routes", "module", [])]),
        ("domain", "package", [("model", "module", []), ("ports", "module", [])]),
        ("infra", "package", [("cache", "module", []), ("db", "module", [])]),
        ("services", "package", [("pricing", "module", [])]),
    ]


def test_the_tree_of_a_subpackage_knows_its_parent_and_flags(repo):
    (repo / "sample" / "infra" / "cache.py").write_text("from sample.infra import db\n")
    (repo / "sample" / "infra" / "db.py").write_text("from sample.infra import cache\n")
    (repo / "sample" / "infra" / "zz.py").write_text("")
    (repo / "sample" / "infra" / "sub").mkdir()
    (repo / "sample" / "infra" / "sub" / "__init__.py").write_text("")
    (repo / "sample" / "infra" / "sub" / "leaf.py").write_text("")
    client = TestClient(create_app(ViewerState(repo)))

    top = client.get("/api/tree").json()
    infra = client.get("/api/tree", params={"root": "sample.infra"}).json()

    assert [c["name"] for c in top["children"] if c["tangled"]] == ["infra"]
    assert infra["parent"] == "sample"
    assert [(c["name"], c["kind"]) for c in infra["children"]] == [
        ("sub", "package"),
        ("cache", "module"),
        ("db", "module"),
        ("zz", "module"),
    ]
    domain = client.get("/api/tree", params={"root": "sample.domain"}).json()
    assert [c["name"] for c in domain["children"] if c["abstract"]] == ["ports"]


def test_the_tree_can_hide_tests_and_rejects_unknown_roots(repo):
    (repo / "sample" / "tests").mkdir()
    (repo / "sample" / "tests" / "__init__.py").write_text("")
    (repo / "sample" / "tests" / "test_api.py").write_text("from sample.api import routes\n")
    client = TestClient(create_app(ViewerState(repo)))

    def names(**params):
        return [c["name"] for c in client.get("/api/tree", params=params).json()["children"]]

    assert "tests" in names()
    assert "tests" not in names(hide_tests=True)
    assert client.get("/api/tree", params={"root": "sample.infra.db"}).status_code == 404
    assert client.get("/api/tree", params={"root": "nope"}).status_code == 404


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


def rules_with_one_violation(repo):
    from archview.cli import main

    main(["init", str(repo)])
    rules = repo / "archview.toml"
    rules.write_text(rules.read_text().replace('api = ["domain", "services"]', 'api = ["domain"]'))


def test_marks_edges_and_imports_that_break_the_rules(repo, capsys):
    rules_with_one_violation(repo)
    client = TestClient(create_app(ViewerState(repo)))

    view = client.get("/api/view").json()
    summary = client.get("/api/project").json()

    broken = [(e["source"], e["target"]) for e in view["edges"] if e["violation"]]
    assert broken == [("sample.api", "sample.services")]
    assert 'class="violation"' in view["dot"]
    assert (summary["rules"], summary["failing"]) == ("archview.toml", 1)


def test_shows_a_violating_outside_package_without_externals(repo, capsys):
    from archview.cli import main

    main(["init", str(repo)])
    rules = repo / "archview.toml"
    rules.write_text(rules.read_text() + "\n[archview.externals]\napi = []\n")
    client = TestClient(create_app(ViewerState(repo)))

    view = client.get("/api/view").json()

    assert "grimp" in [n["id"] for n in view["nodes"]]
    assert ("sample.api", "grimp") in [(e["source"], e["target"]) for e in view["edges"]]


def test_serves_the_check_report(repo, capsys):
    rules_with_one_violation(repo)
    client = TestClient(create_app(ViewerState(repo)))

    report = client.get("/api/check").json()

    assert [p["kind"] for p in report["problems"] if p["fails"]] == ["not_allowed"]
    assert "domain" in report["metrics"]


def test_check_is_not_found_without_rules(client):
    assert client.get("/api/check").status_code == 404


def test_exports_the_view_as_mermaid_or_dot(client):
    mermaid = client.get("/api/export", params={"format": "mermaid"})
    dot = client.get("/api/export", params={"format": "dot", "root": "sample.infra"})

    assert mermaid.text.startswith("%% archview: sample\nflowchart TB")
    assert dot.text.startswith('digraph "sample.infra"')
    assert client.get("/api/export", params={"format": "png"}).status_code == 404


def test_views_can_show_externals_and_hide_tests(repo):
    (repo / "sample" / "tests").mkdir()
    (repo / "sample" / "tests" / "__init__.py").write_text("")
    (repo / "sample" / "tests" / "test_api.py").write_text("from sample.api import routes\n")
    client = TestClient(create_app(ViewerState(repo)))

    def names(**params):
        return [n["name"] for n in client.get("/api/view", params=params).json()["nodes"]]

    assert "tests" in names()
    assert "tests" not in names(hide_tests=True)
    assert "grimp" in names(externals=True)


def test_does_not_serve_files_outside_the_ui_folder(client):
    assert client.get("/ui/../server/app.py").status_code == 404
    assert client.get("/ui/%2e%2e/server/app.py").status_code == 404


def test_watch_reanalyzes_when_a_file_changes(repo):
    import time

    workspace = ViewerState(repo)
    workspace.watch(interval=0.05)
    first = workspace.generation

    time.sleep(0.2)
    (repo / "sample" / "api" / "views.py").write_text("from sample.domain import model\n")
    deadline = time.monotonic() + 5
    while workspace.generation == first and time.monotonic() < deadline:
        time.sleep(0.05)

    assert workspace.generation > first
    assert "sample.api.views" in {n.id for n in workspace.project.model.nodes}


def test_python_summary_carries_the_language_and_separator(client):
    summary = client.get("/api/project").json()

    assert (summary["language"], summary["separator"]) == ("python", ".")


def test_watching_lists_source_files_outside_node_modules_and_hidden_directories(tmp_path):
    for name in ("a.ts", "src/b.tsx", "node_modules/x/c.ts", ".git/d.ts", "README.md"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("")

    found = source_files(tmp_path, (".ts", ".tsx"))

    assert [p.relative_to(tmp_path).as_posix() for p in found] == ["a.ts", "src/b.tsx"]


@requires_typescript
def test_serves_a_typescript_project(tmp_path):
    repo = tmp_path / "ts-sample"
    shutil.copytree(TS_SAMPLE, repo, ignore=shutil.ignore_patterns("node_modules"))
    (repo / "node_modules").symlink_to(TS_SAMPLE / "node_modules")
    client = TestClient(create_app(ViewerState(repo)))

    summary = client.get("/api/project").json()
    view = client.get("/api/view").json()
    tree = client.get("/api/tree", params={"root": "ts-sample/domain"}).json()

    assert (summary["project"], summary["language"], summary["separator"]) == (
        "ts-sample",
        "typescript",
        "/",
    )
    assert [n["name"] for n in view["nodes"]] == [
        "app",
        "components",
        "domain",
        "services",
        "utils",
    ]
    assert [c["name"] for c in tree["children"]] == ["Repository.ts", "order.ts", "types.ts"]
    assert (
        client.get("/api/source", params={"module": "ts-sample/domain/order.ts"}).status_code == 200
    )


# ---------- workspace mode (M8) ----------


def test_the_api_returns_the_workspace_view_at_the_top():
    client = client_for(WORKSPACE)

    data = client.get("/api/view").json()

    assert sorted(n["id"] for n in data["nodes"]) == ["core", "plugin"]
    assert all(n["kind"] == "package" and n["has_children"] for n in data["nodes"])
    assert data["parent"] is None


def test_the_api_drills_into_a_package():
    client = client_for(WORKSPACE)

    data = client.get("/api/view", params={"package": "core", "root": "core"}).json()

    assert "core.ports" in [n["id"] for n in data["nodes"]]
    assert data["project"] == "core"
    assert data["separator"] == "."


def test_a_packages_own_root_points_back_to_the_workspace():
    client = client_for(WORKSPACE)

    data = client.get("/api/view", params={"package": "core", "root": "core"}).json()

    assert data["parent"] == "workspace"


def test_the_api_reads_a_source_file_from_a_package():
    client = client_for(WORKSPACE)

    body = client.get("/api/source", params={"package": "core", "module": "core.ports"}).json()

    assert "Port" in body["text"]
    assert body["file"].endswith("ports.py")


def test_a_single_package_repo_still_works(repo):
    client = client_for(repo)

    assert client.get("/api/view").json()["nodes"]


def test_an_unknown_package_is_not_found():
    client = client_for(WORKSPACE)

    assert client.get("/api/view", params={"package": "nope", "root": "nope"}).status_code == 404
    assert client.get("/api/source", params={"package": "nope", "module": "x"}).status_code == 404


def test_a_package_param_on_a_non_workspace_repo_is_not_found(client):
    assert (
        client.get("/api/view", params={"package": "sample", "root": "sample"}).status_code == 404
    )


def test_the_workspace_summary_lists_its_packages():
    client = client_for(WORKSPACE)

    summary = client.get("/api/project").json()

    assert summary["workspace"] is True
    assert summary["packages"] == ["core", "plugin"]
    assert summary["project"] == "workspace"


def test_the_api_checks_the_whole_workspace_and_one_package():
    client = client_for(WORKSPACE)

    top = client.get("/api/check").json()
    core = client.get("/api/check", params={"package": "core"}).json()

    assert top["workspace"] == "workspace"
    assert "core" in [p["package"] for p in top["packages"]]
    assert {"model", "ports"} <= core["metrics"].keys()
    assert client.get("/api/check", params={"package": "plugin"}).status_code == 404


def test_the_top_view_marks_a_cross_package_violation(workspace_repo):
    (workspace_repo / "archview.toml").write_text(
        '[archview.workspace]\npackages = ["core", "plugin"]\n\n'
        "[archview.workspace.allowed]\ncore = []\nplugin = []\n"
    )
    client = client_for(workspace_repo)

    view = client.get("/api/view").json()

    broken = [(e["source"], e["target"]) for e in view["edges"] if e["violation"]]
    assert ("plugin", "core") in broken
    assert 'class="violation"' in view["dot"]


def test_watch_watches_every_package_directory(workspace_repo):
    import time

    state = ViewerState(workspace_repo)
    state.watch(interval=0.05)
    first = state.generation

    time.sleep(0.2)
    (workspace_repo / "plugin" / "src" / "plugin" / "extra.py").write_text("")
    deadline = time.monotonic() + 5
    while state.generation == first and time.monotonic() < deadline:
        time.sleep(0.05)

    assert state.generation > first
    view = state.view(root="plugin", package="plugin")
    assert "plugin.extra" in [n["id"] for n in view["nodes"]]
