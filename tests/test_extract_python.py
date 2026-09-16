"""The Python extractor: grimp's import graph turned into the model (A1-A3, A6)."""

from pathlib import Path

import pytest

from archview.extract.python import build_model

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def sample():
    return build_model("sample", FIXTURES)


def test_builds_a_node_for_every_package_and_module_in_the_tree(sample):
    assert [(n.id, n.kind) for n in sample.nodes] == [
        ("sample", "package"),
        ("sample.api", "package"),
        ("sample.api.routes", "module"),
        ("sample.domain", "package"),
        ("sample.domain.model", "module"),
        ("sample.infra", "package"),
        ("sample.infra.cache", "module"),
        ("sample.infra.db", "module"),
        ("sample.services", "package"),
        ("sample.services.pricing", "module"),
    ]


def test_records_the_source_file_of_packages_and_modules(sample):
    files = {n.id: n.file for n in sample.nodes}
    assert files["sample.api"] == "sample/api/__init__.py"
    assert files["sample.api.routes"] == "sample/api/routes.py"


def test_resolves_from_package_import_module_to_that_module(sample):
    assert ("sample.services.pricing", "sample.domain.model") in {
        (i.importer, i.imported) for i in sample.imports
    }


def test_resolves_from_package_import_attribute_to_the_package(sample):
    assert ("sample.api.routes", "sample.domain") in {
        (i.importer, i.imported) for i in sample.imports
    }


def test_records_the_file_and_line_behind_each_import(sample):
    imp = next(
        i
        for i in sample.imports
        if (i.importer, i.imported) == ("sample.api.routes", "sample.services.pricing")
    )
    assert (imp.file, imp.line, imp.text) == (
        "sample/api/routes.py",
        11,
        "from sample.services import pricing",
    )


def test_captures_imports_written_inside_a_function(sample):
    assert ("sample.services.pricing", "sample.infra.cache") in {
        (i.importer, i.imported) for i in sample.imports
    }


def test_ignores_stdlib_and_third_party_imports(sample):
    outside = {i.imported for i in sample.imports if not i.imported.startswith("sample")}
    assert outside == set()


def test_does_not_leave_the_analysed_project_on_the_import_path(sample):
    import sys

    assert str(FIXTURES) not in sys.path
