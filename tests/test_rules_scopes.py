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


def test_a_forbidden_target_outside_the_scope_is_a_dead_rule():
    allowed = {"print": ("pricing", "users"), "pricing": (), "users": ()}
    r = check_scope(
        M, "app.svc", Config(allowed=allowed, forbidden=(Forbidden("print", "openai"),))
    )
    assert (
        Notice(
            "unknown_component",
            "[archview.forbidden] names 'openai', which is not a child of app.svc; "
            "imports that leave a nested scope are checked by the rules above it",
        )
        in r.warnings
    )


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
