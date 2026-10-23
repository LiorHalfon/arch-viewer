"""The bottom of the core package: imports nothing (workspace fixture)."""

from dataclasses import dataclass


@dataclass
class Thing:
    name: str
