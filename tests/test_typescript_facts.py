"""The Node half: what `typescript.mjs` reports for the fixture project (ADR 0010)."""

import json

import pytest

from archview.extract import typescript
from archview.extract.typescript import ExtractionError, read_facts
from tests.typescript_support import TS_SAMPLE, requires_node, requires_typescript


@pytest.fixture(scope="module")
def facts():
    if not (TS_SAMPLE / "node_modules" / "typescript").is_dir():
        pytest.skip("run npm ci --prefix tests/fixtures/ts-sample")
    return read_facts(TS_SAMPLE, TS_SAMPLE / "tsconfig.json")


def imports_of(facts, file):
    return {
        i["specifier"]: i for i in next(f for f in facts["files"] if f["file"] == file)["imports"]
    }


@requires_typescript
def test_lists_the_files_of_every_referenced_project_sorted(facts):
    files = [f["file"] for f in facts["files"]]

    assert files == sorted(files)
    assert set(files) == {
        "app/index.tsx",
        "app/screens/Home.tsx",
        "app/screens/Home.web.tsx",
        "components/Button.tsx",
        "components/Transitions/Transitions.tsx",
        "components/Transitions/Transitions/Fade.tsx",
        "components/index.ts",
        "domain/Repository.ts",
        "domain/order.ts",
        "domain/types.ts",
        "services/__mocks__/pricing.ts",
        "services/pricing.test.ts",
        "services/pricing.ts",
        "utils/format.ts",
        "vite.config.ts",
    }


@requires_typescript
def test_resolves_paths_aliases_barrels_and_same_named_directories(facts):
    assert (
        imports_of(facts, "domain/order.ts")["@/services/pricing"]["resolved"]
        == "services/pricing.ts"
    )
    assert imports_of(facts, "app/index.tsx")["@/components"]["resolved"] == "components/index.ts"
    assert (
        imports_of(facts, "components/Transitions/Transitions.tsx")["./Transitions/Fade"][
            "resolved"
        ]
        == "components/Transitions/Transitions/Fade.tsx"
    )
    assert (
        imports_of(facts, "app/screens/Home.web.tsx")["./Home"]["resolved"]
        == "app/screens/Home.tsx"
    )


@requires_typescript
def test_flags_type_only_lazy_and_dynamic_imports(facts):
    home = imports_of(facts, "app/screens/Home.tsx")
    app = imports_of(facts, "app/index.tsx")
    button = imports_of(facts, "components/Button.tsx")

    assert (home["@/domain/types"]["type_only"], home["@/domain/order"]["type_only"]) == (
        True,
        False,
    )
    assert (app["@/app/screens/Home"]["lazy"], app["@/app/screens/Home"]["resolved"]) == (
        True,
        "app/screens/Home.tsx",
    )
    assert app[None]["dynamic"] is True
    assert (button["../utils/legacy.js"]["lazy"], button["../utils/legacy.js"]["resolved"]) == (
        True,
        "utils/legacy.js",
    )
    assert button["@tanstack/react-query"]["lazy"] is False


@requires_typescript
def test_marks_builtins_and_unresolved_aliases(facts):
    fmt = imports_of(facts, "utils/format.ts")
    button = imports_of(facts, "components/Button.tsx")

    assert (fmt["fs"]["builtin"], fmt["node:path"]["builtin"]) == (True, True)
    assert (fmt["@/utils/missing"]["resolved"], fmt["@/utils/missing"]["alias"]) == (None, True)
    assert (button["@/assets/icon.png"]["resolved"], button["@/assets/icon.png"]["alias"]) == (
        None,
        True,
    )
    assert (
        button["@tanstack/react-query"]["resolved"],
        button["@tanstack/react-query"]["alias"],
    ) == (
        None,
        False,
    )


@requires_typescript
def test_records_the_line_and_its_text(facts):
    order = imports_of(facts, "domain/order.ts")["@/services/pricing"]

    assert (order["line"], order["text"]) == (2, 'import { discount } from "@/services/pricing";')


@requires_typescript
def test_abstract_means_an_abstract_class_or_only_type_exports(facts):
    abstract = {f["file"]: f["abstract"] for f in facts["files"]}

    assert abstract["domain/types.ts"] is True
    assert abstract["domain/Repository.ts"] is True
    assert abstract["domain/order.ts"] is False
    assert abstract["components/Button.tsx"] is False


@requires_node
def test_a_repo_without_typescript_installed_says_to_run_npm_install(tmp_path):
    (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["*.ts"]}))
    (tmp_path / "a.ts").write_text("export const a = 1;\n")

    with pytest.raises(ExtractionError, match=r"typescript not found in .*; run npm install"):
        read_facts(tmp_path, tmp_path / "tsconfig.json")


@requires_typescript
def test_a_broken_extends_is_an_error_not_a_quiet_fallback(tmp_path):
    (tmp_path / "node_modules").symlink_to(TS_SAMPLE / "node_modules")
    (tmp_path / "tsconfig.json").write_text(json.dumps({"extends": "./missing.json"}))
    (tmp_path / "a.ts").write_text("export const a = 1;\n")

    with pytest.raises(ExtractionError, match=r"tsconfig\.json: .*missing\.json"):
        read_facts(tmp_path, tmp_path / "tsconfig.json")


def test_no_node_on_the_path_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(typescript.shutil, "which", lambda _: None)

    with pytest.raises(ExtractionError, match="node not found on PATH"):
        read_facts(tmp_path, tmp_path / "tsconfig.json")
