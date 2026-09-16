"""The bottom of the stack: imports nothing from the project."""

from dataclasses import dataclass


@dataclass
class Order:
    amount: int
