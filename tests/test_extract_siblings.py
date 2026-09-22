"""The multi-package pass that recovers what grimp squashes (issue #4).

A single package's model records `plugin.adapter -> core` whichever part of `core`
was imported, because grimp squashes an external import to its top-level name. One
graph over the packages together resolves the real target.
"""

from __future__ import annotations

from pathlib import Path

from archview.extract.siblings import resolve_targets


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def two_packages(tmp_path: Path) -> dict[str, Path]:
    write(tmp_path, "core/src/core/__init__.py", "")
    write(tmp_path, "core/src/core/model.py", "class Thing: ...\n")
    write(tmp_path, "core/src/core/ports.py", "class Port: ...\n")
    write(tmp_path, "plugin/src/plugin/__init__.py", "")
    write(
        tmp_path,
        "plugin/src/plugin/adapter.py",
        "from core.ports import Port\nfrom core.model import Thing\nfrom core import model as m2\n",
    )
    return {"core": tmp_path / "core" / "src", "plugin": tmp_path / "plugin" / "src"}


def test_a_deep_import_resolves_to_the_exact_module(tmp_path):
    found = resolve_targets(two_packages(tmp_path))
    assert found[("plugin.adapter", 1)] == "core.ports"
    assert found[("plugin.adapter", 2)] == "core.model"


def test_an_aliased_re_export_resolves_too(tmp_path):
    """`from core import model as m2` names only `core` but reaches `core.model`.

    This is the case that rules out reading the import line as text.
    """
    assert resolve_targets(two_packages(tmp_path))[("plugin.adapter", 3)] == "core.model"


def test_a_third_party_import_is_not_reported(tmp_path):
    roots = two_packages(tmp_path)
    write(tmp_path, "plugin/src/plugin/other.py", "import networkx\n")
    found = resolve_targets(roots)
    assert not [t for t in found.values() if t.startswith("networkx")]


def test_an_import_inside_one_package_is_not_reported(tmp_path):
    """Only edges that cross a package line matter here."""
    roots = two_packages(tmp_path)
    write(tmp_path, "core/src/core/ports.py", "from core.model import Thing\n")
    found = resolve_targets(roots)
    assert not [k for k in found if k[0].startswith("core.")]


def test_the_result_is_deterministic(tmp_path):
    roots = two_packages(tmp_path)
    assert list(resolve_targets(roots).items()) == list(resolve_targets(roots).items())


def test_sys_path_is_left_as_it_was(tmp_path):
    import sys

    before = list(sys.path)
    resolve_targets(two_packages(tmp_path))
    assert sys.path == before


def test_a_member_name_already_imported_elsewhere_still_resolves(tmp_path):
    """A member name colliding with something already imported in this process must
    not make `resolve_targets` resolve against the wrong location.

    `importlib.util.find_spec`, which grimp uses to locate each top-level package,
    returns an already-imported module's cached spec without consulting `sys.path`
    at all - so a process that has ever imported a same-named module from elsewhere
    would otherwise silently resolve cross-package imports against the wrong
    package (issue #10's `tests` collides with pytest's own `tests` package for
    exactly this reason; here the collision is made real rather than mocked)."""
    import importlib
    import sys

    decoy = tmp_path / "decoy"
    write(decoy, "core/__init__.py", "")
    sys.path.insert(0, str(decoy))
    try:
        importlib.import_module("core")
    finally:
        sys.path.remove(str(decoy))
    assert Path(sys.modules["core"].__file__) == decoy / "core" / "__init__.py"
    try:
        found = resolve_targets(two_packages(tmp_path))
        assert found[("plugin.adapter", 1)] == "core.ports"
        assert found[("plugin.adapter", 2)] == "core.model"
    finally:
        del sys.modules["core"]


def test_a_non_path_entry_in_path_does_not_crash_the_guard(tmp_path):
    """A foreign package can put anything into `__path__` - not only a plain string
    or `os.PathLike` - since Python never enforces its contents. `Path(p)` raises
    `TypeError` on anything else, which would take down an extraction that
    previously worked (Fix 6, review). An unrecognised entry is treated as not a
    match - the safe direction, since it still lets the real collision cases evict."""
    from archview.extract.siblings import _elsewhere

    class Weird:
        """Not a str and not an os.PathLike."""

    class FakeModule:
        __path__ = (Weird(),)

    assert _elsewhere(FakeModule(), tmp_path, "weird") is True
