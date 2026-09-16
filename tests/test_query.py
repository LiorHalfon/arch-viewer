"""Agent queries on the model: why, deps, rdeps, cycles (requirement G1, ADR 0009)."""

from dataclasses import replace

import pytest

from archview.model.graph import Node
from archview.model.query import (
    UnknownName,
    all_cycles,
    dependencies,
    dependents,
    resolve,
    runtime_only,
    why,
)
from archview.render.query import cycles_to_text
from tests.builders import model


def test_resolves_full_relative_and_external_names():
    m = model(("pkg.a.x", "pkg.b.y"))
    m = replace(m, nodes=(*m.nodes, Node("requests", None, "external")))

    assert resolve(m, "pkg.a.x") == "pkg.a.x"
    assert resolve(m, "a.x") == "pkg.a.x"
    assert resolve(m, "requests") == "requests"


def test_an_unknown_name_suggests_close_matches():
    m = model(("pkg.api.routes", "pkg.domain.model"))

    with pytest.raises(UnknownName, match=r"pkg\.api\.routes"):
        resolve(m, "api.route")


def test_why_lists_the_direct_imports_between_two_packages():
    m = model(
        ("pkg.domain.pricing", "pkg.infra.db"),
        ("pkg.domain.orders", "pkg.infra.cache"),
        ("pkg.api.x", "pkg.infra.db"),
    )

    answer = why(m, "pkg.domain", "pkg.infra")

    assert [(i.importer, i.imported) for i in answer.direct] == [
        ("pkg.domain.orders", "pkg.infra.cache"),
        ("pkg.domain.pricing", "pkg.infra.db"),
    ]
    assert answer.chain == ()
    assert answer.found


def test_why_falls_back_to_the_shortest_chain():
    m = model(
        ("pkg.a.x", "pkg.b.y"),
        ("pkg.b.y", "pkg.c.z"),
        ("pkg.b.y", "pkg.d.w"),
        ("pkg.d.w", "pkg.c.z"),
    )

    answer = why(m, "pkg.a", "pkg.c")

    assert answer.direct == ()
    assert [(i.importer, i.imported) for i in answer.chain] == [
        ("pkg.a.x", "pkg.b.y"),
        ("pkg.b.y", "pkg.c.z"),
    ]


def test_a_chain_does_not_pass_through_either_end():
    m = model(
        ("pkg.a.x", "pkg.a.inner"),
        ("pkg.a.inner", "pkg.m.hop"),
        ("pkg.m.hop", "pkg.b.y"),
    )

    answer = why(m, "pkg.a.x", "pkg.b")

    assert [(i.importer, i.imported) for i in answer.chain] == [
        ("pkg.a.x", "pkg.a.inner"),
        ("pkg.a.inner", "pkg.m.hop"),
        ("pkg.m.hop", "pkg.b.y"),
    ]
    assert why(m, "pkg.a", "pkg.b").chain[0].importer == "pkg.a.inner"


def test_why_ties_between_equally_short_chains_break_by_name():
    m = model(
        ("pkg.a.x", "pkg.q.hop"),
        ("pkg.a.x", "pkg.p.hop"),
        ("pkg.q.hop", "pkg.c.z"),
        ("pkg.p.hop", "pkg.c.z"),
    )

    assert why(m, "pkg.a", "pkg.c").chain[0].imported == "pkg.p.hop"


def test_why_finds_nothing_when_there_is_no_path():
    m = model(("pkg.c.z", "pkg.a.x"))

    answer = why(m, "pkg.a", "pkg.c")

    assert not answer.found


def test_why_refuses_overlapping_names():
    m = model(("pkg.a.x", "pkg.b.y"))

    with pytest.raises(ValueError, match="contains"):
        why(m, "pkg.a", "pkg.a.x")


def test_runtime_only_drops_type_checking_imports():
    m = model(("pkg.a.x", "pkg.b.y"))
    m = replace(m, imports=tuple(replace(i, type_checking=True) for i in m.imports))

    assert why(m, "pkg.a", "pkg.b").found
    assert not why(runtime_only(m), "pkg.a", "pkg.b").found


def test_deps_of_a_package_are_shortened_to_its_depth():
    m = model(
        ("pkg.services.pricing", "pkg.infra.cache"),
        ("pkg.services.pricing", "pkg.infra.db"),
        ("pkg.services.billing", "pkg.domain.model"),
        ("pkg.services.billing", "pkg.services.pricing"),
    )

    deps = dependencies(m, "pkg.services")

    assert [(d.name, len(d.imports)) for d in deps] == [("pkg.domain", 1), ("pkg.infra", 2)]


def test_deps_of_a_module_are_modules():
    m = model(
        ("pkg.services.pricing", "pkg.infra.cache"),
        ("pkg.services.pricing", "pkg.infra.db"),
    )

    assert [d.name for d in dependencies(m, "pkg.services.pricing")] == [
        "pkg.infra.cache",
        "pkg.infra.db",
    ]


def test_deps_leave_out_third_party_packages_unless_asked():
    m = model(("pkg.api.routes", "pkg.domain.model"), ("pkg.api.routes", "requests"))
    m = replace(
        m,
        nodes=tuple(
            Node("requests", None, "external") if n.id == "requests" else n for n in m.nodes
        ),
    )

    assert [d.name for d in dependencies(m, "pkg.api")] == ["pkg.domain"]
    assert [d.name for d in dependencies(m, "pkg.api", externals=True)] == [
        "pkg.domain",
        "requests",
    ]


def test_imports_are_listed_in_file_and_line_order():
    m = model(("pkg.a.x", "pkg.b.z"), ("pkg.a.x", "pkg.b.y"))

    assert [i.line for i in why(m, "pkg.a", "pkg.b").direct] == [1, 2]


def test_rdeps_list_who_imports_a_name_including_externals():
    m = model(
        ("pkg.api.routes", "pkg.services.pricing"),
        ("pkg.infra.db", "pkg.services.pricing"),
        ("pkg.api.routes", "requests"),
    )
    m = replace(
        m,
        nodes=tuple(
            Node("requests", None, "external") if n.id == "requests" else n for n in m.nodes
        ),
    )

    assert [d.name for d in dependents(m, "pkg.services")] == ["pkg.api", "pkg.infra"]
    assert [d.name for d in dependents(m, "requests")] == ["pkg.api.routes"]


def test_cycles_are_found_at_every_level_with_a_real_path():
    m = model(
        ("pkg.a.x", "pkg.b.y"),
        ("pkg.b.y", "pkg.a.x"),
        ("pkg.c.p.one", "pkg.c.q.two"),
        ("pkg.c.q.two", "pkg.c.r.three"),
        ("pkg.c.r.three", "pkg.c.p.one"),
    )

    cycles = all_cycles(m)

    assert [(c.level, c.path) for c in cycles] == [
        ("pkg", ("pkg.a", "pkg.b", "pkg.a")),
        ("pkg.c", ("pkg.c.p", "pkg.c.q", "pkg.c.r", "pkg.c.p")),
    ]
    assert [(s.source, s.target, len(s.imports)) for s in cycles[0].steps] == [
        ("pkg.a", "pkg.b", 1),
        ("pkg.b", "pkg.a", 1),
    ]


def test_a_tangle_lists_the_members_its_path_misses():
    m = model(
        ("pkg.a.x", "pkg.b.y"),
        ("pkg.b.y", "pkg.a.x"),
        ("pkg.b.y", "pkg.c.z"),
        ("pkg.c.z", "pkg.b.y"),
    )

    (cycle,) = all_cycles(m)

    assert cycle.members == ("pkg.a", "pkg.b", "pkg.c")
    assert cycle.path == ("pkg.a", "pkg.b", "pkg.a")
    assert cycle.missed == ("pkg.c",)


def test_a_tangle_shows_the_edges_its_path_does_not_take():
    m = model(
        ("pkg.a.x", "pkg.b.y"),
        ("pkg.b.y", "pkg.a.x"),
        ("pkg.b.y", "pkg.c.z"),
        ("pkg.c.z", "pkg.b.y"),
    )

    (cycle,) = all_cycles(m)
    text = cycles_to_text((cycle,), "pkg")

    assert [(s.source, s.target) for s in cycle.others] == [("pkg.b", "pkg.c"), ("pkg.c", "pkg.b")]
    assert "also in this tangle: pkg.c, through\n  pkg.b -> pkg.c  (1 import)" in text


def test_the_imports_behind_a_cycle_step_are_in_file_and_line_order():
    m = model(("pkg.a.x", "pkg.b.z"), ("pkg.a.x", "pkg.b.y"), ("pkg.b.y", "pkg.a.x"))
    m = replace(m, imports=m.imports[::-1])

    (cycle,) = all_cycles(m)

    assert [i.line for i in cycle.steps[0].imports] == [1, 2]


def test_cycles_can_be_limited_to_a_subtree():
    m = model(
        ("pkg.a.x", "pkg.b.y"),
        ("pkg.b.y", "pkg.a.x"),
        ("pkg.c.p.one", "pkg.c.q.two"),
        ("pkg.c.q.two", "pkg.c.p.one"),
    )

    assert [c.level for c in all_cycles(m, root="pkg.c")] == ["pkg.c"]
