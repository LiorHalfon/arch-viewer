"""Graphviz DOT for a view: layers as ranks, cycles in red (V1, V2, V6)."""

from dataclasses import replace

from archview.model.view import build_view
from archview.render.dot import to_dot
from archview.render.mermaid import to_mermaid
from tests.builders import model


def test_puts_the_nodes_of_one_layer_on_the_same_rank():
    view = build_view(model(("pkg.api.routes", "pkg.domain.model")), "pkg")

    dot = to_dot(view)

    assert '{ rank=same; "pkg.api" }' in dot
    assert '{ rank=same; "pkg.domain" }' in dot


def test_labels_each_edge_with_its_import_count():
    view = build_view(
        model(("pkg.api.routes", "pkg.domain.model"), ("pkg.api.views", "pkg.domain.model")),
        "pkg",
    )

    assert '"pkg.api" -> "pkg.domain" [label="2"]' in to_dot(view)


def test_draws_cyclic_edges_in_red():
    view = build_view(model(("pkg.a.x", "pkg.b.y"), ("pkg.b.y", "pkg.a.x")), "pkg")

    dot = to_dot(view)

    assert '"pkg.a" -> "pkg.b" [label="1" color="red" penwidth=2 class="cycle"]' in dot
    assert '"pkg.b" -> "pkg.a" [label="1" color="red" penwidth=2 class="cycle"]' in dot


def test_is_valid_input_for_graphviz():
    view = build_view(model(("pkg.api.routes", "pkg.domain.model")), "pkg")

    dot = to_dot(view)

    assert dot.startswith('digraph "pkg" {')
    assert dot.rstrip().endswith("}")


def test_draws_packages_as_uml_components_and_modules_as_plain_boxes():
    view = build_view(model(("pkg.api.routes", "pkg.main")), "pkg")

    dot = to_dot(view)

    assert (
        '"pkg.api" [label="api\\n(1 module)" shape=component style="filled" class="package"]' in dot
    )
    assert (
        '"pkg.main" [label="main" fillcolor="#f7f7f7" penwidth=2 class="module zone-pain"]' in dot
    )


def test_marks_a_package_with_a_cycle_somewhere_inside_it():
    view = build_view(model(("pkg.api.routes", "pkg.domain.model")), "pkg")

    dot = to_dot(view, tangled={"pkg.api"})

    assert 'label="api \u27f2\\n(1 module)" fontcolor="red"' in dot
    assert 'class="package tangled"' in dot


def styled_view():
    m = model(
        ("pkg.api.routes", "pkg.domain.ports"),
        ("pkg.api.routes", "pkg.infra.db"),
        ("pkg.infra.db", "pkg.domain.ports"),
    )
    m = replace(
        m,
        nodes=tuple(replace(n, abstract=n.id == "pkg.domain.ports") for n in m.nodes),
        imports=tuple(replace(i, type_checking=i.imported == "pkg.infra.db") for i in m.imports),
    )
    return build_view(m, "pkg")


def test_abstract_nodes_are_green_and_edges_to_them_end_in_a_hollow_triangle():
    dot = to_dot(styled_view())

    assert 'fillcolor="#dcefd9" class="package abstract' in dot
    assert '"pkg.api" -> "pkg.domain" [label="1" arrowhead=onormal class="abstract"]' in dot


def test_type_checking_edges_are_dotted_and_violations_dashed_orange():
    dot = to_dot(styled_view(), violations={("pkg.infra", "pkg.domain")})

    assert '"pkg.api" -> "pkg.infra" [label="1" style="dotted" class="typing"]' in dot
    assert (
        '"pkg.infra" -> "pkg.domain" [label="1" color="#d9480f" style="dashed" penwidth=2'
        ' arrowhead=onormal class="violation abstract"]' in dot
    )


def test_mermaid_flowchart_has_every_box_and_counted_edge():
    text = to_mermaid(styled_view(), violations={("pkg.infra", "pkg.domain")})

    assert text.startswith("%% archview: pkg\nflowchart TB\n")
    assert '  n_pkg_api["api<br/>1 module"]' in text
    assert "  n_pkg_api -- 1 --> n_pkg_domain" in text
    assert "  n_pkg_api -. 1 .-> n_pkg_infra" in text
    assert "  n_pkg_infra -. 1 ✗ .-> n_pkg_domain" in text
    assert "  class n_pkg_domain abstract" in text


def test_quotes_ids_with_slashes_dots_and_at_signs():
    m = model(("app/ui/Button.web.tsx", "app/@scope/x.ts"), sep="/")

    dot = to_dot(build_view(m, "app"))

    assert '"app/ui" -> "app/@scope" [label="1"' in dot
    assert '  "app/ui" [label="ui\\n(1 module)"' in dot
