"""Rules that name a package outside the project (issue #1)."""

from __future__ import annotations

import pytest

from archview.model.graph import Import, Model, Node
from archview.rules.check import check, component_edges
from archview.rules.components import ComponentMap
from archview.rules.config import Config, ConfigError, Exemption, Forbidden
from tests.builders import model_with_external


def test_outside_names_a_module_that_is_not_under_the_project():
    components = ComponentMap("shop", ".", {})
    assert components.outside("openai") == "openai"


def test_outside_trusts_the_extractors_own_squash():
    """grimp already squashes a deep Python import (`openai.types.chat`) to its
    top-level package before `outside` ever sees it, and TypeScript's `_external_name`
    does the same for npm imports - so `outside` must not re-split on `sep`, or a
    scoped npm name or a workspace's `../sibling` outside name (M8) would be cut down
    to its first segment (`@scope`, `..`)."""
    components = ComponentMap("web", "/", {})
    assert components.outside("@scope/pkg") == "@scope/pkg"
    assert components.outside("../sibling") == "../sibling"


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


def test_a_dead_externals_rule_warns():
    """An `externals` target nothing imports is dead config: you granted access to a
    package that is not there. The `forbidden` mirror image is NOT dead - see
    `test_a_forbidden_target_that_nothing_imports_does_not_warn` (issue #5). This test
    asserted the `forbidden` case until then, which was the behaviour that issue
    reported as training people to ignore warnings."""
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"llm": ("anthropic",)})
    report = check(model_with_external(), config)
    assert any("anthropic" in w.message for w in report.warnings)


def test_an_externals_key_that_is_not_a_component_warns():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"nope": ()})
    report = check(model_with_external(), config)
    assert any("nope" in w.message for w in report.warnings)


def test_an_allowed_target_naming_an_outside_package_warns():
    """`[archview.allowed]` is only ever consulted for `edges.internal` pairs, where
    both sides are components (`_rule_problems`); naming an outside package there is a
    rule that can never fire, and used to be silent because the `known` set the
    `allowed` loop checked against was widened (for `forbidden`/`*`) to include
    externals - Fix 2 (M7/M8 review)."""
    config = Config(allowed={"api": ["llm"], "llm": ["openai"]})
    report = check(model_with_external(), config)
    assert [w.message for w in report.warnings if w.kind == "unknown_component"] == [
        "[archview.allowed.llm] names 'openai', which has no modules"
    ]


def test_an_allowed_target_naming_the_star_wildcard_warns():
    """Unlike `forbidden.from`, `[archview.allowed]` targets never expand `"*"` - so
    naming it there is a dead entry that must warn."""
    config = Config(allowed={"api": ["llm"], "llm": ["*"]})
    report = check(model_with_external(), config)
    assert [w.message for w in report.warnings if w.kind == "unknown_component"] == [
        "[archview.allowed.llm] names '*', which has no modules"
    ]


def test_an_outside_name_on_the_from_side_is_an_error():
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("openai", "llm"),))
    with pytest.raises(ConfigError, match="openai"):
        check(model_with_external(), config)


def test_a_forbidden_target_that_nothing_imports_does_not_warn():
    """A ban naming an absent package is the ban working, not dead config.

    The name is missing from the graph precisely because nobody imports it (issue #5).
    """
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("*", "anthropic"),))
    report = check(model_with_external(), config)
    assert [w for w in report.warnings if "anthropic" in w.message] == []


def test_a_forbidden_source_that_names_nothing_still_warns():
    """`from` naming a component that does not exist can never fire - that is a typo."""
    config = Config(allowed={"api": ["llm"], "llm": []}, forbidden=(Forbidden("nope", "openai"),))
    report = check(model_with_external(), config)
    assert any("nope" in w.message for w in report.warnings)


def test_a_layers_derived_rule_still_warns_about_a_typo():
    """`layers` names components, so an absent one there is a misspelling, not a ban."""
    config = Config(allowed={"api": ["llm"], "llm": []}, layers=[("api",), ("typo",)])
    report = check(model_with_external(), config)
    assert any("typo" in w.message for w in report.warnings)


def test_public_outside_a_workspace_warns_that_it_does_nothing():
    """`public` only constrains imports from other packages in a workspace."""
    config = Config(allowed={"api": ["llm"], "llm": []}, public=("api",))
    report = check(model_with_external(), config)
    assert [w.kind for w in report.warnings if w.kind == "public_ignored"] == ["public_ignored"]


def test_public_inside_a_workspace_does_not_warn():
    config = Config(allowed={"api": ["llm"], "llm": []}, public=("api",))
    report = check(model_with_external(), config, in_workspace=True)
    assert not [w for w in report.warnings if w.kind == "public_ignored"]


def two_reach_openai() -> Model:
    """`wiring` and `book` both import openai; only `wiring` will be constrained."""
    nodes = (
        Node("shop", None, "package"),
        Node("shop.wiring", "shop", "module", "shop/wiring.py"),
        Node("shop.book", "shop", "module", "shop/book.py"),
        Node("openai", None, "external"),
        Node("httpx", None, "external"),
    )
    imports = (
        Import("shop.wiring", "openai", "shop/wiring.py", 1, "import openai"),
        Import("shop.book", "openai", "shop/book.py", 1, "import openai"),
        Import("shop.book", "httpx", "shop/book.py", 2, "import httpx"),
    )
    return Model(project="shop", nodes=nodes, imports=imports)


ALLOWED_BOTH = {"wiring": (), "book": ()}


def test_a_partial_externals_table_says_what_it_does_not_cover():
    """The whole of issue #5: the table reads as a fence and is an allow-list."""
    config = Config(allowed=ALLOWED_BOTH, externals={"wiring": ("openai",)})
    report = check(two_reach_openai(), config)
    note = next(w for w in report.warnings if w.kind == "partial_externals")
    assert "book" in note.message
    assert "openai" in note.message


def test_no_note_when_every_importer_is_constrained():
    config = Config(
        allowed=ALLOWED_BOTH,
        externals={"wiring": ("openai",), "book": ("openai", "httpx")},
    )
    report = check(two_reach_openai(), config)
    assert [w for w in report.warnings if w.kind == "partial_externals"] == []


def test_no_note_for_a_package_the_table_does_not_name():
    """httpx is imported by an unconstrained component, but the table never names it,
    so it is not this notice's business - that is what keeps the notice quiet."""
    config = Config(allowed=ALLOWED_BOTH, externals={"wiring": ("openai",)})
    report = check(two_reach_openai(), config)
    notes = [w for w in report.warnings if w.kind == "partial_externals"]
    assert not any("httpx" in w.message for w in notes)


def three_reach_openai() -> Model:
    """`wiring` and `checkout` both grant themselves `openai`; `book` also imports it
    but is a key of neither."""
    nodes = (
        Node("shop", None, "package"),
        Node("shop.wiring", "shop", "module", "shop/wiring.py"),
        Node("shop.checkout", "shop", "module", "shop/checkout.py"),
        Node("shop.book", "shop", "module", "shop/book.py"),
        Node("openai", None, "external"),
    )
    imports = (
        Import("shop.wiring", "openai", "shop/wiring.py", 1, "import openai"),
        Import("shop.checkout", "openai", "shop/checkout.py", 1, "import openai"),
        Import("shop.book", "openai", "shop/book.py", 1, "import openai"),
    )
    return Model(project="shop", nodes=nodes, imports=imports)


def test_two_keys_granting_the_same_package_still_produce_one_note():
    """The repetition Fix A1 removes: `wiring` and `checkout` both grant `openai`, so
    the old per-(key, package) loop emitted the same 'book is unconstrained' notice
    twice, verbatim. There must be exactly one notice for the package, naming both
    granting keys."""
    config = Config(
        allowed={"wiring": (), "checkout": (), "book": ()},
        externals={"wiring": ("openai",), "checkout": ("openai",)},
    )
    report = check(three_reach_openai(), config)
    notes = [w for w in report.warnings if w.kind == "partial_externals"]
    assert len(notes) == 1
    assert "wiring" in notes[0].message
    assert "checkout" in notes[0].message
    assert "book" in notes[0].message


def test_closed_mode_fails_a_component_with_no_externals_entry():
    config = Config(
        allowed={"api": ["llm"], "llm": []},
        externals={"api": ()},
        externals_undeclared="error",
    )
    report = check(model_with_external(), config)
    assert [(p.kind, p.components) for p in report.problems if p.fails] == [
        ("undeclared_externals", ("llm",))
    ]


def test_closed_mode_silences_the_partial_externals_notice():
    """`partial_externals` names the unconstrained importer as already failing
    (`undeclared_externals`) under closed mode, and its own last sentence - "only
    components named in [table.externals] are checked" - is exactly what closed mode
    stops being true. Restating a failure and misdescribing the config at the same
    time is worse than staying quiet (review)."""
    config = Config(
        allowed=ALLOWED_BOTH,
        externals={"wiring": ("openai",)},
        externals_undeclared="error",
    )
    report = check(two_reach_openai(), config)
    assert [w for w in report.warnings if w.kind == "partial_externals"] == []


def test_closed_mode_passes_when_every_reacher_is_declared():
    config = Config(
        allowed={"api": ["llm"], "llm": []},
        externals={"llm": ("openai",)},
        externals_undeclared="error",
    )
    assert [p for p in check(model_with_external(), config).problems if p.fails] == []


def test_the_default_is_open():
    config = Config(allowed={"api": ["llm"], "llm": []}, externals={"api": ()})
    assert [p for p in check(model_with_external(), config).problems if p.fails] == []
