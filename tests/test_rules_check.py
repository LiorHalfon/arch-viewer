"""The checker: actual dependencies against the rules (C2, C3, C4)."""

from archview.rules.check import check
from archview.rules.components import ComponentMap
from archview.rules.config import ALL, Config, Exemption, Forbidden
from archview.rules.init import infer_rules
from tests.builders import model

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


def test_uses_the_pyproject_table_name_in_rules():
    m = model(("app.a.x", "app.b.y"))

    report = check(m, Config(table="tool.archview", allowed={"a": (), "b": ()}))

    assert report.problems[0].rule == "tool.archview.allowed.a"
