"""Rules that name a package outside the project (issue #1)."""

from __future__ import annotations

import pytest

from archview.rules.check import check, component_edges
from archview.rules.components import ComponentMap
from archview.rules.config import Config, ConfigError, Exemption, Forbidden
from tests.builders import model_with_external


def test_outside_names_a_module_that_is_not_under_the_project():
    components = ComponentMap("shop", ".", {})
    assert components.outside("openai") == "openai"
    assert components.outside("openai.types") == "openai"


def test_outside_is_none_inside_the_project():
    components = ComponentMap("shop", ".", {})
    assert components.outside("shop.api") is None
    assert components.outside("shop") is None


def test_outside_respects_ignored():
    components = ComponentMap("shop", ".", {}, frozenset({"openai"}))
    assert components.outside("openai") is None


def test_outside_edges_are_kept_apart_from_internal_ones():
    m = model_with_external()
    edges = component_edges(m, ComponentMap("shop", ".", {}), Config())
    assert list(edges.internal) == [("api", "llm")]
    assert list(edges.outside) == [("llm", "openai")]
    assert edges.outside[("llm", "openai")][0].line == 2


def test_an_exception_exempts_an_outside_edge():
    m = model_with_external()
    config = Config(exceptions=(Exemption("shop.llm", "openai", "the one adapter"),))
    edges = component_edges(m, ComponentMap("shop", ".", {}), config)
    assert edges.outside == {}
    assert edges.exceptions_used == {0}


def kinds(report):
    return sorted((p.kind, p.components) for p in report.problems)


def test_an_externals_allow_list_fails_an_undeclared_outside_import():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"llm": ()})
    report = check(model_with_external(), config)
    assert ("outside", ("llm", "openai")) in kinds(report)


def test_a_declared_outside_import_passes():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"llm": ("openai",)})
    assert check(model_with_external(), config).problems == ()


def test_all_lets_a_component_reach_anything_outside():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"llm": "all"})
    assert check(model_with_external(), config).problems == ()


def test_a_component_absent_from_the_externals_table_is_unconstrained():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"api": ()})
    assert check(model_with_external(), config).problems == ()


def test_an_outside_name_never_becomes_an_undeclared_component():
    config = Config(allowed={"api": ["llm"], "llm": []})
    report = check(model_with_external(), config)
    assert "openai" not in report.components
    assert not [p for p in report.problems if p.kind == "undeclared"]


def test_forbidden_reaches_an_outside_package():
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("llm", "openai"),))
    report = check(model_with_external(), config)
    assert ("forbidden", ("llm", "openai")) in kinds(report)


def test_forbidden_from_a_star_matches_every_component():
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("*", "openai"),))
    report = check(model_with_external(), config)
    assert ("forbidden", ("llm", "openai")) in kinds(report)


def test_forbidden_beats_the_externals_allow_list():
    config = Config(
        allowed={"api": ["llm"], "llm": []},
        externals={"llm": ("openai",)},
        forbidden=(Forbidden("llm", "openai"),),
    )
    assert [p.kind for p in check(model_with_external(), config).problems] == ["forbidden"]


def test_a_live_outside_rule_warns_about_nothing():
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("llm", "openai"),))
    report = check(model_with_external(), config)
    assert [w for w in report.warnings if w.kind == "unknown_component"] == []


def test_a_dead_outside_rule_warns():
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("llm", "anthropic"),))
    report = check(model_with_external(), config)
    assert any("anthropic" in w.message for w in report.warnings)


def test_an_externals_key_that_is_not_a_component_warns():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"nope": ()})
    report = check(model_with_external(), config)
    assert any("nope" in w.message for w in report.warnings)


def test_an_outside_name_on_the_from_side_is_an_error():
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("openai", "llm"),))
    with pytest.raises(ConfigError, match="openai"):
        check(model_with_external(), config)
