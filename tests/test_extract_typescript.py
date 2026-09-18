"""The TypeScript extractor's Python half: compiler facts turned into the model (ADR 0010)."""

import pytest

from archview.extract.typescript import Target, build_model, classify, find_source_root


def fact(specifier, resolved=None, line=1, **flags):
    return {
        "specifier": specifier,
        "resolved": resolved,
        "line": line,
        "text": f'import x from "{specifier}";',
        "type_only": False,
        "lazy": False,
        "dynamic": False,
        "builtin": False,
        "alias": False,
        **flags,
    }


def facts(*files):
    """`files`: (path, imports) or (path, imports, abstract)."""
    return {
        "files": [
            {"file": f[0], "imports": list(f[1]), "abstract": f[2] if len(f) > 2 else False}
            for f in files
        ]
    }


def test_ids_keep_the_extension_and_directories_become_packages():
    m = build_model(
        facts(
            ("components/ui/Button.tsx", []), ("components/ui/Button.web.tsx", []), ("i18n.ts", [])
        ),
        "app",
    )

    assert (m.language, m.separator, m.project) == ("typescript", "/", "app")
    assert [(n.id, n.parent, n.kind, n.file) for n in m.nodes] == [
        ("app", None, "package", None),
        ("app/components", "app", "package", None),
        ("app/components/ui", "app/components", "package", None),
        ("app/components/ui/Button.tsx", "app/components/ui", "module", "components/ui/Button.tsx"),
        (
            "app/components/ui/Button.web.tsx",
            "app/components/ui",
            "module",
            "components/ui/Button.web.tsx",
        ),
        ("app/i18n.ts", "app", "module", "i18n.ts"),
    ]


def test_a_file_next_to_a_directory_of_the_same_name_does_not_clash():
    m = build_model(
        facts(("components/T/T.tsx", []), ("components/T/T/Fade.tsx", []), ("utils/x.ts", [])),
        "app",
    )

    assert {(n.id, n.kind) for n in m.nodes} >= {
        ("app/components/T/T", "package"),
        ("app/components/T/T.tsx", "module"),
    }


def test_the_one_top_level_directory_holding_every_file_is_the_source_root():
    m = build_model(facts(("src/a.ts", []), ("src/b/c.ts", [])), "hono")

    assert [(n.id, n.file) for n in m.nodes] == [
        ("hono", None),
        ("hono/a.ts", "src/a.ts"),
        ("hono/b", None),
        ("hono/b/c.ts", "src/b/c.ts"),
    ]
    assert find_source_root(["a.ts", "src/b.ts"]) == ""
    assert find_source_root(["src/a.ts", "lib/b.ts"]) == ""
    assert find_source_root([]) == ""


def test_root_config_files_are_left_out_before_the_source_root_is_chosen():
    m = build_model(facts(("vite.config.ts", []), ("src/a.ts", [])), "p")

    assert [n.id for n in m.nodes] == ["p", "p/a.ts"]


def test_a_given_source_root_drops_the_files_outside_it():
    m = build_model(
        facts(("src/a.ts", [fact("../scripts/x", resolved="scripts/x.ts")]), ("scripts/x.ts", [])),
        "p",
        source_root="src",
    )

    assert [n.id for n in m.nodes] == ["p", "p/a.ts"]
    assert m.imports == ()


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (fact("@/utils/x", resolved="utils/x.ts"), Target("internal", "utils/x.ts")),
        (fact("../legacy.js", resolved="legacy.js"), Target("internal", "legacy.js")),
        (fact("./global", resolved="global.d.ts"), Target("drop")),
        (fact("./data.json", resolved="data.json"), Target("drop")),
        (fact("node:fs", builtin=True), Target("drop")),
        (fact("@/assets/icon.png", alias=True), Target("drop")),
        (fact("./missing"), Target("unresolved")),
        (fact("@/utils/missing", alias=True), Target("unresolved")),
        (fact(None, dynamic=True), Target("dynamic")),
        (fact("react"), Target("external", "react")),
        (fact("@expo/vector-icons/Ionicons"), Target("external", "@expo/vector-icons")),
        (
            fact("react", resolved="node_modules/@types/react/index.d.ts"),
            Target("external", "react"),
        ),
        (
            fact(
                "@tanstack/react-query",
                resolved="node_modules/.pnpm/@tanstack+react-query@5.90.2/node_modules/"
                "@tanstack/react-query/build/modern/index.js",
            ),
            Target("external", "@tanstack/react-query"),
        ),
        (fact("@acme/ui", resolved="../ui/src/index.ts"), Target("external", "@acme/ui")),
        (fact("../../shared/x", resolved="../shared/x.ts"), Target("external", "../shared")),
        (
            fact("~/vendor/lib", resolved="node_modules/some-lib/index.js", alias=False),
            Target("external", "some-lib"),
        ),
    ],
)
def test_classifies_every_kind_of_specifier(given, expected):
    assert classify(given) == expected


def test_imports_carry_flags_and_externals_come_after_the_internal_nodes():
    m = build_model(
        facts(
            (
                "a.ts",
                [
                    fact("./b", resolved="b.ts", line=2, type_only=True),
                    fact("react", line=3),
                    fact("./c", resolved="c.ts", line=4, lazy=True),
                ],
            ),
            ("b.ts", []),
            ("c.ts", []),
        ),
        "p",
    )

    assert [
        (i.importer, i.imported, i.file, i.line, i.type_checking, i.lazy) for i in m.imports
    ] == [
        ("p/a.ts", "p/b.ts", "a.ts", 2, True, False),
        ("p/a.ts", "p/c.ts", "a.ts", 4, False, True),
        ("p/a.ts", "react", "a.ts", 3, False, False),
    ]
    assert (m.nodes[-1].id, m.nodes[-1].parent, m.nodes[-1].kind) == ("react", None, "external")


def test_a_resolved_internal_file_outside_the_file_list_becomes_a_module():
    m = build_model(facts(("a.ts", [fact("./legacy.js", resolved="legacy.js")])), "p")

    assert ("p/legacy.js", "module", "legacy.js") in {(n.id, n.kind, n.file) for n in m.nodes}
    assert [(i.importer, i.imported) for i in m.imports] == [("p/a.ts", "p/legacy.js")]


def test_dynamic_and_unresolved_imports_become_warnings():
    m = build_model(
        facts(
            (
                "a.ts",
                [
                    fact(None, line=5, dynamic=True, text="return import(name);"),
                    fact("./missing", line=2),
                ],
            )
        ),
        "p",
    )

    assert [(w.kind, w.module, w.file, w.line, w.target) for w in m.warnings] == [
        ("unresolved_import", "p/a.ts", "a.ts", 2, "./missing"),
        ("dynamic_import", "p/a.ts", "a.ts", 5, None),
    ]
    assert m.imports == ()


def test_abstract_comes_from_the_facts():
    m = build_model(facts(("types.ts", [], True), ("order.ts", [])), "p")

    assert {n.id: n.abstract for n in m.nodes if n.file} == {
        "p/order.ts": False,
        "p/types.ts": True,
    }
