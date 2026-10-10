"""`archview check` and `archview init` end to end (C3-C6, MVP acceptance)."""

import json
import shutil
from pathlib import Path

import pytest

from archview.cli import main
from tests.test_golden import check as golden

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(tmp_path):
    """A writable copy of the fixture project."""
    shutil.copytree(FIXTURES / "sample", tmp_path / "sample")
    return tmp_path


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_init_writes_rules_that_the_check_then_passes(repo, capsys):
    code, out, _ = run(capsys, "init", str(repo))
    assert code == 0
    assert "wrote" in out

    code, out, _ = run(capsys, "check", str(repo))

    assert code == 0
    assert "CYCLE infra -> services -> infra" in out  # reported, not failing
    assert "ok: sample, 5 components" in out


def test_init_writes_the_current_dependencies_and_switches_off_existing_cycles(repo, capsys):
    run(capsys, "init", str(repo))

    golden("sample-archview.toml", (repo / "archview.toml").read_text())


def test_removing_one_allowed_dependency_fails_with_file_and_line(repo, capsys):
    run(capsys, "init", str(repo))
    rules = repo / "archview.toml"
    rules.write_text(
        rules.read_text().replace(
            'api = ["domain", "infra", "services"]', 'api = ["domain", "infra"]'
        )
    )

    code, out, _ = run(capsys, "check", str(repo))

    assert code == 1
    assert "VIOLATION api -> services (1 import) not allowed by [archview.allowed.api]" in out
    assert "sample/api/routes.py:11  from sample.services import pricing" in out
    assert out.endswith("1 problem in 5 components. exit 1\n")


def test_json_output_is_stable_and_complete(repo, capsys):
    run(capsys, "init", str(repo))
    rules = repo / "archview.toml"
    rules.write_text(rules.read_text().replace("fail_on_cycles = false", "fail_on_cycles = true"))

    code, first, _ = run(capsys, "check", str(repo), "--format", "json")
    _, second, _ = run(capsys, "check", str(repo), "--format", "json")

    assert code == 1
    assert first == second
    report = json.loads(first)
    assert report["ok"] is False
    [cycle] = report["problems"]
    assert (cycle["kind"], cycle["components"], cycle["from"]) == (
        "cycle",
        ["infra", "services"],
        None,
    )
    golden("sample-check.json", first)


def test_check_without_rules_tells_you_to_run_init(repo, capsys):
    code, _, err = run(capsys, "check", str(repo))

    assert code == 2
    assert "run `archview init` first" in err


def test_init_refuses_to_overwrite_rules_without_force(repo, capsys):
    run(capsys, "init", str(repo))

    code, _, err = run(capsys, "init", str(repo))

    assert code == 2
    assert "--force" in err
    assert run(capsys, "init", str(repo), "--force")[0] == 0


def test_init_can_exclude_files_and_keeps_the_exclusion(repo, capsys):
    run(capsys, "init", str(repo), "--exclude", "**/infra/**")

    text = (repo / "archview.toml").read_text()
    assert 'exclude = ["**/infra/**"]' in text
    assert "infra" not in text.split("[archview.allowed]")[1]
    assert run(capsys, "check", str(repo))[0] == 0


def test_init_force_keeps_type_checking_imports_so_its_rules_pass(tmp_path, capsys):
    """`init` infers the rules with the old setting, so it must write it too: without
    it `check` falls back to "include" and fails on the import `init` skipped (#13)."""
    for path, text in {
        "shop/__init__.py": "",
        "shop/a/__init__.py": "",
        "shop/a/uses.py": (
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from shop.b.core import B\n"
        ),
        "shop/b/__init__.py": "",
        "shop/b/core.py": "class B: ...\n",
        "archview.toml": '[archview]\npackage = "shop"\ntype_checking_imports = "ignore"\n',
    }.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)

    assert run(capsys, "init", str(tmp_path), "--force")[0] == 0

    assert 'type_checking_imports = "ignore"' in (tmp_path / "archview.toml").read_text()
    assert run(capsys, "check", str(tmp_path))[0] == 0


def test_a_broken_rules_file_is_a_usage_error_not_a_failed_check(repo, capsys):
    (repo / "archview.toml").write_text("[archview]\nalowed = {}\n")

    code, _, err = run(capsys, "check", str(repo))

    assert code == 2
    assert "did you mean 'allowed'" in err


def test_check_reads_a_rules_file_given_explicitly(repo, tmp_path, capsys):
    rules = tmp_path / "elsewhere.toml"
    run(capsys, "init", str(repo), "--config", str(rules))

    assert not (repo / "archview.toml").exists()
    assert run(capsys, "check", str(repo), "--config", str(rules))[0] == 0


def test_update_baseline_records_known_problems_so_only_new_ones_fail(repo, capsys):
    run(capsys, "init", str(repo))
    rules = repo / "archview.toml"
    rules.write_text(
        rules.read_text().replace(
            'api = ["domain", "infra", "services"]', 'api = ["domain", "infra"]'
        )
    )
    assert run(capsys, "check", str(repo))[0] == 1

    code, out, _ = run(capsys, "check", str(repo), "--update-baseline")
    assert code == 0
    assert "archview-baseline.json (1 known problems)" in out

    code, out, _ = run(capsys, "check", str(repo))
    assert code == 0
    assert "known: VIOLATION api -> services" in out

    (repo / "sample" / "api" / "views.py").write_text("from sample.services import pricing\n")
    code, out, _ = run(capsys, "check", str(repo))
    assert code == 1
    assert "sample/api/views.py:1" in out
    assert "1 more are in the baseline" in out


def test_metrics_prints_one_row_per_component(repo, capsys):
    code, out, _ = run(capsys, "metrics", str(repo))

    assert code == 0
    assert out.splitlines()[0].split() == ["component", "Ca", "Ce", "I", "A", "D", "zone"]
    assert "domain     4   0   0.00  0.33  0.67  pain" in out


def test_graph_prints_mermaid_with_violations_marked(repo, capsys):
    run(capsys, "init", str(repo))
    rules = repo / "archview.toml"
    rules.write_text(
        rules.read_text().replace(
            'api = ["domain", "infra", "services"]', 'api = ["domain", "infra"]'
        )
    )

    code, out, _ = run(capsys, "graph", str(repo), "--mermaid")

    assert code == 0
    assert "n_sample_api -. 1 ✗ .-> n_sample_services" in out


def test_graph_can_show_external_packages(repo, capsys):
    _, out, _ = run(capsys, "graph", str(repo), "--externals", "--json")

    assert [n["id"] for n in json.loads(out)["nodes"] if n["kind"] == "external"] == ["grimp"]


def test_an_outside_violation_is_reported_with_file_and_line(repo, capsys):
    run(capsys, "init", str(repo))
    rules = repo / "archview.toml"
    rules.write_text(rules.read_text() + "\n[archview.externals]\napi = []\n")

    code, out, _ = run(capsys, "check", str(repo))

    assert code == 1
    assert "OUTSIDE api -> grimp (1 import) not allowed by [archview.externals.api]" in out
    assert "sample/api/routes.py:8  import grimp" in out


def test_an_outside_violation_in_json(repo, capsys):
    run(capsys, "init", str(repo))
    rules = repo / "archview.toml"
    rules.write_text(rules.read_text() + "\n[archview.externals]\napi = []\n")

    code, out, _ = run(capsys, "check", str(repo), "--format", "json")

    assert code == 1
    data = json.loads(out)
    [problem] = [p for p in data["problems"] if p["kind"] == "outside"]
    assert problem["from"] == "api"
    assert problem["to"] == "grimp"
    assert problem["rule"] == "archview.externals.api"
    assert problem["components"] == ["api", "grimp"]
    assert problem["imports"][0]["line"] == 8


def nested_copy(tmp_path: Path) -> Path:
    copy = tmp_path / "nested"
    shutil.copytree(FIXTURES / "nested", copy)
    return copy


def test_check_reports_each_nested_scope_in_its_own_section(tmp_path, capsys):
    code, out, _ = run(capsys, "check", str(nested_copy(tmp_path)))

    assert code == 1
    assert (
        "warning: shop/services/assets/archview.toml is not checked: shop.services.assets "
        "is not a package archview analyses (excluded, or not a package)"
    ) in out
    assert (
        "shop.services (shop/services/archview.toml)  1 problem\n"
        "  VIOLATION print -> users (1 import) not allowed by [archview.allowed.print]"
    ) in out
    assert out.endswith("1 problem in 3 components and 1 nested scope. exit 1\n")
    golden("nested-check.txt", out)


def test_nested_scopes_appear_in_the_json(tmp_path, capsys):
    code, out, _ = run(capsys, "check", str(nested_copy(tmp_path)), "--format", "json")

    assert code == 1
    report = json.loads(out)
    assert report["ok"] is False
    [scope] = report["scopes"]
    assert scope["rules"] == "shop/services/archview.toml"
    assert scope["project"] == "shop.services"
    assert scope["scopes"] == []
    golden("nested-check.json", out)


def test_a_passing_nested_scope_says_ok(tmp_path, capsys):
    copy = nested_copy(tmp_path)
    rules = copy / "shop/services/archview.toml"
    rules.write_text(
        rules.read_text().replace('print = ["pricing"]', 'print = ["pricing", "users"]')
    )

    code, out, _ = run(capsys, "check", str(copy))

    assert code == 0
    assert "shop.services (shop/services/archview.toml)  ok\n" in out
    assert out.endswith("ok: shop, 3 components and 1 nested scope, no failing problems\n")


def test_an_invalid_nested_rules_file_exits_2(tmp_path, capsys):
    copy = nested_copy(tmp_path)
    (copy / "shop/services/archview.toml").write_text("[archview.allowed\n")

    code, _, err = run(capsys, "check", str(copy))

    assert code == 2
    assert "shop/services/archview.toml: not valid TOML" in err


def test_update_baseline_writes_one_baseline_per_scope(tmp_path, capsys):
    copy = nested_copy(tmp_path)

    code, out, _ = run(capsys, "check", str(copy), "--update-baseline")

    assert code == 0
    lines = out.splitlines()
    assert len(lines) == 2
    assert lines[1].endswith("shop/services/archview-baseline.json (1 known problems)")
    assert (copy / "shop/services/archview-baseline.json").is_file()

    code, out, _ = run(capsys, "check", str(copy))
    assert code == 0
    assert "known:" in out


def add_print_scope(copy: Path) -> None:
    """A second depth: `shop.services.print` gets rules for its own children, and one
    violation, `render.pdf` importing `layout.page`."""
    printing = copy / "shop/services/print"
    for child in ("layout", "render"):
        (printing / child).mkdir()
        (printing / child / "__init__.py").write_text("")
    (printing / "layout/page.py").write_text("")
    (printing / "render/pdf.py").write_text("from shop.services.print.layout import page\n")
    (printing / "archview.toml").write_text(
        "[archview.allowed]\nflow = []\nlayout = []\nrender = []\n"
    )


def test_nested_files_at_two_depths_are_checked_apart(tmp_path, capsys):
    copy = nested_copy(tmp_path)
    add_print_scope(copy)

    code, out, _ = run(capsys, "check", str(copy))

    assert code == 1
    outer = out.index("shop.services (shop/services/archview.toml)  1 problem\n")
    inner = out.index("shop.services.print (shop/services/print/archview.toml)  1 problem\n")
    assert outer < inner
    assert "VIOLATION print -> users" in out[outer:inner]
    assert "render -> layout" not in out[outer:inner]
    assert "  VIOLATION render -> layout (1 import)" in out[inner:]
    assert "print -> users" not in out[inner:]
    assert out.endswith("2 problems in 3 components and 2 nested scopes. exit 1\n")

    code, out, _ = run(capsys, "check", str(copy), "--update-baseline")

    assert code == 0
    assert len(out.splitlines()) == 3
    for where in (copy, copy / "shop/services", copy / "shop/services/print"):
        assert (where / "archview-baseline.json").is_file()
    assert run(capsys, "check", str(copy))[0] == 0


def test_init_root_writes_a_nested_rules_file_the_check_then_passes(tmp_path, capsys):
    copy = nested_copy(tmp_path)
    rules = copy / "shop/services/archview.toml"
    rules.unlink()

    code, out, _ = run(capsys, "init", str(copy), "--root", "services")

    assert code == 0
    assert out == f"wrote {rules.resolve()}\n"
    assert 'print = ["pricing", "users"]' in rules.read_text()
    assert run(capsys, "check", str(copy))[0] == 0


def test_init_root_refuses_an_existing_file_and_force_keeps_components_and_ignored(
    tmp_path, capsys
):
    copy = nested_copy(tmp_path)
    rules = copy / "shop/services/archview.toml"
    rules.write_text(
        '[archview]\nignored = ["users"]\n\n'
        '[archview.allowed]\npay = []\nprint = ["pay"]\n\n'
        '[archview.components]\npay = ["shop.services.pricing"]\n'
    )

    code, _, err = run(capsys, "init", str(copy), "--root", "services")
    assert code == 2
    assert "--force" in err

    assert run(capsys, "init", str(copy), "--root", "services", "--force")[0] == 0
    text = rules.read_text()
    assert 'ignored = ["users"]' in text
    assert 'pay = []\nprint = ["pay"]\n' in text
    assert text.endswith('[archview.components]\npay = ["shop.services.pricing"]\n')


def test_init_root_stdout_prints_the_rules_and_leaves_the_file_alone(tmp_path, capsys):
    copy = nested_copy(tmp_path)
    rules = copy / "shop/services/archview.toml"
    before = rules.read_text()

    code, out, _ = run(capsys, "init", str(copy), "--root", "shop.services", "--stdout")

    assert code == 0
    assert out.startswith("# Dependency rules between the children of shop.services,")
    assert rules.read_text() == before


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--root", "services.print.flow"), "shop.services.print.flow is not a package"),
        (("--root", "shop"), "shop is the project"),
        (("--root", "nope"), "no module or package 'nope'"),
        (("--root", "services", "--config", "x.toml"), "--config"),
        (("--root", "services", "--exclude", "x"), "--exclude"),
        (("--root", "services", "--tsconfig", "tsconfig.json"), "--tsconfig"),
        (("--root", "services", "--language", "python"), "--language"),
    ],
)
def test_init_root_usage_errors_exit_2(tmp_path, capsys, args, message):
    copy = nested_copy(tmp_path)

    code, _, err = run(capsys, "init", str(copy), "--force", *args)

    assert code == 2
    assert message in err


def test_init_root_keeps_type_checking_imports_so_its_rules_pass(tmp_path, capsys):
    """The nested file is inferred with the root's setting, which `check` also reads (#13)."""
    copy = nested_copy(tmp_path)
    root = copy / "archview.toml"
    root.write_text(
        root.read_text().replace(
            'package = "shop"', 'package = "shop"\ntype_checking_imports = "ignore"'
        )
    )
    (copy / "shop/services/pricing/types.py").write_text(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from shop.services.users import repo\n"
    )

    assert run(capsys, "init", str(copy), "--root", "services", "--force")[0] == 0

    assert "pricing = []" in (copy / "shop/services/archview.toml").read_text()
    assert run(capsys, "check", str(copy))[0] == 0


def bespoke(tmp_path: Path, rules: str) -> Path:
    """Issue #17's layout: a core with ports, types and desk, and a plugin beside it."""
    for path, text in {
        "src/__init__.py": "",
        "src/bespoke_story/__init__.py": "",
        "src/bespoke_story/ports/__init__.py": "class Port: ...\n",
        "src/bespoke_story/types/__init__.py": "class Kind: ...\n",
        "src/bespoke_story/desk/__init__.py": "",
        "src/bespoke_story/desk/cast.py": "class Cast: ...\n",
        "src/bespoke_openai/__init__.py": "",
        "src/bespoke_openai/language.py": (
            "from src.bespoke_story.ports import Port\n"
            "from src.bespoke_story.types import Kind\n"
            "from src.bespoke_story.desk import cast\n"
        ),
        "archview.toml": '[archview]\npackage = "src"\n\n' + rules,
    }.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    return tmp_path


CONTRACT = """
[archview.allowed]
bespoke_story = []
bespoke_openai = ["bespoke_story.ports", "bespoke_story.types"]
"""


def test_a_qualified_grant_fails_only_the_import_into_another_part(tmp_path, capsys):
    code, out, _ = run(capsys, "check", str(bespoke(tmp_path, CONTRACT)))

    assert code == 1
    assert "has no modules" not in out
    assert (
        "VIOLATION bespoke_openai -> bespoke_story.desk (1 import) not allowed by "
        "[archview.allowed.bespoke_openai]"
    ) in out
    assert "src/bespoke_openai/language.py:3  from src.bespoke_story.desk import cast" in out
    assert "language.py:1" not in out
    assert "bespoke_openai may import only: bespoke_story.ports, bespoke_story.types" in out


def test_a_qualified_forbidden_target_fails_the_check(tmp_path, capsys):
    rules = (
        '[archview.allowed]\nbespoke_story = []\nbespoke_openai = ["bespoke_story"]\n\n'
        '[[archview.forbidden]]\nfrom = "bespoke_openai"\nto = "bespoke_story.desk"\n'
    )

    code, out, _ = run(capsys, "check", str(bespoke(tmp_path, rules)))

    assert code == 1
    assert "FORBIDDEN bespoke_openai -> bespoke_story.desk (1 import)" in out


@pytest.mark.parametrize(
    ("rules", "where", "name"),
    [
        (
            '[archview.allowed]\nbespoke_story = []\nbespoke_openai = ["bespoke_story.portz"]\n',
            "[archview.allowed.bespoke_openai]",
            "bespoke_story.portz",
        ),
        (
            '[[archview.forbidden]]\nfrom = "bespoke_openai"\nto = "bespoke_story.portz"\n',
            "[archview.forbidden]",
            "bespoke_story.portz",
        ),
        (
            '[[archview.forbidden]]\nfrom = "bespoke_storz.desk"\nto = "bespoke_openai"\n',
            "[archview.forbidden]",
            "bespoke_storz.desk",
        ),
    ],
)
def test_a_qualified_name_that_places_nowhere_exits_2(tmp_path, capsys, rules, where, name):
    code, out, err = run(capsys, "check", str(bespoke(tmp_path, rules)))

    assert code == 2
    assert out == ""
    assert err.startswith("archview: archview.toml: ")
    assert where in err
    assert repr(name) in err
