"""Finding the top-level packages of a repo, so the CLI needs no configuration (V13)."""

from pathlib import Path

from archview.extract.discover import find_packages

FIXTURES = Path(__file__).parent / "fixtures"


def make(root: Path, *files: str) -> Path:
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    return root


def test_finds_a_package_that_sits_at_the_repo_root():
    assert find_packages(FIXTURES) == {"sample": FIXTURES}


def test_finds_packages_under_a_src_directory(tmp_path):
    make(tmp_path, "src/myapp/__init__.py", "src/myapp/core.py")

    assert find_packages(tmp_path) == {"myapp": tmp_path / "src"}


def test_treats_src_itself_as_the_package_when_it_has_an_init(tmp_path):
    make(tmp_path, "src/__init__.py", "src/webapp/__init__.py")

    assert find_packages(tmp_path) == {"src": tmp_path}


def test_skips_tests_and_build_directories(tmp_path):
    make(tmp_path, "myapp/__init__.py", "tests/__init__.py", "build/__init__.py")

    assert find_packages(tmp_path) == {"myapp": tmp_path}


def test_returns_nothing_for_a_repo_with_no_python_packages(tmp_path):
    make(tmp_path, "README.md", "web/index.html")

    assert find_packages(tmp_path) == {}


def test_prefers_the_src_copy_when_a_name_exists_in_both_places(tmp_path):
    make(tmp_path, "src/myapp/__init__.py", "myapp/__init__.py")

    assert find_packages(tmp_path) == {"myapp": tmp_path / "src"}
