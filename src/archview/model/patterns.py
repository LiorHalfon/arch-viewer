"""Glob patterns over dotted names and file paths.

`*` matches within one segment, `**` matches any number of segments. A dotted
pattern that names a package also covers everything below it, so `app.db`
matches `app.db.session`.
"""

from __future__ import annotations

import re
from functools import cache


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


def matches_name(pattern: str, name: str) -> bool:
    """True if `name` or one of its ancestors matches the dotted `pattern`."""
    regex = _compile(pattern, ".")
    parts = name.split(".")
    return any(regex.fullmatch(".".join(parts[: i + 1])) for i in range(len(parts)))


def matches_path(pattern: str, path: str) -> bool:
    """True if the relative POSIX `path` matches the file glob `pattern`."""
    return _compile(pattern, "/").fullmatch(path) is not None


def specificity(pattern: str) -> tuple[int, int]:
    """Longer, less wild patterns win when several match the same name."""
    return (pattern.count(".") + 1, -pattern.count("*"))
