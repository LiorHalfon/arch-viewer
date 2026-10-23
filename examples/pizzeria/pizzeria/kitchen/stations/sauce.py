"""Spread the tomato sauce on the base."""

from pizzeria.kitchen import inventory
from pizzeria.kitchen.stations.dough import stretch


def spread() -> list[str]:
    inventory.take("tomato")
    return [*stretch(), "tomato"]
