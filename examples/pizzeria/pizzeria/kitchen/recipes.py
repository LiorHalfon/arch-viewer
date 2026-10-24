"""How to make each pizza on the menu."""

from pizzeria.kitchen import inventory
from pizzeria.menu.pizzas import Pizza


def toppings_for(pizza: Pizza) -> tuple[str, ...]:
    return pizza.toppings


def can_make(pizza: Pizza) -> bool:
    needed = ("dough", "tomato", *toppings_for(pizza))
    return all(inventory.STOCK.get(item, 0) > 0 for item in needed)
