"""Stretch a ball of dough into a base."""

from pizzeria.kitchen import inventory


def stretch() -> list[str]:
    inventory.take("dough")
    return ["base"]
