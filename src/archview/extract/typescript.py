"""Turn what the TypeScript compiler reports into the model (ADR 0010).

`typescript.mjs` runs in Node with the analysed repo's own `typescript` package and
prints raw facts per file (see `read_facts`); every decision about ids, kinds,
externals and warnings is made here. Ids are paths below the source root, prefixed by
the project and keeping the file extension, split by '/'.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from archview.model.graph import ExtractionWarning, Import, Model, Node
from archview.model.names import ancestors, parent

SEP = "/"
CODE = re.compile(r"\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$")
DECLARATION = re.compile(r"\.d\.(ts|mts|cts)$")
NON_CODE = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|avif|ico|bmp|css|scss|sass|less|json|md|mdx|html|txt"
    r"|woff2?|ttf|otf|eot|mp3|mp4|wav|webm|lottie|riv|wasm|graphql|gql|ya?ml)$",
    re.IGNORECASE,
)
ROOT_CONFIG = re.compile(r"^[^/]*\.config\.[^/]+$")  # vite.config.ts, next.config.mjs


@dataclass(frozen=True, slots=True)
class Target:
    """Where one import goes: `internal` (a repo file), `external` (an npm package),
    `drop` (builtin, declaration, asset), `unresolved` or `dynamic` (warnings)."""

    kind: str
    name: str | None = None


def _package_name(specifier: str) -> str:
    """`react-native/Libraries/x` -> `react-native`; `@expo/vector-icons/x` -> `@expo/vector-icons`."""  # noqa: E501
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") and len(parts) > 1 else parts[0]


def _is_bare(specifier: str) -> bool:
    return not specifier.startswith((".", "/"))


def _external_name(specifier: str, resolved: str) -> str:
    """The package a bare specifier names; else the package or folder the file sits in."""
    if _is_bare(specifier) and not specifier.startswith("~"):
        return _package_name(specifier)
    parts = resolved.split("/")
    if "node_modules" in parts:
        last = max(i for i, p in enumerate(parts) if p == "node_modules")
        return _package_name("/".join(parts[last + 1 :]))
    ups = next((i for i, p in enumerate(parts) if p != ".."), len(parts) - 1)
    return SEP.join(parts[: ups + 1])


def classify(fact: dict[str, Any]) -> Target:
    specifier, resolved = fact["specifier"], fact["resolved"]
    if fact["dynamic"]:
        return Target("dynamic")
    if fact["builtin"]:
        return Target("drop")
    if resolved is not None:
        return _resolved_target(specifier, resolved)
    if NON_CODE.search(specifier.split("?")[0]):
        return Target("drop")
    if not _is_bare(specifier) or fact["alias"]:
        return Target("unresolved")
    return Target("external", _package_name(specifier))


def _resolved_target(specifier: str, resolved: str) -> Target:
    if "node_modules" in resolved.split("/") or resolved.startswith("../"):
        return Target("external", _external_name(specifier, resolved))
    if DECLARATION.search(resolved) or not CODE.search(resolved):
        return Target("drop")
    return Target("internal", resolved)


def find_source_root(files: Iterable[str]) -> str:
    """The one top-level directory every file lies under (`src`), else '' (the repo)."""
    tops = {f.split(SEP)[0] if SEP in f else "" for f in files}
    return next(iter(tops)) if len(tops) == 1 and "" not in tops else ""


def _below(file: str, root: str) -> bool:
    return not root or file.startswith(root + SEP)


def build_model(facts: dict[str, Any], project: str, source_root: str | None = None) -> Model:
    """The model of one TypeScript project; `source_root` (relative to the repo) is
    found with `find_source_root` when not given, and files outside it are left out."""
    files = {f["file"]: f for f in facts["files"] if not ROOT_CONFIG.match(f["file"])}
    targets = {
        (file, index): classify(fact)
        for file, entry in files.items()
        for index, fact in enumerate(entry["imports"])
    }
    internal = set(files) | {
        t.name
        for t in targets.values()
        if t.kind == "internal" and t.name and not ROOT_CONFIG.match(t.name)
    }
    root = find_source_root(internal) if source_root is None else source_root.strip(SEP)
    ids = {
        file: f"{project}{SEP}{file[len(root) + 1 :] if root else file}"
        for file in sorted(internal)
        if _below(file, root)
    }
    imports, warnings = _imports(files, targets, ids, project)
    externals = sorted({i.imported for i in imports} - set(ids.values()))
    return Model(
        project=project,
        nodes=(*_tree(project, ids, files), *(Node(e, None, "external") for e in externals)),
        imports=tuple(sorted(imports, key=lambda i: (i.importer, i.imported, i.line))),
        language="typescript",
        warnings=tuple(sorted(warnings, key=lambda w: (w.module, w.line))),
        separator=SEP,
    )


def _tree(project: str, ids: dict[str, str], files: dict[str, Any]) -> list[Node]:
    """The project, every directory on the way to a file, and the files."""
    nodes = {project: Node(project, None, "package")}
    for file, node_id in ids.items():
        for directory in ancestors(node_id, SEP)[1:-1]:
            nodes.setdefault(directory, Node(directory, parent(directory, SEP), "package"))
        abstract = bool(files.get(file, {}).get("abstract"))
        nodes[node_id] = Node(node_id, parent(node_id, SEP), "module", file, abstract)
    return sorted(nodes.values(), key=lambda n: n.id)


def _imports(files, targets, ids, project) -> tuple[list[Import], list[ExtractionWarning]]:
    imports: list[Import] = []
    warnings: list[ExtractionWarning] = []
    for file in sorted(f for f in files if f in ids):
        importer = ids[file]
        for index, fact in enumerate(files[file]["imports"]):
            target = targets[(file, index)]
            if target.kind in ("dynamic", "unresolved"):
                kind = "dynamic_import" if target.kind == "dynamic" else "unresolved_import"
                warnings.append(
                    ExtractionWarning(
                        kind, importer, file, fact["line"], fact["text"], fact["specifier"]
                    )
                )
                continue
            imported = _imported(target, ids, project)
            if imported is None or imported == importer:
                continue
            imports.append(
                Import(
                    importer,
                    imported,
                    file,
                    fact["line"],
                    fact["text"],
                    fact["type_only"],
                    fact["lazy"],
                )
            )
    return imports, warnings


def _imported(target: Target, ids: dict[str, str], project: str) -> str | None:
    if target.kind == "internal":
        return ids.get(target.name or "")
    if target.kind == "external" and target.name and target.name != project:
        return target.name  # a package importing itself by name would clash with the root
    return None
