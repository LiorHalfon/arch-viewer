"""A ticket for each pizza, sent down the line."""

from pizzeria.kitchen.recipes import can_make
from pizzeria.kitchen.stations.boxing import box
from pizzeria.menu.pizzas import Pizza


def cook(pizza: Pizza) -> str:
    if not can_make(pizza):
        raise LookupError(f"Cannot make a {pizza.name} tonight")
    return box(pizza)
