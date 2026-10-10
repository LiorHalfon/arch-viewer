"""Exclusions (A11) and cycle labels."""

from dataclasses import replace

from archview.model.cycles import describe_cycle
from archview.model.filter import scoped_model, without_files
from archview.model.graph import ExtractionWarning, Import, Node
from tests.builders import model, model_with_external


def test_drops_excluded_files_and_every_import_that_touches_them():
    m = model(
        ("app.api.routes", "app.domain.order"),
        ("app.tests.test_api", "app.api.routes"),
    )

    kept = without_files(m, ["**/tests/*"])

    assert "app.tests.test_api" not in {n.id for n in kept.nodes}
    assert [(i.importer, i.imported) for i in kept.imports] == [
        ("app.api.routes", "app.domain.order")
    ]


def test_drops_the_subtree_of_an_excluded_package(tmp_path):
    m = model(("app.legacy.old.x", "app.domain.order"))
    nodes = tuple(
        n if n.id != "app.legacy" else n.__class__(n.id, n.parent, n.kind, "app/legacy/__init__.py")
        for n in m.nodes
    )

    kept = without_files(m.__class__(m.project, nodes, m.imports), ["app/legacy/__init__.py"])

    assert not any(n.id.startswith("app.legacy") for n in kept.nodes)
    assert kept.imports == ()


def test_no_patterns_leaves_the_model_alone():
    m = model(("app.a.x", "app.b.y"))

    assert without_files(m, []) is m


def test_names_a_two_member_cycle_as_a_path_and_a_bigger_one_as_a_tangle():
    assert describe_cycle(("a", "b")) == "a -> b -> a"
    assert describe_cycle(("a", "b", "c")) == "tangle of 3: a, b, c"


def test_hides_tests_by_their_conventional_names():
    from archview.model.filter import without_tests

    m = model(
        ("app.api.routes", "app.domain.order"),
        ("app.tests.test_api", "app.api.routes"),
        ("app.api.test_routes", "app.api.routes"),
        ("app.conftest", "app.domain.order"),
    )

    kept = without_tests(m)

    assert [(i.importer, i.imported) for i in kept.imports] == [
        ("app.api.routes", "app.domain.order")
    ]


def test_hides_typescript_tests_by_their_conventional_names():
    from archview.model.filter import without_tests

    m = model(
        ("app/services/pricing.ts", "app/domain/order.ts"),
        ("app/services/pricing.test.ts", "app/services/pricing.ts"),
        ("app/services/pricing.spec.tsx", "app/services/pricing.ts"),
        ("app/services/__mocks__/pricing.ts", "app/domain/order.ts"),
        ("app/__tests__/flow.ts", "app/services/pricing.ts"),
        ("app/e2e/flow.ts", "app/services/pricing.ts"),
        ("app/ui/Button.e2e.tsx", "app/services/pricing.ts"),
        sep="/",
    )

    kept = without_tests(m)

    assert [(i.importer, i.imported) for i in kept.imports] == [
        ("app/services/pricing.ts", "app/domain/order.ts")
    ]


def test_scoped_model_keeps_the_scope_and_the_imports_inside_it():
    m = model(
        ("app.svc.a.x", "app.svc.b.y"),  # inside
        ("app.svc.a.x", "app.models.m"),  # leaves the scope
        ("app.api.r", "app.svc.a.x"),  # enters the scope
    )

    s = scoped_model(m, "app.svc")

    assert s.project == "app.svc"
    assert {n.id for n in s.nodes} == {
        "app.svc",
        "app.svc.a",
        "app.svc.a.x",
        "app.svc.b",
        "app.svc.b.y",
    }
    assert [(i.importer, i.imported) for i in s.imports] == [("app.svc.a.x", "app.svc.b.y")]
    assert next(n for n in s.nodes if n.id == "app.svc").parent is None


def test_scoped_model_drops_extraction_warnings():
    m = model_with_external()
    warning = ExtractionWarning("dynamic_import", "shop.llm", "shop/llm.py", 3, "import_module(x)")
    m = m.__class__(m.project, m.nodes, m.imports, warnings=(warning,))

    assert scoped_model(m, "shop").warnings == ()


def test_scoped_model_keeps_what_the_scope_imports_from_outside_the_project():
    """The rest of the project is the rules above's business; outside packages a nested
    file's `externals` can judge (issue #18)."""
    m = model_with_external()
    others = Node("requests", None, "external")
    m = replace(
        m,
        nodes=(
            *m.nodes,
            Node("other", None, "package"),
            Node("other.x", "other", "module", "o.py"),
            others,
        ),
        imports=(
            *m.imports,
            Import("shop.api", "other.x", "shop/api.py", 5, "import other.x"),
            Import("other.x", "requests", "o.py", 1, "import requests"),
        ),
    )

    s = scoped_model(m, "shop")

    assert [n.id for n in s.nodes if n.kind == "external"] == ["openai"]
    assert [(i.importer, i.imported) for i in s.imports] == [
        ("shop.api", "shop.llm"),
        ("shop.llm", "openai"),
    ]
