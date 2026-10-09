"""Qualified names in one package's rules: `core.ports` names a part of `core` (#17)."""

import pytest

from archview.rules.check import check
from archview.rules.config import Config, ConfigError, Forbidden
from archview.rules.scopes import check_scope
from tests.builders import model

PORTS = ("app.plugin.language", "app.core.ports.port")
TYPES = ("app.plugin.language", "app.core.types")
DESK = ("app.plugin.images", "app.core.desk.cast")
CONTRACT = {"plugin": ("core.ports", "core.types"), "core": ()}


def kinds(report):
    return [(p.kind, p.components, p.count) for p in report.problems]


def notices(report):
    return [w.message for w in report.warnings]


def test_a_qualified_grant_allows_imports_into_the_parts_it_names():
    report = check(model(PORTS, TYPES), Config(allowed=CONTRACT))

    assert report.problems == ()
    assert not [m for m in notices(report) if "has no modules" in m]


def test_a_qualified_grant_rejects_an_import_into_another_part_of_the_package():
    report = check(model(PORTS, TYPES, DESK), Config(allowed=CONTRACT))

    [problem] = report.problems
    assert (problem.kind, problem.components, problem.count) == (
        "not_allowed",
        ("plugin", "core.desk"),
        1,
    )
    assert problem.rule == "archview.allowed.plugin"
    assert [i.imported for i in problem.imports] == ["app.core.desk.cast"]
    assert "plugin may import only: core.ports, core.types" in problem.hint


def test_an_import_of_the_package_root_is_outside_a_qualified_grant():
    report = check(
        model(PORTS, TYPES, ("app.plugin.language", "app.core")), Config(allowed=CONTRACT)
    )

    assert kinds(report) == [("not_allowed", ("plugin", "core"), 1)]


def test_a_plain_grant_of_the_package_still_allows_every_part_of_it():
    allowed = {"plugin": ("core",), "core": ()}

    assert check(model(PORTS, TYPES, DESK), Config(allowed=allowed)).problems == ()


def test_a_qualified_grant_no_import_reaches_is_an_unused_allowance():
    report = check(
        model(PORTS, ("app.core.types", "app.core.ports.port")), Config(allowed=CONTRACT)
    )

    assert report.unused == (("plugin", "core.types"),)


def test_a_qualified_grant_reaches_its_whole_subtree():
    deep = ("app.plugin.language", "app.core.ports.sub.deep")
    allowed = {"plugin": ("core.ports",), "core": ()}

    assert check(model(deep), Config(allowed=allowed)).problems == ()


def test_a_qualified_forbidden_target_fires_on_that_subtree_and_nowhere_else():
    config = Config(
        allowed={"plugin": ("core",), "core": ()},
        forbidden=(Forbidden("plugin", "core.desk"),),
    )

    report = check(model(PORTS, TYPES, DESK), config)

    [problem] = report.problems
    assert (problem.kind, problem.components, problem.count) == (
        "forbidden",
        ("plugin", "core.desk"),
        1,
    )
    assert problem.rule == "archview.forbidden"
    assert [i.imported for i in problem.imports] == ["app.core.desk.cast"]


def test_a_qualified_forbidden_target_takes_the_wildcard_source():
    config = Config(allowed={"plugin": "all", "core": ()}, forbidden=(Forbidden("*", "core.desk"),))

    assert kinds(check(model(PORTS, DESK), config)) == [("forbidden", ("plugin", "core.desk"), 1)]


def test_a_qualified_forbidden_source_fires_only_for_imports_from_that_subtree():
    m = model(
        ("app.core.desk.cast", "app.plugin.language"),
        ("app.core.ports.port", "app.plugin.language"),
    )
    config = Config(
        allowed={"core": ("plugin",), "plugin": ()},
        forbidden=(Forbidden("core.desk", "plugin"),),
    )

    report = check(m, config)

    [problem] = report.problems
    assert (problem.kind, problem.components, problem.count) == (
        "forbidden",
        ("core.desk", "plugin"),
        1,
    )
    assert [i.importer for i in problem.imports] == ["app.core.desk.cast"]
    assert not [m for m in notices(report) if "has no modules" in m]


@pytest.mark.parametrize(
    ("config", "where", "name"),
    [
        (
            Config(allowed={"plugin": ("core.portz",), "core": ()}),
            "[archview.allowed.plugin]",
            "core.portz",
        ),
        (
            Config(allowed={"plugin": ("nothing.ports",), "core": ()}),
            "[archview.allowed.plugin]",
            "nothing.ports",
        ),
        (
            Config(forbidden=(Forbidden("plugin", "core.portz"),)),
            "[archview.forbidden]",
            "core.portz",
        ),
        (
            Config(forbidden=(Forbidden("core.portz", "plugin"),)),
            "[archview.forbidden]",
            "core.portz",
        ),
        (
            Config(forbidden=(Forbidden("nothing.x", "plugin"),)),
            "[archview.forbidden]",
            "nothing.x",
        ),
    ],
)
def test_a_qualified_name_that_places_nowhere_is_a_config_error(config, where, name):
    from dataclasses import replace

    with pytest.raises(ConfigError) as error:
        check(model(PORTS, DESK), replace(config, path="archview.toml"))

    message = str(error.value)
    assert message.startswith("archview.toml: ")
    assert where in message
    assert repr(name) in message


def test_a_qualified_name_must_lie_in_the_component_it_starts_with():
    """`[components]` can move a module out of the directory it sits in."""
    config = Config(
        allowed={"plugin": ("core.desk",), "core": (), "desk": ()},
        components={"desk": ("app.core.desk",)},
    )

    with pytest.raises(ConfigError, match="belongs to desk"):
        check(model(PORTS, DESK), config)


def test_a_dotted_outside_name_in_typescript_stays_an_outside_name():
    """npm names may hold a dot (`chart.js`); only Python squashes every outside name."""
    m = model(("web/plugin/a.ts", "web/core/ports/p.ts"), sep="/")

    report = check(m, Config(forbidden=(Forbidden("plugin", "chart.js"),)))

    assert report.problems == ()


def test_a_qualified_grant_in_typescript():
    m = model(
        ("web/plugin/a.ts", "web/core/ports/p.ts"),
        ("web/plugin/a.ts", "web/core/desk/c.ts"),
        sep="/",
    )

    report = check(m, Config(allowed={"plugin": ("core.ports",), "core": ()}))

    assert kinds(report) == [("not_allowed", ("plugin", "core.desk"), 1)]


def test_a_nested_scope_takes_qualified_names_too():
    m = model(
        ("app.svc.plugin.language", "app.svc.core.ports.port"),
        ("app.svc.plugin.images", "app.svc.core.desk.cast"),
    )
    config = Config(
        allowed={"plugin": ("core",), "core": ()}, forbidden=(Forbidden("plugin", "core.desk"),)
    )

    report = check_scope(m, "app.svc", config)

    assert kinds(report) == [("forbidden", ("plugin", "core.desk"), 1)]
    assert not [m for m in notices(report) if "not a child" in m]


def test_layers_take_qualified_names():
    m = model(
        ("app.core.desk.cast", "app.plugin.language"), ("app.core.ports.port", "app.plugin.x")
    )
    config = Config(
        allowed={"core": ("plugin",), "plugin": ()}, layers=(("plugin",), ("core.desk",))
    )

    report = check(m, config)

    assert kinds(report) == [("forbidden", ("core.desk", "plugin"), 1)]
    assert report.problems[0].rule == "archview.layers"
    assert not [m for m in notices(report) if "has no modules" in m]
