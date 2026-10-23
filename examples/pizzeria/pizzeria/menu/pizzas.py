"""The pizzas on the menu and what they cost."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Pizza:
    name: str
    price: float
    toppings: tuple[str, ...]


MENU = {
    "margherita": Pizza("margherita", 9.0, ("mozzarella", "basil")),
    "pepperoni": Pizza("pepperoni", 11.0, ("mozzarella", "pepperoni")),
    "funghi": Pizza("funghi", 10.5, ("mozzarella", "mushrooms")),
}


def find(name: str) -> Pizza:
    return MENU[name]
