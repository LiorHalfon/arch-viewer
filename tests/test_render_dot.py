"""Graphviz DOT for a view: layers as ranks, cycles in red (V1, V2, V6)."""

from archview.model.view import build_view
from archview.render.dot import to_dot
from tests.test_view import model


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

    assert '"pkg.a" -> "pkg.b" [label="1" color="red" penwidth=2]' in dot
    assert '"pkg.b" -> "pkg.a" [label="1" color="red" penwidth=2]' in dot


def test_is_valid_input_for_graphviz():
    view = build_view(model(("pkg.api.routes", "pkg.domain.model")), "pkg")

    dot = to_dot(view)

    assert dot.startswith('digraph "pkg" {')
    assert dot.rstrip().endswith("}")
