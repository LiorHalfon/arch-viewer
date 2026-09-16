"""Glob patterns for components (C2) and exclusions (A11)."""

import pytest

from archview.model.patterns import matches_name, matches_path


@pytest.mark.parametrize(
    ("pattern", "name", "expected"),
    [
        ("app.db", "app.db", True),
        ("app.db", "app.db.session", True),
        ("app.db", "app.dbx", False),
        ("app.*", "app.api.routes", True),
        ("app.*_client", "app.http_client", True),
        ("app.*_client", "app.http.client", False),
        ("**.legacy", "app.billing.legacy.export", True),
        ("app.**.models", "app.models", True),
        ("app.**.models", "app.a.b.models", True),
    ],
)
def test_matches_dotted_names_and_their_subtrees(pattern, name, expected):
    assert matches_name(pattern, name) is expected


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("**/tests/**", "src/app/tests/test_x.py", True),
        ("**/tests/**", "tests/test_x.py", True),
        ("**/tests/**", "src/app/contests/x.py", False),
        ("src/app/*.py", "src/app/main.py", True),
        ("src/app/*.py", "src/app/sub/main.py", False),
        ("**/migrations/*", "app/migrations/0001.py", True),
    ],
)
def test_matches_file_paths(pattern, path, expected):
    assert matches_path(pattern, path) is expected
