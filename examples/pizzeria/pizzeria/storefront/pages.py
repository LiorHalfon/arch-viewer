"""The menu page and the order button."""

from pizzeria.menu.pizzas import MENU, find
from pizzeria.orders.checkout import place
from pizzeria.orders.order import Order


def menu_page() -> list[str]:
    return [f"{pizza.name}: {pizza.price:.2f}" for pizza in MENU.values()]


def order_button(phone: str, address: str, names: list[str]) -> str:
    return place(Order(phone, address, [find(name) for name in names]))
