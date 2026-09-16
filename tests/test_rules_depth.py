"""Checker depth: TYPE_CHECKING (A4), layers and independence (C8), zones (C9), baseline (C7)."""

from dataclasses import replace

from archview.rules.baseline import apply_baseline, baseline_of, load_baseline
from archview.rules.check import check
from archview.rules.config import Config, MetricRules, parse_config
from tests.builders import model


def kinds(report, failing_only=False):
    return [(p.kind, p.components) for p in report.problems if p.fails or not failing_only]


def test_type_checking_imports_are_ignored_by_default_and_can_be_included():
    m = model(("app.domain.order", "app.infra.db"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))
    rules = {"domain": (), "infra": ()}

    assert check(m, Config(allowed=rules)).problems == ()
    included = Config(allowed=rules, type_checking_imports="include")
    assert kinds(check(m, included)) == [("not_allowed", ("domain", "infra"))]


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
