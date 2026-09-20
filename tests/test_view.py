"""Deriving the view for a root: aggregation, cycles, layers, metrics."""

from dataclasses import replace

from archview.model.view import build_view, tangled_packages
from tests.builders import model, model_with_external


def test_aggregates_imports_between_children_of_the_root_into_one_counted_edge():
    m = model(
        ("pkg.api.routes", "pkg.domain.model"),
        ("pkg.api.views", "pkg.domain.model"),
    )

    view = build_view(m, "pkg")

    assert [(e.source, e.target, e.count) for e in view.edges] == [("pkg.api", "pkg.domain", 2)]


def test_lists_each_child_of_the_root_as_a_node_with_its_module_count():
    m = model(
        ("pkg.api.routes", "pkg.domain.model"),
        ("pkg.api.views", "pkg.domain.model"),
    )

    view = build_view(m, "pkg")

    assert [(n.id, n.name, n.kind, n.module_count) for n in view.nodes] == [
        ("pkg.api", "api", "package", 2),
        ("pkg.domain", "domain", "package", 1),
    ]


def test_marks_the_nodes_and_edges_that_take_part_in_a_cycle():
    m = model(
        ("pkg.a.x", "pkg.b.y"),
        ("pkg.b.y", "pkg.a.x"),
        ("pkg.a.x", "pkg.c.z"),
    )

    view = build_view(m, "pkg")

    assert view.cycles == (("pkg.a", "pkg.b"),)
    assert {n.id for n in view.nodes if n.in_cycle} == {"pkg.a", "pkg.b"}
    assert {(e.source, e.target) for e in view.edges if e.in_cycle} == {
        ("pkg.a", "pkg.b"),
        ("pkg.b", "pkg.a"),
    }


def test_layers_importers_above_the_packages_they_import():
    m = model(
        ("pkg.api.routes", "pkg.services.pricing"),
        ("pkg.services.pricing", "pkg.domain.model"),
    )

    view = build_view(m, "pkg")

    assert {n.name: n.layer for n in view.nodes} == {"api": 0, "services": 1, "domain": 2}


def test_gives_the_members_of_a_cycle_the_same_layer():
    m = model(
        ("pkg.a.x", "pkg.b.y"),
        ("pkg.b.y", "pkg.a.x"),
        ("pkg.a.x", "pkg.c.z"),
    )

    view = build_view(m, "pkg")

    layers = {n.name: n.layer for n in view.nodes}
    assert layers["a"] == layers["b"]
    assert layers["c"] > layers["a"]


def test_counts_fan_in_and_fan_out_per_node():
    m = model(
        ("pkg.api.routes", "pkg.domain.model"),
        ("pkg.api.views", "pkg.domain.model"),
        ("pkg.services.pricing", "pkg.domain.model"),
    )

    view = build_view(m, "pkg")

    fan = {n.name: (n.fan_in, n.fan_out) for n in view.nodes}
    assert fan == {"api": (0, 2), "domain": (3, 0), "services": (0, 1)}


def test_keeps_the_concrete_imports_behind_each_edge():
    m = model(
        ("pkg.api.routes", "pkg.domain.model"),
        ("pkg.api.views", "pkg.domain.model"),
    )

    view = build_view(m, "pkg")

    behind = [(i.importer, i.imported, i.file, i.line) for i in view.edges[0].imports]
    assert behind == [
        ("pkg.api.routes", "pkg.domain.model", "pkg/api/routes.py", 1),
        ("pkg.api.views", "pkg.domain.model", "pkg/api/views.py", 2),
    ]


def test_a_package_is_tangled_when_a_cycle_sits_anywhere_inside_it():
    m = model(
        ("pkg.core.a.x", "pkg.core.b.y"),
        ("pkg.core.b.y", "pkg.core.a.x"),
        ("pkg.api.routes", "pkg.core.a.x"),
    )

    assert tangled_packages(m) == frozenset({"pkg", "pkg.core"})


def test_computes_instability_abstractness_distance_and_zone_per_node():
    m = model(
        ("pkg.api.routes", "pkg.domain.order"),
        ("pkg.api.views", "pkg.domain.ports"),
        ("pkg.infra.db", "pkg.domain.ports"),
    )
    m = replace(m, nodes=tuple(replace(n, abstract=n.id == "pkg.domain.ports") for n in m.nodes))

    view = build_view(m, "pkg")

    got = {n.name: (n.instability, n.abstractness, n.distance, n.zone) for n in view.nodes}
    assert got == {
        "api": (1.0, 0.0, 0.0, "main_sequence"),
        "domain": (0.0, 0.5, 0.5, "pain"),
        "infra": (1.0, 0.0, 0.0, "main_sequence"),
    }


def test_marks_edges_to_abstractions_and_edges_only_for_type_checkers():
    m = model(("pkg.api.routes", "pkg.domain.ports"), ("pkg.api.routes", "pkg.infra.db"))
    m = replace(
        m,
        nodes=tuple(replace(n, abstract=n.id == "pkg.domain.ports") for n in m.nodes),
        imports=tuple(replace(i, type_checking=i.imported == "pkg.infra.db") for i in m.imports),
    )

    edges = {e.target: (e.abstract, e.type_checking) for e in build_view(m, "pkg").edges}

    assert edges == {"pkg.domain": (True, False), "pkg.infra": (False, True)}


def test_shows_external_packages_as_boxes_only_when_asked():
    m = model(("pkg.api.routes", "fastapi"), ("pkg.api.routes", "pkg.domain.order"))
    m = replace(
        m,
        project="pkg",
        nodes=tuple(
            replace(n, kind="external", parent=None, file=None) if n.id == "fastapi" else n
            for n in m.nodes
        ),
    )

    assert [n.name for n in build_view(m, "pkg").nodes] == ["api", "domain"]
    view = build_view(m, "pkg", externals=True)
    assert [(n.name, n.kind) for n in view.nodes] == [
        ("api", "package"),
        ("domain", "package"),
        ("fastapi", "external"),
    ]
    assert ("pkg.api", "fastapi") in {(e.source, e.target) for e in view.edges}


def test_keep_pulls_a_named_external_into_a_view_without_externals():
    m = model_with_external()

    view = build_view(m, "shop", externals=False, keep=frozenset({"openai"}))

    assert "openai" in [n.id for n in view.nodes]
    assert ("shop.llm", "openai") in [(e.source, e.target) for e in view.edges]


def test_keep_does_not_pull_in_other_externals():
    m = model_with_external()

    view = build_view(m, "shop", externals=False, keep=frozenset({"anthropic"}))

    assert "openai" not in [n.id for n in view.nodes]


def test_keep_ignores_a_name_that_is_not_actually_external():
    m = model_with_external()

    view = build_view(m, "shop", externals=False, keep=frozenset({"shop.api"}))

    assert [n.id for n in view.nodes] == ["shop.api", "shop.llm"]


def test_an_empty_keep_leaves_a_default_view_unchanged():
    m = model_with_external()

    assert build_view(m, "shop") == build_view(m, "shop", keep=frozenset())


def test_slash_separated_ids_with_dotted_file_names_are_their_own_nodes():
    m = model(
        ("app/api/routes.ts", "app/domain/order.ts"),
        ("app/api/Button.web.tsx", "app/api/Button.tsx"),
        sep="/",
    )

    top = build_view(m, "app")
    api = build_view(m, "app/api")

    assert [(e.source, e.target, e.count) for e in top.edges] == [("app/api", "app/domain", 1)]
    assert [n.name for n in api.nodes] == ["Button.tsx", "Button.web.tsx", "routes.ts"]
    assert [(e.source, e.target) for e in api.edges] == [
        ("app/api/Button.web.tsx", "app/api/Button.tsx")
    ]


def test_tangled_packages_are_found_with_slash_separated_ids():
    m = model(("app/a/x.ts", "app/b/y.ts"), ("app/b/y.ts", "app/a/x.ts"), sep="/")

    assert tangled_packages(m) == frozenset({"app"})
