"""Glob patterns over node names and file paths.

`*` matches within one segment, `**` matches any number of segments. A name pattern
that names a package also covers everything below it, so `app.db` matches
`app.db.session` (and `app/db` matches `app/db/session.ts`).
"""

from __future__ import annotations

import re
from functools import cache

from archview.model.names import ancestors


@cache
def _compile(pattern: str, sep: str) -> re.Pattern[str]:
    s = re.escape(sep)
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**" + sep, i):
            out.append(f"(?:.*{s})?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append(f"[^{s}]*")
            i += 1
        elif pattern[i] == "?":
            out.append(f"[^{s}]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def matches_name(pattern: str, name: str, sep: str) -> bool:
    """True if `name` or one of its ancestors matches `pattern`, both split by `sep`."""
    regex = _compile(pattern, sep)
    return any(regex.fullmatch(prefix) for prefix in ancestors(name, sep))


def matches_path(pattern: str, path: str) -> bool:
    """True if the relative POSIX `path` matches the file glob `pattern`."""
    return _compile(pattern, "/").fullmatch(path) is not None


def specificity(pattern: str, sep: str) -> tuple[int, int]:
    """Longer, less wild patterns win when several match the same name."""
    return (pattern.count(sep) + 1, -pattern.count("*"))
