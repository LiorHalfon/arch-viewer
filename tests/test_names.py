"""Hierarchy on node ids, for '.' (Python) and '/' (TypeScript) alike."""

import pytest

from archview.model.names import ancestors, last, parent, truncate, within


@pytest.mark.parametrize(
    ("name", "ancestor", "sep", "expected"),
    [
        ("app.api.routes", "app.api", ".", True),
        ("app.api", "app.api", ".", True),
        ("app.apis", "app.api", ".", False),
        ("app/components/Button.tsx", "app/components", "/", True),
        ("app/components.tsx", "app/components", "/", False),
        ("app/ui/Button.web.tsx", "app/ui/Button", "/", False),
    ],
)
def test_within_needs_the_separator_after_the_ancestor(name, ancestor, sep, expected):
    assert within(name, ancestor, sep) is expected


def test_parent_ancestors_last_and_truncate_split_on_the_given_separator():
    assert parent("app/ui/Button.web.tsx", "/") == "app/ui"
    assert parent("app", "/") is None
    assert ancestors("app/ui/Button.web.tsx", "/") == ["app", "app/ui", "app/ui/Button.web.tsx"]
    assert ancestors("app.api.routes", ".") == ["app", "app.api", "app.api.routes"]
    assert last("app/ui/Button.web.tsx", "/") == "Button.web.tsx"
    assert last("app.api.routes", ".") == "routes"
    assert truncate("app/ui/Button.tsx", 2, "/") == "app/ui"
