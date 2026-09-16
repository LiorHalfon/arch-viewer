"""Bob's package metrics (requirement A10).

- Ca (afferent): distinct modules outside the node that import something inside it.
- Ce (efferent): distinct modules outside the node that something inside it imports.
- I = Ce / (Ca + Ce), instability; undefined when the node has no dependencies at all.
- A = abstract modules / modules, abstractness.
- D = |A + I - 1|, distance from the main sequence.

Zone: `main_sequence` when D <= threshold; otherwise `pain` (concrete and stable,
A + I < 1) or `useless` (abstract and unstable, A + I > 1); `isolated` when I is
undefined.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_THRESHOLD = 0.3


@dataclass(frozen=True, slots=True)
class Metrics:
    ca: int
    ce: int
    instability: float | None
    abstractness: float
    distance: float | None
    zone: str


def _round(value: float) -> float:
    return round(value, 3)


def metrics(
    ca: int, ce: int, abstract: int, modules: int, threshold: float = DEFAULT_THRESHOLD
) -> Metrics:
    a = abstract / modules if modules else 0.0
    if ca + ce == 0:
        return Metrics(ca, ce, None, _round(a), None, "isolated")
    i = ce / (ca + ce)
    d = abs(a + i - 1)
    return Metrics(ca, ce, _round(i), _round(a), _round(d), _zone(a, i, d, threshold))


def _zone(a: float, i: float, d: float, threshold: float) -> str:
    if d <= threshold:
        return "main_sequence"
    return "pain" if a + i < 1 else "useless"
