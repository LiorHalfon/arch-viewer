"""Bake the pizza."""

from pizzeria.kitchen.stations.toppings import top
from pizzeria.menu.pizzas import Pizza

TEMPERATURE = 450  # degrees Celsius: a wood-fired oven


def bake(pizza: Pizza) -> list[str]:
    return [*top(pizza), f"baked at {TEMPERATURE} C"]
