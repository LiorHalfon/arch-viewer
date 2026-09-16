"""Graphviz DOT for a view: layers as ranks, cycles in red (V1, V2, V6)."""

from archview.model.view import build_view
from archview.render.dot import to_dot
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
    assert '"pkg.main" [label="main" fillcolor="#f7f7f7" penwidth=2 class="module"]' in dot


def test_marks_a_package_with_a_cycle_somewhere_inside_it():
    view = build_view(model(("pkg.api.routes", "pkg.domain.model")), "pkg")

    dot = to_dot(view, tangled={"pkg.api"})

    assert 'label="api \u27f2\\n(1 module)" fontcolor="red"' in dot
    assert 'class="package tangled"' in dot
