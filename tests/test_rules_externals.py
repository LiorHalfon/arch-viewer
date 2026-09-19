"""Rules that name a package outside the project (issue #1)."""

from __future__ import annotations

from archview.rules.check import component_edges
from archview.rules.components import ComponentMap
from archview.rules.config import Config, Exemption
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
