"""The checker: actual dependencies against the rules (C2, C3, C4)."""

from dataclasses import replace

import pytest

from archview.model.graph import Import, Model, Node
from archview.rules.check import check, component_map
from archview.rules.components import ComponentMap
from archview.rules.config import ALL, Config, ConfigError, Exemption, Forbidden
from archview.rules.init import infer_rules, infer_scope_rules
from tests.builders import model, model_with_external
from tests.test_rules_scopes import M as SCOPED

LAYERED = model(
    ("app.api.routes", "app.services.pricing"),
    ("app.services.pricing", "app.domain.order"),
    ("app.api.routes", "app.domain.order"),
)

RULES = {"api": ("services", "domain"), "services": ("domain",), "domain": ()}


def kinds(report):
    return [(p.kind, p.components) for p in report.problems]


def test_passes_when_every_dependency_is_allowed():
    report = check(LAYERED, Config(allowed=RULES))

    assert report.problems == ()
    assert not report.failed
    assert report.components == ("api", "domain", "services")


def test_a_component_may_always_import_itself():
    m = model(("app.domain.order", "app.domain.money"))

    assert check(m, Config(allowed={"domain": ()})).problems == ()


def test_reports_a_dependency_the_rules_do_not_allow_with_the_imports_behind_it():
    m = model(("app.domain.order", "app.infra.db"), ("app.domain.money", "app.infra.db"))

    report = check(m, Config(allowed={"domain": (), "infra": ()}))

    [problem] = report.problems
    assert (problem.kind, problem.components, problem.count) == (
        "not_allowed",
        ("domain", "infra"),
        2,
    )
    assert problem.rule == "archview.allowed.domain"
    assert [(i.file, i.line) for i in problem.imports] == [
        ("app/domain/order.py", 1),
        ("app/domain/money.py", 2),
    ]
    assert report.failed


def test_hints_at_inversion_when_the_import_runs_against_the_declared_direction():
    m = model(("app.domain.order", "app.infra.db"), ("app.infra.db", "app.domain.order"))

    report = check(m, Config(allowed={"domain": (), "infra": ("domain",)}, fail_on_cycles=False))

    hint = report.problems[0].hint
    assert "infra may depend on domain" in hint
    assert "invert it" in hint


def test_hints_at_what_is_allowed_when_the_components_are_unrelated():
    m = model(("app.api.routes", "app.infra.db"))

    report = check(m, Config(allowed={"api": ("domain",), "infra": ()}))

    assert "api may import only: domain" in report.problems[0].hint


def test_the_all_wildcard_allows_any_dependency():
    m = model(("app.tests.test_api", "app.api.routes"))

    assert check(m, Config(allowed={"tests": ALL, "api": ()})).problems == ()


def test_forbidden_wins_even_over_the_all_wildcard():
    m = model(("app.tests.test_api", "app.api.routes"))
    config = Config(allowed={"tests": ALL, "api": ()}, forbidden=(Forbidden("tests", "api"),))

    assert kinds(check(m, config)) == [("forbidden", ("tests", "api"))]


def test_forbidden_is_checked_without_an_allowed_table():
    m = model(("app.domain.order", "app.infra.db"))

    report = check(m, Config(forbidden=(Forbidden("domain", "infra"),)))

    assert kinds(report) == [("forbidden", ("domain", "infra"))]
    assert [w.kind for w in report.warnings] == ["no_rules"]


def test_a_component_missing_from_the_allowed_table_is_a_problem():
    report = check(LAYERED, Config(allowed={"api": ("services", "domain"), "domain": ()}))

    assert kinds(report) == [("undeclared", ("services",))]
    assert report.problems[0].count == 1


def test_an_exception_exempts_one_module_level_import_and_says_why():
    m = model(("app.domain.order", "app.infra.db"), ("app.domain.money", "app.infra.db"))
    exemption = Exemption("app.domain.order", "app.infra.db", "TT-1")

    report = check(m, Config(allowed={"domain": (), "infra": ()}, exceptions=(exemption,)))

    assert [p.count for p in report.problems] == [1]


def test_warns_about_an_exception_that_matches_nothing():
    exemption = Exemption("app.api.gone", "app.domain.order", "TT-2")

    report = check(LAYERED, Config(allowed=RULES, exceptions=(exemption,)))

    assert [w.kind for w in report.warnings] == ["unused_exception"]


def test_warns_about_rules_that_name_components_with_no_modules():
    report = check(LAYERED, Config(allowed={**RULES, "servces": ("domain",)}))

    assert [w.message for w in report.warnings] == [
        "[archview.allowed.servces] names 'servces', which has no modules"
    ]


def test_reports_a_cycle_between_components_and_names_the_thinnest_edge():
    m = model(
        ("app.services.pricing", "app.infra.cache"),
        ("app.services.pricing", "app.infra.db"),
        ("app.infra.db", "app.services.pricing"),
    )

    report = check(m, Config(allowed={"services": ("infra",), "infra": ("services",)}))

    [cycle] = report.problems
    assert (cycle.kind, cycle.components, cycle.count) == ("cycle", ("infra", "services"), 2)
    assert "infra -> services (1 import)" in cycle.hint


def test_cycles_are_reported_but_do_not_fail_when_switched_off():
    m = model(("app.a.x", "app.b.y"), ("app.b.y", "app.a.x"))

    report = check(m, Config(allowed={"a": ("b",), "b": ("a",)}, fail_on_cycles=False))

    assert kinds(report) == [("cycle", ("a", "b"))]
    assert not report.failed


def test_violations_do_not_fail_when_switched_off():
    m = model(("app.a.x", "app.b.y"))

    report = check(m, Config(allowed={"a": (), "b": ()}, fail_on_violations=False))

    assert kinds(report) == [("not_allowed", ("a", "b"))]
    assert not report.failed


def test_ignored_components_are_not_checked():
    m = model(("app.scripts.seed", "app.infra.db"))

    report = check(m, Config(allowed={"infra": ()}, ignored=("scripts",)))

    assert report.problems == ()


def test_explicit_components_group_modules_by_pattern():
    m = model(("app.db.session", "app.domain.order"), ("app.http_client.x", "app.api.routes"))
    config = Config(
        allowed={"adapters": ("domain",), "domain": (), "api": ()},
        components={"adapters": ("app.db", "app.http_*")},
    )

    assert kinds(check(m, config)) == [("not_allowed", ("adapters", "api"))]


def test_the_most_specific_component_pattern_wins():
    components = ComponentMap("app", ".", {"infra": ("app.infra",), "cache": ("app.infra.cache",)})

    assert components.of("app.infra.cache.redis") == "cache"
    assert components.of("app.infra.db") == "infra"
    assert components.of("app.api") == "api"
    assert components.of("app") == "app"
    assert components.of("other.thing") is None


def with_inits(m: Model, *packages: str) -> Model:
    """`m` with each of `packages` a package that has its own `__init__.py`."""
    return replace(
        m,
        nodes=tuple(
            replace(n, kind="package", file=f"{n.id.replace('.', '/')}/__init__.py")
            if n.id in packages
            else n
            for n in m.nodes
        ),
    )


SPLIT = with_inits(
    model(
        ("app.services.orders", "app.repos.interfaces.orders"),
        ("app.repos.sql.orders", "app.repos.interfaces.orders"),
    ),
    "app.repos",
)
SPLIT_RULES = Config(
    allowed={
        "repos_interfaces": (),
        "repos_sql": ("repos_interfaces",),
        "services": ("repos_interfaces",),
    },
    components={"repos_interfaces": ("app.repos.interfaces",), "repos_sql": ("app.repos.sql",)},
)


def test_the_init_left_by_a_package_split_into_components_is_not_one():
    report = check(SPLIT, SPLIT_RULES)

    assert report.components == ("repos_interfaces", "repos_sql", "services")
    assert report.problems == ()


def test_the_init_left_by_a_split_needs_a_rule_once_it_imports():
    m = replace(
        SPLIT,
        imports=(
            *SPLIT.imports,
            Import("app.repos", "app.repos.sql.orders", "app/repos/__init__.py", 1, "import x"),
        ),
    )

    (problem,) = check(m, SPLIT_RULES).problems

    assert (problem.kind, problem.components) == ("undeclared", ("repos",))
    assert problem.hint.startswith(
        "repos is only the __init__ of app.repos; its modules belong to "
        "repos_interfaces and repos_sql."
    )


def test_a_package_that_holds_only_an_init_is_still_a_component():
    m = model(("app.a.x", "app.b.y"))
    m = replace(m, nodes=(*m.nodes, Node("app.c", "app", "package", "app/c/__init__.py")))

    report = check(m, Config(allowed={"a": ("b",), "b": ()}))

    assert kinds(report) == [("undeclared", ("c",))]


def test_init_writes_no_rule_for_the_init_left_by_a_split():
    text = infer_rules(SPLIT, SPLIT_RULES)

    assert "repos = " not in text
    assert 'repos_sql = ["repos_interfaces"]' in text


def test_folding_puts_the_modules_directly_in_the_project_in_its_own_component():
    m = model(("app.wiring", "app.api.routes"), ("app.api.routes", "app.paths"))

    components = component_map(Config(components={"api": ("app.api",)}), m, fold=True)

    assert [components.of(n) for n in ("app.wiring", "app.paths", "app.api.routes")] == [
        "app",
        "app",
        "api",
    ]


def test_an_externals_key_naming_part_of_a_component_points_at_its_own_rules_file():
    m = model(("shop.llm.chat", "openai"), ("shop.api.routes", "shop.llm.chat"))
    m = replace(
        m, nodes=tuple(Node("openai", None, "external") if n.id == "openai" else n for n in m.nodes)
    )
    config = Config(externals={"api": (), "llm.chat": ("openai",)})

    with pytest.raises(ConfigError) as error:
        check(m, config)

    assert str(error.value) == (
        "[archview.externals] has the key 'llm.chat', a part of llm, but its keys name "
        "whole components. To say what part of llm may import, give llm a rules file of "
        "its own, with an [archview.externals] table keyed by llm's children"
    )


def test_components_of_a_slash_separated_project_include_root_files():
    m = model(
        ("app/components/ui/Button.tsx", "app/utils/format.ts"),
        ("app/i18n.ts", "app/components/ui/Button.tsx"),
        sep="/",
    )
    config = Config(allowed={"components": (), "utils": (), "i18n.ts": ("components",)})

    assert kinds(check(m, config)) == [("not_allowed", ("components", "utils"))]


def test_slash_separated_component_patterns_and_exceptions():
    components = ComponentMap("app", "/", {"ui": ("app/components/ui",)})
    m = model(("app/components/ui/Button.tsx", "app/utils/format.ts"), sep="/")
    config = Config(
        allowed={"components": (), "utils": ()},
        exceptions=(Exemption("app/components/**", "app/utils/format.ts", "legacy"),),
    )

    assert components.of("app/components/ui/Button.tsx") == "ui"
    assert components.of("app/components/Card.tsx") == "components"
    assert components.of("app") == "app"
    assert kinds(check(m, config)) == []


def test_init_quotes_file_components_and_records_the_language():
    m = model(("app/i18n.ts", "app/utils/format.ts"), sep="/")

    text = infer_rules(m)

    assert 'language = "typescript"' in text
    assert '"i18n.ts" = ["utils"]' in text


def test_init_writes_no_externals_table_by_default():
    assert "[archview.externals]" not in infer_rules(model_with_external(), Config())


def test_init_externals_writes_the_table_from_todays_imports():
    text = infer_rules(model_with_external(), Config(), externals=True)

    assert "[archview.externals]" in text
    assert 'llm = ["openai"]' in text
    assert "api = []" in text


def test_init_for_a_scope_writes_the_rules_between_its_children():
    text = infer_scope_rules(SCOPED, "app.svc", Config())

    assert text == (
        "# Dependency rules between the children of app.svc, inferred by\n"
        "# `archview init --root` from the imports as they are today. Imports that leave\n"
        "# app.svc are checked by the rules above it, not here. Delete the\n"
        "# dependencies that should not exist; the check then fails until the code matches.\n"
        "# Agents: never edit this file to make the check pass - fix the code or ask.\n"
        "\n"
        "[archview]\n"
        "fail_on_violations = true\n"
        "fail_on_cycles = true\n"
        "\n"
        "[archview.allowed]\n"
        "pricing = []\n"
        'print = ["pricing", "users"]\n'
        "users = []\n"
    )


def test_init_for_a_scope_keeps_its_components_and_ignored_and_reports_cycles():
    m = model(
        ("app.svc.print.flow", "app.svc.users.repo"),
        ("app.svc.users.repo", "app.svc.print.flow"),
        ("app.svc.pricing.price", "app.svc.legacy.old"),
    )
    config = Config(components={"pay": ("app.svc.pricing",)}, ignored=("legacy",))

    text = infer_scope_rules(m, "app.svc", config)

    assert 'ignored = ["legacy"]' in text
    assert "#   print -> users -> print\nfail_on_cycles = false\n" in text
    assert 'pay = []\nprint = ["users"]\nusers = ["print"]\n' in text
    assert text.endswith('[archview.components]\npay = ["app.svc.pricing"]\n')


def test_uses_the_pyproject_table_name_in_rules():
    m = model(("app.a.x", "app.b.y"))

    report = check(m, Config(table="tool.archview", allowed={"a": (), "b": ()}))

    assert report.problems[0].rule == "tool.archview.allowed.a"
