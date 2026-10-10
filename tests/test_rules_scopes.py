from dataclasses import replace

from archview.model.graph import Node
from archview.rules.check import Notice, Report
from archview.rules.config import Config, Exemption, Forbidden
from archview.rules.scopes import check_scope
from tests.builders import model

M = model(
    ("app.svc.print.flow", "app.svc.pricing.price"),
    ("app.svc.print.flow", "app.svc.users.repo"),
    ("app.svc.print.flow", "app.models.order"),
    ("app.api.routes", "app.svc.print.flow"),
)
ALLOWED = {"print": ("pricing",), "pricing": (), "users": ()}


def test_a_scope_checks_the_children_of_its_package():
    r = check_scope(M, "app.svc", Config(allowed=ALLOWED))
    assert r.project == "app.svc"
    assert r.components == ("pricing", "print", "users")
    assert [(p.kind, p.components) for p in r.problems] == [("not_allowed", ("print", "users"))]


def test_a_new_child_missing_from_allowed_is_undeclared():
    r = check_scope(M, "app.svc", Config(allowed={"print": ("pricing", "users"), "pricing": ()}))
    assert [(p.kind, p.components) for p in r.problems] == [("undeclared", ("users",))]


def test_a_cycle_inside_the_scope_is_found():
    m = model(
        ("app.svc.print.flow", "app.svc.users.repo"),
        ("app.svc.users.repo", "app.svc.print.flow"),
    )
    r = check_scope(m, "app.svc", Config(allowed={"print": ("users",), "users": ("print",)}))
    assert [p.kind for p in r.problems] == ["cycle"]


def test_an_exception_names_modules_by_their_full_name():
    exc = Exemption("app.svc.print.**", "app.svc.users.**", "legacy")
    r = check_scope(M, "app.svc", Config(allowed=ALLOWED, exceptions=(exc,)))
    assert r.problems == ()


def test_a_component_pattern_is_read_below_the_scope():
    config = Config(
        allowed={"billing": ("people",), "people": ()},
        components={"billing": ("print", "pricing"), "people": ("users",)},
        scope="app.svc",
    )

    r = check_scope(M, "app.svc", config)

    assert r.components == ("billing", "people")
    assert r.problems == ()


def test_a_component_pattern_written_in_full_is_still_read_in_full():
    config = Config(
        allowed={"billing": ("people",), "people": ()},
        components={"billing": ("app.svc.print", "pricing"), "people": ("app.svc.users",)},
        scope="app.svc",
    )

    assert check_scope(M, "app.svc", config).components == ("billing", "people")


def test_an_exception_may_name_modules_below_the_scope():
    exc = Exemption("print.**", "users.**", "legacy")
    r = check_scope(M, "app.svc", Config(allowed=ALLOWED, exceptions=(exc,), scope="app.svc"))
    assert r.problems == ()
    assert [w.kind for w in r.warnings] == []


def test_an_unmatched_pattern_says_it_was_read_below_the_scope():
    config = Config(allowed=ALLOWED, components={"people": ("user",)}, scope="app.svc")

    assert (
        Notice(
            "unmatched_pattern",
            "[archview.components.people] pattern 'user' matches no module below app.svc",
        )
        in check_scope(M, "app.svc", config).warnings
    )


def test_a_forbidden_target_in_the_rest_of_the_project_is_a_dead_rule():
    allowed = {"print": ("pricing", "users"), "pricing": (), "users": ()}
    r = check_scope(
        M, "app.svc", Config(allowed=allowed, forbidden=(Forbidden("print", "models"),))
    )
    assert (
        Notice(
            "unknown_component",
            "[archview.forbidden] names 'models', which is not a child of app.svc; "
            "imports into the rest of the project are checked by the rules above it",
        )
        in r.warnings
    )


def test_a_forbidden_package_nothing_imports_yet_is_the_ban_working():
    allowed = {"print": ("pricing", "users"), "pricing": (), "users": ()}
    r = check_scope(
        M, "app.svc", Config(allowed=allowed, forbidden=(Forbidden("print", "openai"),))
    )
    assert [w for w in r.warnings if "not a child" in w.message] == []


def with_openai(m):
    """`m` with `openai` an outside package rather than a module of the project."""
    outside = Node("openai", None, "external")
    return replace(m, nodes=tuple(outside if n.id == "openai" else n for n in m.nodes))


OPENAI = with_openai(
    model(
        ("app.svc.print.flow", "app.svc.pricing.price"),
        ("app.svc.print.flow", "openai"),
        ("app.svc.pricing.price", "openai"),
        ("app.svc.print.flow", "app.models.order"),
    )
)
PASSING = {"print": ("pricing",), "pricing": ()}


def test_a_scope_checks_what_its_children_import_from_outside_the_project():
    config = Config(allowed=PASSING, externals={"print": ("openai",), "pricing": ()})

    (problem,) = check_scope(OPENAI, "app.svc", config).problems

    assert (problem.kind, problem.components, problem.rule) == (
        "outside",
        ("pricing", "openai"),
        "archview.externals.pricing",
    )


def test_a_scope_without_externals_does_not_judge_outside_imports():
    assert check_scope(OPENAI, "app.svc", Config(allowed=PASSING)).problems == ()


def test_closed_externals_in_a_scope_fail_a_child_that_is_not_a_key():
    config = Config(allowed=PASSING, externals={"print": ("openai",)}, externals_undeclared="error")

    r = check_scope(OPENAI, "app.svc", config)

    assert [(p.kind, p.components) for p in r.problems] == [("undeclared_externals", ("pricing",))]


def test_a_forbidden_outside_package_fires_in_a_scope():
    config = Config(allowed=PASSING, forbidden=(Forbidden("pricing", "openai"),))

    r = check_scope(OPENAI, "app.svc", config)

    assert [(p.kind, p.components) for p in r.problems] == [("forbidden", ("pricing", "openai"))]
    assert [w for w in r.warnings if "not a child" in w.message] == []


def test_a_forbidden_target_that_is_a_child_is_not_a_dead_rule():
    allowed = {"print": ("pricing", "users"), "pricing": (), "users": ()}
    r = check_scope(
        M, "app.svc", Config(allowed=allowed, forbidden=(Forbidden("pricing", "users"),))
    )
    assert not [w for w in r.warnings if "not a child" in w.message]


def test_a_scope_without_allowed_points_at_init_root():
    r = check_scope(M, "app.svc", Config())
    assert [w for w in r.warnings if w.kind == "no_rules"] == [
        Notice(
            "no_rules",
            "no [archview.allowed] table: only cycles are checked; "
            "run `archview init --root app.svc` to write one",
        )
    ]


def test_a_report_fails_when_a_scope_fails():
    inner = check_scope(M, "app.svc", Config(allowed={"print": (), "pricing": (), "users": ()}))
    outer = Report("app", ("svc",), (), (), scopes=(("app/svc/archview.toml", inner),))
    assert outer.failed and outer.failing == 2
