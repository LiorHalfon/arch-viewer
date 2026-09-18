"""The Node half: what `typescript.mjs` reports for the fixture project (ADR 0010)."""

import json
import subprocess

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
def test_a_wrapped_import_is_recorded_whole_not_by_its_first_line(facts):
    button = imports_of(facts, "components/Button.tsx")["@tanstack/react-query"]

    assert (button["line"], button["text"]) == (
        1,
        'import { useMutation, useQuery, } from "@tanstack/react-query";',
    )


@requires_typescript
def test_a_pathological_statement_is_truncated(tmp_path):
    (tmp_path / "node_modules").symlink_to(TS_SAMPLE / "node_modules")
    (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["*.ts"]}))
    names = ",\n".join(f"  name{i} as renamed{i}" for i in range(40))
    (tmp_path / "a.ts").write_text(f"import {{\n{names},\n}} from './b';\n")

    text = read_facts(tmp_path, tmp_path / "tsconfig.json")["files"][0]["imports"][0]["text"]

    assert len(text) == 200
    assert text.startswith("import { name0 as renamed0, name1 as renamed1,")
    assert text.endswith("…")


@requires_typescript
def test_a_referenced_sibling_package_outside_the_repo_is_not_a_file_of_this_one(tmp_path):
    (tmp_path / "core" / "src").mkdir(parents=True)
    (tmp_path / "core" / "src" / "x.ts").write_text("export const x = 1;\n")
    (tmp_path / "core" / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"composite": True}, "include": ["src"]})
    )
    app = tmp_path / "app"
    (app / "src").mkdir(parents=True)
    (app / "node_modules").symlink_to(TS_SAMPLE / "node_modules")
    (app / "src" / "a.ts").write_text(
        'import { x } from "../../core/src/x";\nexport const a = x;\n'
    )
    (app / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"composite": True},
                "include": ["src"],
                "references": [{"path": "../core"}],
            }
        )
    )

    facts = read_facts(app, app / "tsconfig.json")

    assert [f["file"] for f in facts["files"]] == ["src/a.ts"]
    assert facts["files"][0]["imports"][0]["resolved"] == "../core/src/x.ts"


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


@requires_node
def test_a_missing_repo_is_one_line_not_a_stack_trace(tmp_path):
    missing = tmp_path / "gone"

    with pytest.raises(ExtractionError, match="no such directory") as error:
        read_facts(missing, missing / "tsconfig.json")

    assert "\n" not in str(error.value)


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


def test_a_wedged_node_run_times_out_instead_of_hanging(monkeypatch, tmp_path):
    monkeypatch.setattr(typescript.shutil, "which", lambda _: "/usr/bin/node")

    def hang(*args, **kwargs):
        assert kwargs["timeout"] == typescript.TIMEOUT
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(typescript.subprocess, "run", hang)

    with pytest.raises(ExtractionError, match=r"did not finish within 120s"):
        read_facts(tmp_path, tmp_path / "tsconfig.json")
