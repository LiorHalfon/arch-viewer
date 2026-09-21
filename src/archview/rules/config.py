"""Load and validate the rules file (requirements C1, C2, C11).

The rules live in `archview.toml` under `[archview]`, or in `pyproject.toml` under
`[tool.archview]`. Mistakes are reported with the key path and a suggestion, never
silently ignored: a typo in a rules file would otherwise switch a rule off.
"""

from __future__ import annotations

import difflib
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RULES_FILE = "archview.toml"
ALL = "all"
ALL_COMPONENTS = "*"
STDLIB = sys.stdlib_module_names | {"__future__"}


class ConfigError(Exception):
    """The rules file cannot be used as written."""


@dataclass(frozen=True, slots=True)
class Forbidden:
    """`source` must not import `target`. `origin` names the table that said so."""

    source: str
    target: str
    origin: str = "forbidden"


@dataclass(frozen=True, slots=True)
class MetricRules:
    """Optional thresholds on component metrics (requirement C9)."""

    threshold: float = 0.3
    fail_on_zones: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Exemption:
    """One module-level import the rules tolerate, always with a reason."""

    importer: str
    imported: str
    reason: str


@dataclass(frozen=True, slots=True)
class WorkspaceRules:
    """The `[archview.workspace]` table: rules between the packages of a workspace."""

    packages: tuple[str, ...] = ()
    fail_on_violations: bool = True
    fail_on_cycles: bool = True
    allowed: dict[str, tuple[str, ...] | str] | None = None
    forbidden: tuple[Forbidden, ...] = ()
    exceptions: tuple[Exemption, ...] = ()
    baseline: str | None = None


@dataclass(frozen=True, slots=True)
class Config:
    path: str | None = None
    table: str = "archview"
    package: str | None = None
    language: str | None = None
    tsconfig: str | None = None
    source_roots: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    type_checking_imports: str = "ignore"
    fail_on_violations: bool = True
    fail_on_cycles: bool = True
    allowed: dict[str, tuple[str, ...] | str] | None = None
    externals: dict[str, tuple[str, ...] | str] | None = None
    forbidden: tuple[Forbidden, ...] = ()
    exceptions: tuple[Exemption, ...] = ()
    ignored: tuple[str, ...] = ()
    components: dict[str, tuple[str, ...]] = field(default_factory=dict)
    public: tuple[str, ...] | None = None
    layers: tuple[tuple[str, ...], ...] = ()
    independent: tuple[tuple[str, ...], ...] = ()
    metrics: MetricRules = field(default_factory=MetricRules)
    baseline: str | None = None
    workspace: WorkspaceRules | None = None

    def all_forbidden(self) -> tuple[Forbidden, ...]:
        """`forbidden`, plus what `layers` and `independent` imply (requirement C8)."""
        derived = [
            Forbidden(lower, upper, "layers")
            for i, layer in enumerate(self.layers)
            for upper in (c for above in self.layers[:i] for c in above)
            for lower in layer
        ]
        derived += [
            Forbidden(a, b, "layers")
            for layer in self.layers
            for a in layer
            for b in layer
            if a != b
        ]
        derived += [
            Forbidden(a, b, "independent")
            for group in self.independent
            for a in group
            for b in group
            if a != b
        ]
        return (*self.forbidden, *derived)


ZONES = ("pain", "useless")
LANGUAGES = ("python", "typescript")
TOP_KEYS = {
    "package",
    "language",
    "tsconfig",
    "source_roots",
    "exclude",
    "type_checking_imports",
    "fail_on_violations",
    "fail_on_cycles",
    "allowed",
    "externals",
    "forbidden",
    "exceptions",
    "ignored",
    "components",
    "public",
    "layers",
    "independent",
    "metrics",
    "baseline",
    "workspace",
}
WORKSPACE_KEYS = {
    "packages",
    "fail_on_violations",
    "fail_on_cycles",
    "allowed",
    "forbidden",
    "exceptions",
    "baseline",
}


def find_config(repo: Path) -> Path | None:
    """`archview.toml` wins; otherwise `pyproject.toml` if it has `[tool.archview]`."""
    rules = repo / RULES_FILE
    if rules.is_file():
        return rules
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file() and "archview" in _read_toml(pyproject).get("tool", {}):
        return pyproject
    return None


def load_config(path: Path) -> Config:
    data = _read_toml(path)
    if path.name == "pyproject.toml":
        table, where = data.get("tool", {}).get("archview"), "tool.archview"
    else:
        table, where = data.get("archview"), "archview"
    if not isinstance(table, dict):
        raise ConfigError(f"{path.name}: no [{where}] table")
    return parse_config(table, where=where, path=path.name)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text())
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error.strerror}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path.name}: not valid TOML: {error}") from error


def parse_config(table: dict[str, Any], where: str = "archview", path: str | None = None) -> Config:
    _known_keys(table, TOP_KEYS, where)
    language = _language(table, where)
    tsconfig = _optional_str(table, "tsconfig", where)
    # TypeScript builtins are not stdlib-checked (see the design spec): a declared
    # `tsconfig` or `language = "typescript"` mean names like "queue" are npm packages,
    # not the Python stdlib module of the same name.
    check_stdlib = language != "typescript" and tsconfig is None
    return Config(
        path=path,
        table=where,
        package=_optional_str(table, "package", where),
        language=language,
        tsconfig=tsconfig,
        source_roots=_str_list(table, "source_roots", where),
        exclude=_str_list(table, "exclude", where),
        fail_on_violations=_bool(table, "fail_on_violations", where),
        fail_on_cycles=_bool(table, "fail_on_cycles", where),
        allowed=_allowed(table.get("allowed"), f"{where}.allowed"),
        externals=_externals(table.get("externals"), f"{where}.externals", check_stdlib),
        forbidden=_forbidden(table.get("forbidden", []), f"{where}.forbidden", check_stdlib),
        exceptions=_exceptions(table.get("exceptions", []), f"{where}.exceptions"),
        ignored=_str_list(table, "ignored", where),
        components=_components(table.get("components", {}), f"{where}.components"),
        public=_optional_str_list(table, "public", where),
        type_checking_imports=_choice(
            table, "type_checking_imports", ("ignore", "include"), "ignore", where
        ),
        layers=_layers(table.get("layers", []), f"{where}.layers"),
        independent=tuple(
            _strings(group, f"{where}.independent")
            for group in _list(table.get("independent", []), f"{where}.independent")
        ),
        metrics=_metrics(table.get("metrics", {}), f"{where}.metrics"),
        baseline=_optional_str(table, "baseline", where),
        workspace=_workspace(table.get("workspace"), f"{where}.workspace"),
    )


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(f"[{where}] must be a list")
    return value


def _choice(table: dict[str, Any], key: str, options: tuple[str, ...], default: str, where: str):
    value = table.get(key, default)
    if value not in options:
        raise ConfigError(f"[{where}] {key} must be one of {', '.join(map(repr, options))}")
    return value


def _layers(value: Any, where: str) -> tuple[tuple[str, ...], ...]:
    """Top to bottom; an entry is a component or a list of peers that share a layer."""
    layers = []
    for entry in _list(value, where):
        layers.append((entry,) if isinstance(entry, str) else _strings(entry, where))
    return tuple(layers)


def _metrics(value: Any, where: str) -> MetricRules:
    if not isinstance(value, dict):
        raise ConfigError(f"[{where}] must be a table")
    _known_keys(value, {"threshold", "fail_on_zones", "ignore"}, where)
    threshold = value.get("threshold", 0.3)
    if (
        not isinstance(threshold, int | float)
        or isinstance(threshold, bool)
        or not 0 <= threshold <= 1
    ):
        raise ConfigError(f"[{where}] threshold must be a number between 0 and 1")
    zones = _str_list(value, "fail_on_zones", where)
    for zone in zones:
        if zone not in ZONES:
            raise ConfigError(f"[{where}] fail_on_zones: unknown zone {zone!r}; use {ZONES}")
    return MetricRules(float(threshold), zones, _str_list(value, "ignore", where))


def _known_keys(table: dict[str, Any], known: set[str], where: str) -> None:
    for key in sorted(table):
        if key not in known:
            close = difflib.get_close_matches(key, sorted(known), n=1)
            hint = f"; did you mean {close[0]!r}?" if close else f"; known keys: {sorted(known)}"
            raise ConfigError(f"[{where}] unknown key {key!r}{hint}")


def _optional_str(table: dict[str, Any], key: str, where: str) -> str | None:
    value = table.get(key)
    if value is not None and not isinstance(value, str):
        raise ConfigError(f"[{where}] {key} must be a string")
    return value


def _language(table: dict[str, Any], where: str) -> str | None:
    value = _optional_str(table, "language", where)
    if value is not None and value not in LANGUAGES:
        raise ConfigError(f"[{where}] language must be one of {', '.join(map(repr, LANGUAGES))}")
    return value


def _bool(table: dict[str, Any], key: str, where: str) -> bool:
    value = table.get(key, True)
    if not isinstance(value, bool):
        raise ConfigError(f"[{where}] {key} must be true or false")
    return value


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"[{where}] must be a list of strings")
    return tuple(value)


def _str_list(table: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    return _strings(table.get(key, []), f"{where}.{key}")


def _optional_str_list(table: dict[str, Any], key: str, where: str) -> tuple[str, ...] | None:
    """Like `_str_list`, but an absent key is None rather than an empty tuple.

    `public` needs the distinction: no key means the whole package is public,
    while an empty list means it publishes nothing.
    """
    if key not in table:
        return None
    return _strings(table[key], f"{where}.{key}")


def _allowed(value: Any, where: str) -> dict[str, tuple[str, ...] | str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError(f"[{where}] must be a table: component = [components it may import]")
    allowed: dict[str, tuple[str, ...] | str] = {}
    for component, targets in value.items():
        if targets == ALL:
            allowed[component] = ALL
        else:
            allowed[component] = _strings(targets, f"{where}.{component}")
    return allowed


def _externals(
    value: Any, where: str, check_stdlib: bool
) -> dict[str, tuple[str, ...] | str] | None:
    """Like `allowed`, but the targets are packages outside the project."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError(
            f"[{where}] must be a table: component = [packages outside the project it may import]"
        )
    table = _allowed(value, where)
    if check_stdlib:
        for component, targets in table.items():
            if targets != ALL:
                for name in targets:
                    _reject_stdlib(name, f"{where}.{component}")
    return table


def _reject_stdlib(name: str, where: str) -> None:
    if name.split(".")[0] in STDLIB:
        raise ConfigError(
            f"[{where}] names {name!r}, a stdlib module: stdlib imports are not "
            "analysed, so the rule could never fire"
        )


def _tables(value: Any, where: str, keys: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ConfigError(f"[[{where}]] must be an array of tables")
    for item in value:
        _known_keys(item, keys, where)
        for key in sorted(keys):
            if not isinstance(item.get(key), str) or not item[key]:
                raise ConfigError(f"[[{where}]] every entry needs a non-empty {key!r}")
    return value


def _forbidden(value: Any, where: str, check_stdlib: bool) -> tuple[Forbidden, ...]:
    items = _tables(value, where, {"from", "to"})
    if check_stdlib:
        for item in items:
            _reject_stdlib(item["to"], where)
    return tuple(Forbidden(i["from"], i["to"]) for i in items)


def _exceptions(value: Any, where: str) -> tuple[Exemption, ...]:
    items = _tables(value, where, {"importer", "imported", "reason"})
    return tuple(Exemption(i["importer"], i["imported"], i["reason"]) for i in items)


def _components(value: Any, where: str) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise ConfigError(f"[{where}] must be a table: component = [module patterns]")
    return {name: _strings(patterns, f"{where}.{name}") for name, patterns in value.items()}


def _workspace(value: Any, where: str) -> WorkspaceRules | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError(f"[{where}] must be a table")
    _known_keys(value, WORKSPACE_KEYS, where)
    return WorkspaceRules(
        packages=_str_list(value, "packages", where),
        fail_on_violations=_bool(value, "fail_on_violations", where),
        fail_on_cycles=_bool(value, "fail_on_cycles", where),
        allowed=_allowed(value.get("allowed"), f"{where}.allowed"),
        # Targets here are sibling package names, never stdlib modules.
        forbidden=_forbidden(value.get("forbidden", []), f"{where}.forbidden", check_stdlib=False),
        exceptions=_exceptions(value.get("exceptions", []), f"{where}.exceptions"),
        baseline=_optional_str(value, "baseline", where),
    )
