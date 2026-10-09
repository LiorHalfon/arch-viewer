"""Qualified names in rules: `core.ports` names one part of `core` (issue #17, ADR 0018).

The meaning is the same in both modes. In a workspace `core` is a package and the
part is one of its components; in a single package `core` is a component and the
part is a module or sub-package inside it. In both:

- A grant may name parts. When a source's grants name parts of `core`, an import
  into `core` must land inside one of those parts; a plain `core` beside them adds
  nothing, and an import of `core`'s own root module is outside every part.
- Whatever checks whole components or packages sees a qualified grant as its owner,
  so it does not deny the very import the grant exists to permit.
- A part covers its whole subtree, compared by name.

The workspace places each cross-package import itself (ADR 0013); a single package
names a module by its path below the project, written with dots.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from archview.model.graph import Model
from archview.model.names import within
from archview.rules.components import ComponentMap
from archview.rules.config import ALL, ALL_COMPONENTS, Config, ConfigError

SEP = "."
Grants = tuple[str, ...] | str | None


def owner(name: str) -> str:
    """`core.ports` -> `core`; `core` -> `core`."""
    return name.split(SEP, 1)[0]


def part(name: str) -> str:
    """`core.desk.cast` -> `core.desk`: a name cut to its owner and one part."""
    return SEP.join(name.split(SEP)[:2])


def is_qualified(name: str, known: Collection[str] = ()) -> bool:
    """A dotted name that is not itself a component or package name."""
    return SEP in name and name not in known


def narrowing(grants: Grants, target: str, known: Collection[str] = ()) -> tuple[str, ...]:
    """The parts of `target` that `grants` names; empty when they name no part of it."""
    if grants is None or grants == ALL:
        return ()
    return tuple(g for g in grants if is_qualified(g, known) and owner(g) == target)


def admitted(reached: str, parts: Iterable[str]) -> bool:
    """True if `reached` lies inside one of `parts`."""
    return any(within(reached, p, SEP) for p in parts)


def widened(
    allowed: dict[str, tuple[str, ...] | str], known: Collection[str] = ()
) -> dict[str, tuple[str, ...] | str]:
    """`allowed` as a check of whole components or packages sees it: each part as its owner."""
    return {
        source: targets
        if targets == ALL
        else tuple(sorted({owner(t) if is_qualified(t, known) else t for t in targets}))
        for source, targets in allowed.items()
    }


@dataclass(frozen=True, slots=True)
class Names:
    """How one rules file names the modules of one model.

    `app.core.ports.port` in project `app` is `core.ports.port`; a TypeScript
    `web/core/ports/p.ts` is `core.ports.p.ts`. In Python every dotted name that is
    not a component is qualified, because an outside name is always squashed to its
    top level. In TypeScript a dotted name is qualified only when it starts with a
    component, since an npm package may have a dot in its name (`chart.js`).
    """

    project: str
    sep: str
    components: frozenset[str]
    known: frozenset[str]

    def relative(self, module: str) -> str:
        if module != self.project and within(module, self.project, self.sep):
            module = module[len(self.project) + len(self.sep) :]
        return module.replace(self.sep, SEP)

    def qualified(self, name: str) -> bool:
        if not is_qualified(name, self.known):
            return False
        return self.sep == SEP or owner(name) in self.components

    def reached(self, module: str, component: str) -> str:
        """The part of `component` an import of `module` lands in, as a report names it."""
        name = self.relative(module)
        return part(name) if owner(name) == component else component


def names_of(config: Config, model: Model, components: ComponentMap, present: tuple[str, ...]):
    """The `Names` for `config` on `model`, once every qualified name it uses is placed.

    A qualified name must start with a component and name a module or package of
    that component; anything else is a `ConfigError` naming the file, the key and the
    name. A rule that names nothing archview can place would otherwise never fire.
    """
    known = {*present, model.project, *config.components, *(config.allowed or {})}
    names = Names(model.project, model.separator, frozenset(present), frozenset(known))
    modules: dict[str, str] = {}
    for node in sorted(model.nodes, key=lambda n: n.id):
        if node.kind != "external" and node.id != model.project:
            modules.setdefault(names.relative(node.id), node.id)
    for where, name in _used(config):
        if names.qualified(name):
            _place(name, where, names, modules, components, config)
    return names


def _used(config: Config) -> list[tuple[str, str]]:
    """(key, name) for every name in an `allowed` value or a `forbidden` rule."""
    table = config.table
    used = [
        (f"[{table}.allowed.{source}]", name)
        for source, targets in sorted((config.allowed or {}).items())
        if targets != ALL
        for name in targets
    ]
    for f in config.all_forbidden():
        used += [(f"[{table}.{f.origin}] from", f.source), (f"[{table}.{f.origin}] to", f.target)]
    return [(where, name) for where, name in used if name != ALL_COMPONENTS]


def _place(
    name: str,
    where: str,
    names: Names,
    modules: dict[str, str],
    components: ComponentMap,
    config: Config,
) -> None:
    prefix = f"{config.path}: " if config.path else ""
    said = f"{prefix}{where} names {name!r}"
    component = owner(name)
    if component not in names.components:
        raise ConfigError(
            f"{said}, but {component!r} is not a component; a qualified name is a "
            "component, a dot, and a module or package inside it"
        )
    module = modules.get(name)
    if module is None:
        expected = names.sep.join((names.project, *name.split(SEP)))
        raise ConfigError(f"{said}, but there is no module or package {expected}")
    belongs = components.of(module)
    if belongs != component:
        raise ConfigError(f"{said}, but {module} belongs to {belongs}, not {component}")
