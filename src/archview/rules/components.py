"""Which component a module belongs to (requirement C2).

By default a component is a direct child of the project package: `shop.api.routes`
belongs to `api`, as `shop/api/routes.ts` does, and the project's own root module to a
component named after the project. Explicit `[components]` patterns take precedence;
when several match, the most specific pattern wins, then the component name. A module
outside the project belongs to no component, but has an outside name of its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from archview.model.names import within
from archview.model.patterns import matches_name, specificity


@dataclass(frozen=True, slots=True)
class ComponentMap:
    project: str
    sep: str
    explicit: Mapping[str, tuple[str, ...]]
    ignored: frozenset[str] = frozenset()

    def of(self, module: str) -> str | None:
        """The component `module` belongs to, or None if it is outside the project or ignored."""
        component = self._explicit(module) or self._default(module)
        return None if component in self.ignored else component

    def outside(self, module: str) -> str | None:
        """The outside package `module` belongs to, or None if it is inside the project.

        `module` is already the extractor's own squashed external id - grimp collapses
        a deep Python import (`openai.types.chat`) to its top-level package (`openai`)
        before this ever runs, and TypeScript's `_external_name` does the equivalent for
        npm imports. Splitting it again here would be wrong for a squashed id that still
        contains `sep` for a reason other than depth: a scoped npm name (`@scope/pkg`)
        or a workspace's `../sibling` outside name (M8) would be cut down to `@scope` or
        `..`.
        """
        if module == self.project or within(module, self.project, self.sep):
            return None
        return None if module in self.ignored else module

    def _explicit(self, module: str) -> str | None:
        hits = [
            (specificity(pattern, self.sep), name)
            for name, patterns in self.explicit.items()
            for pattern in patterns
            if matches_name(pattern, module, self.sep)
        ]
        if not hits:
            return None
        best = max(score for score, _ in hits)
        return min(name for score, name in hits if score == best)

    def _default(self, module: str) -> str | None:
        if module == self.project:
            return self.project
        if not within(module, self.project, self.sep):
            return None
        return module[len(self.project) + 1 :].split(self.sep)[0]

    def unmatched_patterns(self, modules: Iterable[str]) -> list[tuple[str, str]]:
        """(component, pattern) pairs that match no module - usually a typo."""
        names = sorted(modules)
        return [
            (name, pattern)
            for name, patterns in sorted(self.explicit.items())
            for pattern in patterns
            if not any(matches_name(pattern, m, self.sep) for m in names)
        ]
