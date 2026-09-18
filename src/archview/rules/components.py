"""Which component a module belongs to (requirement C2).

By default a component is a direct child of the project package: `shop.api.routes`
belongs to `api`, and the project's own root module to a component named after the
project. Explicit `[components]` patterns take precedence; when several match, the
most specific pattern wins, then the component name.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from archview.model.patterns import matches_name, specificity


@dataclass(frozen=True, slots=True)
class ComponentMap:
    project: str
    explicit: Mapping[str, tuple[str, ...]]
    ignored: frozenset[str] = frozenset()

    def of(self, module: str) -> str | None:
        """The component `module` belongs to, or None if it is outside the project or ignored."""
        component = self._explicit(module) or self._default(module)
        return None if component in self.ignored else component

    def _explicit(self, module: str) -> str | None:
        hits = [
            (specificity(pattern, "."), name)
            for name, patterns in self.explicit.items()
            for pattern in patterns
            if matches_name(pattern, module, ".")
        ]
        if not hits:
            return None
        best = max(score for score, _ in hits)
        return min(name for score, name in hits if score == best)

    def _default(self, module: str) -> str | None:
        if module == self.project:
            return self.project
        prefix = self.project + "."
        if not module.startswith(prefix):
            return None
        return module[len(prefix) :].split(".")[0]

    def unmatched_patterns(self, modules: Iterable[str]) -> list[tuple[str, str]]:
        """(component, pattern) pairs that match no module - usually a typo."""
        names = sorted(modules)
        return [
            (name, pattern)
            for name, patterns in sorted(self.explicit.items())
            for pattern in patterns
            if not any(matches_name(pattern, m, ".") for m in names)
        ]
