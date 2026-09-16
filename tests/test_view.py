"""Deriving the view for a root: aggregation, cycles, layers, metrics."""

from archview.model.graph import Import, Model, Node
from archview.model.view import build_view


def model(*imports: tuple[str, str]) -> Model:
    """A model whose tree is implied by the dotted names in `imports`."""
    ids: set[str] = set()
    for pair in imports:
        for name in pair:
            parts = name.split(".")
            ids.update(".".join(parts[: i + 1]) for i in range(len(parts)))
    leaves = {name for pair in imports for name in pair}
    nodes = tuple(
        Node(
            id=i,
            parent=i.rpartition(".")[0] or None,
            kind="module" if i in leaves else "package",
            file=f"{i.replace('.', '/')}.py" if i in leaves else None,
        )
        for i in sorted(ids)
    )
    return Model(
        project=sorted(ids)[0].split(".")[0],
        nodes=nodes,
        imports=tuple(
            Import(
                importer=a,
                imported=b,
                file=f"{a.replace('.', '/')}.py",
                line=n + 1,
                text=f"import {b}",
            )
            for n, (a, b) in enumerate(imports)
        ),
    )


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
