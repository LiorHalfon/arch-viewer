"""The ast pass: import context, abstractness and dynamic imports (A4, A5, A9; ADR 0002)."""

from textwrap import dedent

from archview.extract.facts import scan


def facts(source: str):
    return scan(dedent(source))


def test_flags_imports_under_type_checking():
    f = facts("""
        from typing import TYPE_CHECKING
        import typing
        if TYPE_CHECKING:
            from a import b
        if typing.TYPE_CHECKING:
            import c
        else:
            import d
    """)

    assert f.flags(5) == {"type_checking"}
    assert f.flags(7) == {"type_checking"}
    assert f.flags(9) == set()


def test_flags_imports_inside_functions_as_lazy_but_not_class_bodies():
    f = facts("""
        def load():
            import a
        async def fetch():
            from b import c
        class K:
            import d
            def m(self):
                if True:
                    import e
    """)

    assert f.flags(3) == {"lazy"}
    assert f.flags(5) == {"lazy"}
    assert f.flags(7) == set()
    assert f.flags(10) == {"lazy"}


def test_a_multi_line_import_is_found_by_its_first_line():
    f = facts("""
        def load():
            from a import (
                b,
                c,
            )
    """)

    assert f.flags(3) == {"lazy"}


def test_protocols_and_abcs_make_a_module_abstract():
    for source in (
        "from typing import Protocol\nclass Port(Protocol):\n    def get(self): ...\n",
        "import typing\nclass Port(typing.Protocol[T]):\n    pass\n",
        "from abc import ABC\nclass Base(ABC):\n    pass\n",
        "import abc\nclass Base(metaclass=abc.ABCMeta):\n    pass\n",
        "from abc import abstractmethod\nclass Base:\n    @abstractmethod\n    def run(s): ...\n",
    ):
        assert scan(source).abstract, source


def test_a_plain_module_is_not_abstract():
    assert not facts("class Order:\n    amount: int\n").abstract


def test_reports_dynamic_imports_with_their_literal_target():
    f = facts("""
        import importlib
        from importlib import import_module
        def load(name):
            importlib.import_module("pkg.plugins.x")
            import_module(name)
            return __import__("os")
    """)

    assert [(d.line, d.target) for d in f.dynamic] == [
        (5, "pkg.plugins.x"),
        (6, None),
        (7, "os"),
    ]
    assert f.dynamic[0].text == 'importlib.import_module("pkg.plugins.x")'


def test_unparseable_source_yields_no_facts():
    f = scan("def broken(:\n")

    assert (f.abstract, f.dynamic, f.flags(1)) == (False, (), set())
