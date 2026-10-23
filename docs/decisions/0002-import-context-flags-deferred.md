# 2. Import context flags (lazy, TYPE_CHECKING, dynamic) deferred

Date: 2026-09-06

## Status

Accepted; implemented later (ADR 0008).

## Context

The model sketch shows `type_checking` and `dynamic` flags per import, and the first version wanted
a `lazy` flag for imports written inside functions (requirement A1 keeps them, and
they are often the edges that break a cycle).

grimp's `get_import_details` returns an `is_lazy` key, so the first version tried to use it. It is
always `False`: the scanner never sets it, only `ImportGraph.add_import(is_lazy=True)
does. Verified on grimp 3.16 with imports inside a function, a class body, a `try`
block and an `if` block — all reported `is_lazy: False`.

`TYPE_CHECKING` is available, but only as a whole-graph switch
(`build_graph(exclude_type_checking_imports=True)`), not as a per-import flag.

## Decision

The first version ships imports as `importer, imported, file, line, text` and nothing else. No flag
is emitted that cannot be filled in honestly.

All three flags arrive together later (requirements A4 and A5, ADR 0008) from one `ast` pass
over each importer's file, which the extractor can afford because it already knows
every module's path. That same pass produces the dynamic-import warnings A5 asks for.

## Consequences

Until then, a `TYPE_CHECKING` import looks like any other import in the view and in the
checker; the fixture project contains one (`sample/api/routes.py`) so the day the
flags land, the golden files show exactly what changed. The schema is versioned, so
adding the fields is a schema bump, not a break.
