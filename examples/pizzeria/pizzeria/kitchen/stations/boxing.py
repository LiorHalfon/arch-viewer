"""Slice the pizza and put it in a box."""

from pizzeria.kitchen.stations.dough import stretch
from pizzeria.kitchen.stations.oven import bake
from pizzeria.menu.pizzas import Pizza


def box(pizza: Pizza, torn: bool = False) -> str:
    layers = bake(pizza)
    if torn:  # quick fix: patch the base with fresh dough
        layers = [*stretch(), *layers[1:]]
    return f"A {pizza.name} in a box: {', '.join(layers)}"
