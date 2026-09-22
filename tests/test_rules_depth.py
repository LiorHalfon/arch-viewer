"""Checker depth: TYPE_CHECKING (A4), layers and independence (C8), zones (C9), baseline (C7)."""

from dataclasses import replace

from archview.model.graph import Import, Model, Node
from archview.rules.baseline import apply_baseline, baseline_of, load_baseline
from archview.rules.check import check
from archview.rules.config import Config, Exemption, MetricRules, parse_config
from tests.builders import model


def kinds(report, failing_only=False):
    return [(p.kind, p.components) for p in report.problems if p.fails or not failing_only]


def test_type_checking_imports_are_included_by_default_and_can_be_ignored():
    """type_checking_imports defaults to "include" (issue #8): a type-only import is
    still a dependency, and is checked like any other unless a rules file opts out."""
    m = model(("app.domain.order", "app.infra.db"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))
    rules = {"domain": (), "infra": ()}

    assert kinds(check(m, Config(allowed=rules))) == [("not_allowed", ("domain", "infra"))]
    ignored = Config(allowed=rules, type_checking_imports="ignore")
    assert check(m, ignored).problems == ()


def test_a_type_only_import_is_checked_by_default():
    """A type-only import is still a dependency: it is a reason this file cannot be
    understood without that one, and it becomes a runtime import the moment someone
    needs a value (issue #8)."""
    m = model(("shop.api", "shop.infra"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))
    report = check(m, Config(allowed={"api": [], "infra": []}))
    assert [p.components for p in report.problems if p.fails] == [("api", "infra")]


def test_ignore_restores_the_old_behaviour():
    m = model(("shop.api", "shop.infra"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))
    report = check(m, Config(allowed={"api": [], "infra": []}, type_checking_imports="ignore"))
    assert report.problems == ()


def test_a_type_only_exception_exempts_a_type_only_import():
    m = model(("web.screens", "web.api"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))
    config = Config(
        allowed={"screens": [], "api": []},
        exceptions=(Exemption("web.screens", "web.api", "prop shapes only", kind="type_only"),),
    )
    assert check(m, config).problems == ()


def test_a_type_only_exception_does_not_exempt_a_value_import():
    """The whole point: the carve-out must not widen to the call it forbids."""
    m = model(("web.screens", "web.api"))
    config = Config(
        allowed={"screens": [], "api": []},
        exceptions=(Exemption("web.screens", "web.api", "prop shapes only", kind="type_only"),),
    )
    assert [p.components for p in check(m, config).problems] == [("screens", "api")]


def test_unused_exception_says_the_kind_excluded_it_not_that_it_is_unused():
    """(Fix 5, review) The pair *is* imported - the exception's own `kind` is what
    keeps it from matching, deliberately. Telling the user to "remove it" in the
    same report that fails this exact pair on `not_allowed` is the wrong steer."""
    m = model(("web.screens", "web.api"))
    config = Config(
        allowed={"screens": [], "api": []},
        exceptions=(Exemption("web.screens", "web.api", "prop shapes only", kind="type_only"),),
    )
    [warning] = [w for w in check(m, config).warnings if w.kind == "unused_exception"]
    assert warning.message == (
        "exception web.screens -> web.api matches no type_only import; "
        "the pair is imported, but not type-only"
    )


def test_unused_exception_says_so_when_type_checking_imports_are_ignored():
    """The same misleading "remove it" appears when `type_checking_imports =
    "ignore"` makes a `type_only` exception structurally unreachable repo-wide,
    not just when this one pair happens to have no type-only import (Fix 5,
    review)."""
    m = model(("web.screens", "web.api"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))
    config = Config(
        allowed={"screens": [], "api": []},
        type_checking_imports="ignore",
        exceptions=(Exemption("web.screens", "web.api", "prop shapes only", kind="type_only"),),
    )
    [warning] = [w for w in check(m, config).warnings if w.kind == "unused_exception"]
    assert warning.message == (
        "exception web.screens -> web.api matches no type_only import; "
        "the pair is imported, but not type-only"
    )


def test_an_exception_without_a_kind_still_exempts_anything():
    m = model(("web.screens", "web.api"))
    config = Config(
        allowed={"screens": [], "api": []},
        exceptions=(Exemption("web.screens", "web.api", "legacy"),),
    )
    assert check(m, config).problems == ()


def test_a_new_exception_kind_is_driven_by_one_shared_predicate(monkeypatch):
    """EXCEPTION_KINDS maps a kind name to the predicate that decides it, rather
    than `_exemption` hardcoding a second, separate condition for `"type_only"`.
    That is what makes adding a kind to the one mapping enough: a kind added here,
    at the single source of truth, must be honoured by `_exemption` without any
    change of its own - the failure mode this guards against is a kind that parses
    and validates but the checker silently never exempts anything with it."""
    from archview.rules import config as config_module

    monkeypatch.setitem(config_module.EXCEPTION_KINDS, "always", lambda imp: True)
    m = model(("web.screens", "web.api"))
    config = Config(
        allowed={"screens": [], "api": []},
        exceptions=(Exemption("web.screens", "web.api", "demo", kind="always"),),
    )
    assert check(m, config).problems == ()


def test_layers_forbid_importing_upwards_and_between_peers():
    config = parse_config({"layers": [["api", "cli"], "services", "domain"]})
    m = model(
        ("app.api.routes", "app.services.pricing"),
        ("app.domain.order", "app.services.pricing"),
        ("app.cli.main", "app.api.routes"),
    )

    report = check(m, config)

    assert [(p.kind, p.components, p.rule) for p in report.problems] == [
        ("forbidden", ("cli", "api"), "archview.layers"),
        ("forbidden", ("domain", "services"), "archview.layers"),
    ]


def test_independent_components_may_not_import_each_other():
    config = parse_config({"independent": [["billing", "shipping"]]})
    m = model(("app.billing.x", "app.shipping.y"), ("app.billing.x", "app.core.z"))

    report = check(m, config)

    assert [(p.components, p.rule) for p in report.problems] == [
        (("billing", "shipping"), "archview.independent")
    ]


def test_reports_component_metrics_and_fails_on_configured_zones():
    m = model(("app.api.a", "app.domain.x"), ("app.api.b", "app.domain.y"))
    config = Config(metrics=MetricRules(fail_on_zones=("pain",)))

    report = check(m, config)

    assert report.metrics["domain"].zone == "pain"
    assert kinds(report) == [("zone", ("domain",))]
    assert "concrete and depended upon" in report.problems[0].hint
    ignored = Config(metrics=MetricRules(fail_on_zones=("pain",), ignore=("domain",)))
    assert check(m, ignored).problems == ()


def test_lists_allowed_dependencies_that_nothing_uses():
    m = model(("app.api.a", "app.domain.x"))

    report = check(m, Config(allowed={"api": ("domain", "infra"), "domain": ()}))

    assert report.unused == (("api", "infra"),)


def test_dynamic_imports_are_reported_as_warnings():
    from archview.model.graph import ExtractionWarning

    m = model(("app.api.a", "app.domain.x"))
    m = replace(
        m, warnings=(ExtractionWarning("dynamic_import", "app.api.a", "app/api/a.py", 3, "x()"),)
    )

    [warning] = [w for w in check(m, Config()).warnings if w.kind != "no_rules"]
    assert warning.kind == "dynamic_import"
    assert warning.message.startswith("app/api/a.py:3 x()")
    assert "dynamic import" in warning.message


def test_an_extraction_warning_is_named_by_its_own_kind():
    """An unresolved import must not be reported as a dynamic one (TypeScript, M6)."""
    from archview.model.graph import ExtractionWarning

    m = model(("app.api.a", "app.domain.x"))
    m = replace(
        m,
        warnings=(
            ExtractionWarning(
                "unresolved_import",
                "app.api.a",
                "app/api/a.py",
                1,
                'import { X } from "@/gone";',
                "@/gone",
            ),
        ),
    )

    [warning] = [w for w in check(m, Config()).warnings if w.kind != "no_rules"]
    assert warning.kind == "unresolved_import"
    assert "unresolved import (@/gone)" in warning.message
    assert "dynamic" not in warning.message


RULES = {"domain": (), "infra": (), "api": ()}


def test_a_baseline_lets_known_violations_pass_and_new_ones_fail(tmp_path):
    before = model(("app.domain.order", "app.infra.db"))
    baseline_file = tmp_path / "archview-baseline.json"
    baseline_file.write_text(baseline_of(check(before, Config(allowed=RULES))).to_json())
    baseline = load_baseline(baseline_file)

    same = apply_baseline(check(before, Config(allowed=RULES)), baseline)
    assert not same.failed
    assert same.problems[0].baselined == 1

    after = model(("app.domain.order", "app.infra.db"), ("app.domain.money", "app.infra.db"))
    report = apply_baseline(check(after, Config(allowed=RULES)), baseline)
    assert report.failed
    [problem] = report.problems
    assert (problem.count, problem.baselined) == (1, 1)
    assert [i.importer for i in problem.imports] == ["app.domain.money"]


def test_a_baselined_cycle_fails_again_when_it_grows():
    small = model(("app.a.x", "app.b.y"), ("app.b.y", "app.a.x"))
    rules = Config(allowed={"a": ("b", "c"), "b": ("a", "c"), "c": ("a", "b")})
    baseline = baseline_of(check(small, rules))

    assert not apply_baseline(check(small, rules), baseline).failed
    grown = model(
        ("app.a.x", "app.b.y"),
        ("app.b.y", "app.a.x"),
        ("app.b.y", "app.c.z"),
        ("app.c.z", "app.a.x"),
    )
    assert apply_baseline(check(grown, rules), baseline).failed


def _llm_reaching(*targets: str) -> Model:
    """`shop.llm` imports each of `targets`, none declared anywhere."""
    nodes = (
        Node("shop", None, "package"),
        Node("shop.llm", "shop", "module", "shop/llm.py"),
        *(Node(t, None, "external") for t in targets),
    )
    imports = tuple(
        Import("shop.llm", t, "shop/llm.py", i + 1, f"import {t}") for i, t in enumerate(targets)
    )
    return Model(project="shop", nodes=nodes, imports=imports)


def test_a_baselined_undeclared_externals_does_not_refail_for_a_new_import():
    """ADR 0014: `undeclared_externals` is a component-level completeness claim, not
    an edge claim - unlike an ordinary rule problem, so it belongs in `WHOLE` next to
    `cycle` and `zone`, not fingerprinted per import. A baselined component must not
    re-fail just because it gained another outside import (Fix 5, review)."""
    config = Config(allowed={"llm": ()}, externals_undeclared="error")
    baseline = baseline_of(check(_llm_reaching("openai"), config))

    report = apply_baseline(check(_llm_reaching("openai", "anthropic"), config), baseline)

    problem = next(p for p in report.problems if p.kind == "undeclared_externals")
    assert not problem.fails
    assert not report.failed


def test_warns_when_baseline_entries_are_fixed():
    before = model(("app.domain.order", "app.infra.db"))
    baseline = baseline_of(check(before, Config(allowed=RULES)))
    fixed = model(("app.api.routes", "app.domain.order"))

    report = apply_baseline(check(fixed, Config(allowed={**RULES, "api": ("domain",)})), baseline)

    assert "stale_baseline" in [w.kind for w in report.warnings]


def test_new_config_keys_are_validated():
    import pytest

    from archview.rules.config import ConfigError

    with pytest.raises(ConfigError, match="type_checking_imports must be one of"):
        parse_config({"type_checking_imports": "yes"})
    with pytest.raises(ConfigError, match="unknown zone 'sad'"):
        parse_config({"metrics": {"fail_on_zones": ["sad"]}})
    with pytest.raises(ConfigError, match="threshold must be a number"):
        parse_config({"metrics": {"threshold": 3}})
