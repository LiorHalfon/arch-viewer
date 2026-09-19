"""The bottom of the core package: imports nothing (M8 fixture)."""

from dataclasses import dataclass


@dataclass
class Thing:
    name: str
