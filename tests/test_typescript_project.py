"""A TypeScript project end to end: language selection, the CLI, errors (M6)."""

import json

import pytest

from archview.cli import main
from archview.model.filter import without_tests
from archview.model.serialize import SCHEMA, model_to_dict
from archview.model.view import build_view
from archview.project import ProjectError, open_project, project_report
from tests.typescript_support import TS_SAMPLE, requires_typescript


@pytest.fixture(scope="module")
def project():
    if not (TS_SAMPLE / "node_modules" / "typescript").is_dir():
        pytest.skip("run npm ci --prefix tests/fixtures/ts-sample")
    return open_project(TS_SAMPLE)


@requires_typescript
def test_a_root_tsconfig_selects_the_typescript_extractor(project):
    model = project.model

    assert (project.package, model.language, model.separator) == ("ts-sample", "typescript", "/")
    assert sorted(n.id for n in model.nodes if n.parent == "ts-sample") == [
        "ts-sample/app",
        "ts-sample/components",
        "ts-sample/domain",
        "ts-sample/services",
        "ts-sample/utils",
    ]
    assert [n.id for n in model.nodes if n.kind == "external"] == ["@tanstack/react-query", "react"]
    assert {(n.id, n.kind) for n in model.nodes} >= {
        ("ts-sample/components/Transitions/Transitions", "package"),
        ("ts-sample/components/Transitions/Transitions.tsx", "module"),
        ("ts-sample/utils/legacy.js", "module"),
    }


@requires_typescript
def test_warnings_views_cycles_and_test_filtering(project):
    model = project.model

    assert [(w.kind, w.module, w.target) for w in model.warnings] == [
        ("dynamic_import", "ts-sample/app/index.tsx", None),
        ("unresolved_import", "ts-sample/utils/format.ts", "@/utils/missing"),
    ]
    assert build_view(model, "ts-sample").cycles == (("ts-sample/domain", "ts-sample/services"),)
    hidden = {n.id for n in model.nodes} - {n.id for n in without_tests(model).nodes}
    assert hidden == {
        "ts-sample/services/__mocks__",
        "ts-sample/services/__mocks__/pricing.ts",
        "ts-sample/services/pricing.test.ts",
    }


@requires_typescript
def test_the_typescript_model_matches_the_published_schema(project):
    from jsonschema import Draft202012Validator

    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(model_to_dict(project.model))


@requires_typescript
def test_graph_why_and_init_work_on_the_fixture(capsys):
    assert main(["graph", str(TS_SAMPLE), "--root", "ts-sample/domain", "--json"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert [n["name"] for n in view["nodes"]] == ["Repository.ts", "order.ts", "types.ts"]

    assert main(["why", "domain", "services", str(TS_SAMPLE)]) == 0
    assert "domain/order.ts" in capsys.readouterr().out

    assert main(["init", str(TS_SAMPLE), "--stdout"]) == 0
    rules = capsys.readouterr().out
    assert 'package = "ts-sample"' in rules
    assert 'language = "typescript"' in rules
    assert 'domain = ["services"]' in rules
    assert "source_roots" not in rules  # the fixture has no src/ layout to pin


@requires_typescript
def test_init_pins_the_inferred_source_root_of_a_src_layout_project(tmp_path, capsys):
    (tmp_path / "node_modules").symlink_to(TS_SAMPLE / "node_modules")
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "package.json").write_text(json.dumps({"name": "@acme/proj"}))
    (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["src"]}))
    (tmp_path / "src" / "api" / "a.ts").write_text("export const a = 1;\n")

    assert main(["init", str(tmp_path), "--stdout"]) == 0
    rules = capsys.readouterr().out

    assert 'package = "proj"' in rules
    assert 'source_roots = ["src"]' in rules


@requires_typescript
def test_a_nested_rules_file_in_a_src_layout_project(tmp_path):
    """The ids start below `src/`, so the scope's directory is found through the source
    root the extractor stripped."""
    (tmp_path / "node_modules").symlink_to(TS_SAMPLE / "node_modules")
    (tmp_path / "src" / "feat" / "a").mkdir(parents=True)
    (tmp_path / "src" / "feat" / "b").mkdir(parents=True)
    (tmp_path / "package.json").write_text(json.dumps({"name": "@acme/proj"}))
    (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["src"]}))
    (tmp_path / "src" / "feat" / "a" / "x.ts").write_text(
        'import { y } from "../b/y";\nexport const x = y;\n'
    )
    (tmp_path / "src" / "feat" / "b" / "y.ts").write_text("export const y = 1;\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "proj"\n[archview.allowed]\nfeat = []\n'
    )
    (tmp_path / "src" / "feat" / "archview.toml").write_text("[archview.allowed]\na = []\nb = []\n")

    report = project_report(open_project(tmp_path))

    assert [shown for shown, _ in report.scopes] == ["src/feat/archview.toml"]
    scope = report.scopes[0][1]
    assert scope.project == "proj/feat"
    assert [(p.kind, p.components) for p in scope.problems] == [("not_allowed", ("a", "b"))]


@requires_typescript
def test_a_repo_level_source_root_skips_its_own_rules_and_hidden_directories(tmp_path):
    """With the ids starting at the repo, the root rules file sits in the package
    directory and is the one in use, so nothing is said about it; node_modules and dot
    directories are never searched (Review Focus 5)."""
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "typescript").symlink_to(TS_SAMPLE / "node_modules" / "typescript")
    (tmp_path / "node_modules" / "x" / "archview.toml").write_text("[archview.allowed]\n")
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "archview.toml").write_text("[archview.allowed]\n")
    (tmp_path / "api").mkdir()
    (tmp_path / "core" / "b").mkdir(parents=True)
    (tmp_path / "core" / "c").mkdir()
    (tmp_path / "package.json").write_text(json.dumps({"name": "@acme/proj"}))
    (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["api", "core"]}))
    (tmp_path / "api" / "a.ts").write_text(
        'import { y } from "../core/b/y";\nexport const a = y;\n'
    )
    (tmp_path / "core" / "b" / "y.ts").write_text("export const y = 1;\n")
    (tmp_path / "core" / "c" / "z.ts").write_text("export const z = 1;\n")
    (tmp_path / "archview.toml").write_text(
        '[archview]\npackage = "proj"\n[archview.allowed]\napi = ["core"]\ncore = []\n'
    )
    (tmp_path / "core" / "archview.toml").write_text("[archview.allowed]\nb = []\nc = []\n")

    report = project_report(open_project(tmp_path))

    assert [w for w in report.warnings if w.kind == "unchecked_rules_file"] == []
    assert [shown for shown, _ in report.scopes] == ["core/archview.toml"]
    assert not report.failed


def test_a_missing_tsconfig_lists_the_ones_found(tmp_path):
    (tmp_path / "packages" / "core").mkdir(parents=True)
    (tmp_path / "packages" / "core" / "tsconfig.json").write_text("{}")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "tsconfig.json").write_text("{}")

    with pytest.raises(
        ProjectError, match=r"no tsconfig\.json in .*found packages/core/tsconfig\.json"
    ):
        open_project(tmp_path, language="typescript")


def test_python_stays_the_default_without_a_tsconfig(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")

    assert open_project(tmp_path).model.language == "python"
