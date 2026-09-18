"""A TypeScript project end to end: language selection, the CLI, errors (M6)."""

import json

import pytest

from archview.cli import main
from archview.model.filter import without_tests
from archview.model.serialize import SCHEMA, model_to_dict
from archview.model.view import build_view
from archview.project import ProjectError, open_project
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
